"""Scoped-role Supabase client construction for the REVS bot.

Same mechanism as telegram-bots/xo/scoped_supabase.py (self-minted
PostgREST JWT carrying a custom `role` claim, verified by Kong+PostgREST,
no login/session needed) — reused here rather than re-invented, pointed at
the `revs_bot` role created by migration
0147_revs_bot_scoped_role.sql.

Deliberate difference from XO's version: **no service_role fallback.**
XO is a single-user, Captain-only bot where service_role was the historical
default and the scoped role is a hardening step; falling back to it on a
misconfigured secret degrades XO's own blast radius but doesn't expose it
to the public. REVS is public-facing from day one — a silent fallback to
service_role here would mean any bug or misconfiguration in the scoped-auth
path hands a bot that talks to strangers full read/write on all ~112+
public tables, not just the 7 this bot needs. build_scoped_client()
therefore returns None on any failure, and app.py refuses to start rather
than run unscoped.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

log = logging.getLogger("revs-bot.scoped-supabase")

SCOPED_ROLE = "revs_bot"


def mint_scoped_token(secret: str, role: str = SCOPED_ROLE, ttl_seconds: int = 0) -> str:
    import jwt  # PyJWT

    now = int(time.time())
    claims: dict[str, Any] = {"role": role, "iat": now}
    if ttl_seconds > 0:
        claims["exp"] = now + ttl_seconds
    token = jwt.encode(claims, secret, algorithm="HS256")
    return token.decode("utf-8") if isinstance(token, bytes) else token


def resolve_scoped_auth() -> Optional[str]:
    secret = os.environ.get("SUPABASE_JWT_SECRET", "").strip()
    if secret:
        try:
            return mint_scoped_token(secret)
        except Exception as exc:
            log.error("[scoped-supabase] failed to mint revs_bot token from SUPABASE_JWT_SECRET: %s", exc)
            return None
    preminted = os.environ.get("REVS_BOT_SCOPED_TOKEN", "").strip()
    return preminted or None


def build_scoped_client(supabase_url: str):
    """Construct a supabase-py client authenticated as `revs_bot`, or None
    if scoping isn't configured or the token fails live verification.
    Caller (app.py) must treat None as fatal — see module docstring."""
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "").strip()
    if not anon_key:
        log.error("[scoped-supabase] SUPABASE_ANON_KEY not set — cannot build scoped client")
        return None
    token = resolve_scoped_auth()
    if not token:
        log.error("[scoped-supabase] no SUPABASE_JWT_SECRET or REVS_BOT_SCOPED_TOKEN configured")
        return None

    from supabase import create_client

    client = create_client(supabase_url, anon_key)
    # Private-attribute patch — see xo/scoped_supabase.py's docstring for
    # why this is the only verified way (supabase-py 2.3.4) to give
    # Authorization a different value than apikey.
    client._auth_token = {"Authorization": f"Bearer {token}"}

    try:
        client.table("revs_users").select("id").limit(1).execute()
    except Exception as exc:
        log.error(
            "[scoped-supabase] revs_bot token failed live verification "
            "(bad SUPABASE_JWT_SECRET/REVS_BOT_SCOPED_TOKEN, wrong signing "
            "key, or migration 0147 not yet applied) — refusing to use it: %s",
            exc,
        )
        return None

    return client
