"""Scoped-role Supabase client construction for the XO bot.

USS-TJR-MSN — XO service_role decision, Option C implementation. See
.claude/skills/bot-reviews/fixes-2026-08-09/xo-bot-service-role-decision.md
and .../xo-bot-scoped-role-implemented.md for the full architecture record.

XO has run on the `service_role` key since inception — it bypasses RLS on
all 112 public tables even though the bot's own code only ever touches 13
(see migration 0135_xo_bot_scoped_role.sql for the exact table/operation
matrix and the `xo_bot` Postgres role + RLS policies it creates). This
module reuses the platform's own proven pattern from
migration 0015_telegram_engineer_ro.sql / the retired
telegram-bot/supabase_readonly.py: a self-minted PostgREST JWT carrying a
custom `role` claim, signed with SUPABASE_JWT_SECRET, verified by
Supabase's Kong+PostgREST gateway, no login/session/Supabase-Auth-user
needed for a long-running service.

Mechanism note (verified 2026-08-10, resolves the open question in the
service-role decision doc): supabase-py 2.3.4's *public* API —
`create_client(url, key, options=ClientOptions(headers={...}))` — does
**not** let Authorization differ from apikey. `SyncClient.__init__` always
overwrites `options.headers["Authorization"]` with `Bearer <key>` derived
from the second positional arg (`_get_auth_headers()`), and the lazy
`.postgrest` property re-applies the same fixed `self._auth_token` again
on first access. Verified empirically: a deliberately-wrong Authorization
passed via ClientOptions was silently discarded and replaced with the
real key's bearer token.

What *does* work (also verified empirically, with a deliberately-wrong
token that reached PostgREST and was rejected there — not by Kong for a
bad apikey): constructing the client normally with the **anon** key (so
Kong's apikey gateway check passes with a real project key, exactly as
`SUPABASE_ANON_KEY` is used for in the retired bot's own comment), then
overwriting the client's private `_auth_token` attribute *before* the
first `.table(...)` call (which is what lazily builds the underlying
postgrest-py client and applies `_auth_token` to its headers). This keeps
every existing `.table(...).select()/.insert()/.update()/.delete().execute()`
call site in app.py / voice_capture.py / engagement_dispatcher.py /
wellness_officer/intelligence.py completely unchanged — only client
*construction* changes.

This relies on a private (underscore-prefixed) supabase-py attribute, so
it is pinned to the currently-installed `supabase==2.3.4` behaviour
(requirements.txt pins this exact version already). Re-verify against
`SyncClient.__init__`/`.postgrest` source if that pin ever moves.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

log = logging.getLogger("xo-bot.scoped-supabase")

SCOPED_ROLE = "xo_bot"


def mint_scoped_token(secret: str, role: str = SCOPED_ROLE, ttl_seconds: int = 0) -> str:
    """Mint a PostgREST JWT pinning the connection to `role`.

    ttl_seconds <= 0 mints a non-expiring token — acceptable for a
    long-running service whose secret can be rotated (same call made by
    the retired bot's mint_scoped_token(), reused verbatim here). Requires
    PyJWT (added to requirements.txt).
    """
    import jwt  # PyJWT

    now = int(time.time())
    claims: dict[str, Any] = {"role": role, "iat": now}
    if ttl_seconds > 0:
        claims["exp"] = now + ttl_seconds
    token = jwt.encode(claims, secret, algorithm="HS256")
    return token.decode("utf-8") if isinstance(token, bytes) else token


def resolve_scoped_auth() -> Optional[str]:
    """Return the bearer token to use for the scoped `xo_bot` role, or None
    if scoping isn't configured yet (no SUPABASE_JWT_SECRET and no
    pre-minted XO_BOT_SCOPED_TOKEN) — callers must fall back to the
    existing service_role path when this returns None, never degrade
    silently to an unscoped or under-scoped credential."""
    secret = os.environ.get("SUPABASE_JWT_SECRET", "").strip()
    if secret:
        try:
            return mint_scoped_token(secret)
        except Exception as exc:
            log.error("[scoped-supabase] failed to mint xo_bot token from SUPABASE_JWT_SECRET: %s", exc)
            return None
    preminted = os.environ.get("XO_BOT_SCOPED_TOKEN", "").strip()
    return preminted or None


def build_scoped_client(supabase_url: str):
    """Construct a supabase-py client authenticated as the scoped `xo_bot`
    Postgres role, or return None if scoping isn't configured OR the
    configured secret/token doesn't actually verify — caller should fall
    back to the legacy service_role client in either case (see
    telegram-bots/xo/app.py::_get_supabase()).

    Requires SUPABASE_ANON_KEY (the Kong gateway apikey — a real,
    recognised project key; the scoped role's own JWT is NOT a valid
    apikey and must not be used for that header, only for Authorization).

    2026-08-10: a live-verification probe was added after a real incident
    during pre-cutover testing — a SUPABASE_JWT_SECRET was provisioned
    that turned out not to match this project's actual signing key
    (confirmed by failing to verify the existing, known-good anon key's
    own signature with it). Every table() call under that secret would
    have failed with PGRST301 ("No suitable key or wrong key type"). Prior
    to this check, build_scoped_client() returned a client unconditionally
    whenever the two env vars were merely *present*, without confirming
    the token actually works — restarting the bot with a bad secret would
    have silently killed every Supabase-backed command handler. Now a
    cheap real query is required to succeed before the scoped client is
    handed back; any failure (bad secret, bad token, network hiccup at
    startup) falls back to service_role with a loud log line instead of
    taking the bot down."""
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "").strip()
    if not anon_key:
        log.warning("[scoped-supabase] SUPABASE_ANON_KEY not set — cannot build scoped client")
        return None
    token = resolve_scoped_auth()
    if not token:
        return None

    from supabase import create_client

    client = create_client(supabase_url, anon_key)
    # See module docstring: this private-attribute patch is the only
    # verified way (supabase-py 2.3.4) to give Authorization a different
    # value than apikey while keeping the real .table() query builder API
    # every call site already uses. Must happen before the first
    # .table()/.postgrest access, which is why this function returns a
    # ready-to-use client rather than a client the caller patches later.
    client._auth_token = {"Authorization": f"Bearer {token}"}

    try:
        client.table("missions").select("mission_id").limit(1).execute()
    except Exception as exc:
        log.error(
            "[scoped-supabase] xo_bot token failed live verification (bad "
            "SUPABASE_JWT_SECRET/XO_BOT_SCOPED_TOKEN, or the secret doesn't "
            "match this project's actual signing key) — refusing to use it, "
            "falling back to service_role: %s", exc,
        )
        return None

    return client
