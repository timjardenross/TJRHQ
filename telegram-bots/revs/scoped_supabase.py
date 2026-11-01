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

Mechanism history (2026-09-14, supabase-py 2.3.4 -> 2.31.0 bump): this
module previously gave Authorization a different value than apikey via a
private-attribute patch, `client._auth_token = {"Authorization": ...}`,
documented at the time as "the only verified way (supabase-py 2.3.4)".
That attribute is now DEAD — confirmed by grepping the installed 2.31.0
`supabase`/`postgrest` package source for `_auth_token` (zero hits) and by
constructing a real client, setting the attribute, and checking that
`client.postgrest.session.headers` never changes. Setting it silently does
nothing; a naive version bump that kept the old patch would have made this
public-facing bot run as the *anon* role with no error, no log line, and
no failed live-verification query (the verification query itself would
just quietly execute as anon rather than revs_bot) — exactly the failure
mode this module's own "no service_role fallback" design was built to
prevent, just via a different unscoped role.

The verified, public replacement — same one telegram-bots/xo/
scoped_supabase.py already documents and this module now uses too —
passes Authorization through `ClientOptions.headers` at construction time:

    from supabase import create_client, ClientOptions
    client = create_client(
        supabase_url, anon_key,
        options=ClientOptions(headers={"Authorization": f"Bearer {token}"}),
    )

One import detail worth flagging since it cost real debugging time here:
`ClientOptions` must come from the top-level `supabase` package (or
equivalently `supabase._sync.client.ClientOptions`, the `SyncClientOptions`
alias), NOT `supabase.lib.client_options.ClientOptions` — the latter is
that class's own *base* class, missing a `storage` field `Client.__init__`
requires on 2.31.0, and raises `AttributeError: 'ClientOptions' object has
no attribute 'storage'` at construction. Empirically verified end-to-end
on supabase-py 2.31.0 + httpx 0.28.1: the resulting
`client.postgrest.session.headers` carries the real anon key under
`apikey` and the scoped `revs_bot` JWT under `authorization`, genuinely
independent, exactly like the old patch was trying to achieve. `.table()`
calls resolve through this same `client.postgrest` instance (via
`.from_()`), so every query this module's caller makes carries the scoped
role correctly.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

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


def resolve_scoped_auth() -> str | None:
    secret = os.environ.get("SUPABASE_JWT_SECRET", "").strip()
    if secret:
        try:
            return mint_scoped_token(secret)
        except Exception as exc:  # noqa: BLE001 - JWT mint surface (bad secret/lib error) is unpredictable, already logged, and callers correctly fall back on None
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

    from supabase import ClientOptions, create_client

    # See module docstring: since supabase-py 2.4.3 (and re-verified live
    # against 2.31.0 here), passing Authorization via ClientOptions.headers
    # is the public, supported way to give Authorization a different value
    # than apikey — the old private `_auth_token` attribute patch is dead
    # on this version and would silently do nothing.
    client = create_client(
        supabase_url, anon_key,
        options=ClientOptions(headers={"Authorization": f"Bearer {token}"}),
    )

    try:
        client.table("revs_users").select("id").limit(1).execute()
    except Exception as exc:  # noqa: BLE001 - live Supabase verification query surface is unpredictable, already logged, and this is a deliberate fail-closed security check
        log.error(
            "[scoped-supabase] revs_bot token failed live verification "
            "(bad SUPABASE_JWT_SECRET/REVS_BOT_SCOPED_TOKEN, wrong signing "
            "key, or migration 0147 not yet applied) — refusing to use it: %s",
            exc,
        )
        return None

    return client
