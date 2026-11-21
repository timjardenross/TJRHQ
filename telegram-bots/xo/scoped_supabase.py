"""Scoped-role Supabase client construction for the XO bot.

USS-TJR-MSN — XO service_role decision, Option C implementation. See
.claude/skills/bot-reviews/fixes-2026-08-09/xo-bot-service-role-decision.md
and .../xo-bot-scoped-role-implemented.md for the full architecture record.
Redesigned for USS-TJR-MSN-0370 — see
knowledge/missions/USS-TJR-MSN-0370-supabase-investigation-knowledge-record.md
for the full investigation (dependency-conflict trail, empirical proof,
and why Dependabot PR #157's full 2.3.4 -> 2.31.0 bump is still blocked).

XO has run on the `service_role` key since inception — it bypasses RLS on
all 112 public tables even though the bot's own code only ever touches 13
(see migration 0135_xo_bot_scoped_role.sql for the exact table/operation
matrix and the `xo_bot` Postgres role + RLS policies it creates). This
module originally reused the platform's own proven pattern from
migration 0015_telegram_engineer_ro.sql / the retired
telegram-bot/supabase_readonly.py: a self-minted PostgREST JWT carrying a
custom `role` claim. It now prefers a private ES256 JWK imported into
Supabase's signing-keys system and refreshes its short-lived token before
each Data API call. SUPABASE_JWT_SECRET remains a temporary legacy fallback.
No login/session/Supabase-Auth-user is needed for the long-running service.

Mechanism history: on supabase-py 2.3.4 (the original pin), the *public*
`create_client(url, key, options=ClientOptions(headers={...}))` API could
not make Authorization differ from apikey — `SyncClient.__init__`
unconditionally overwrote `options.headers["Authorization"]` with
`Bearer <key>`, and the lazy `.postgrest` property re-applied the same
fixed private `self._auth_token` again on first access. That version of
this module worked around it by constructing the client with the anon key
and then monkeypatching the private `client._auth_token` attribute before
the first `.table(...)` call.

That hack is now DEAD: supabase-py removed the `SyncClient` name (renamed
to `Client`) and the whole `_auth_token` mechanism it depended on
somewhere around 2.5.0, and stopped exporting anything by that name by
2.24.0. Verified by installing every relevant version from PyPI in a
throwaway venv and reading `supabase/_sync/client.py` directly — there is
no `_auth_token` attribute anywhere in the class from 2.5.0 onward.

The good news: **supabase-py fixed the underlying limitation properly, in
its own public API, back in 2.4.3** (verified by installing 2.4.2 and
2.4.3 side by side and diffing `_sync/client.py`). From 2.4.3 onward,
`Client.__init__`'s `_get_auth_headers()` reads any Authorization the
caller already put in `options.headers` and uses it as-is instead of
overwriting it with a header derived from the key argument:

    from supabase import create_client
    from supabase.lib.client_options import ClientOptions

    client = create_client(
        supabase_url,
        anon_key,                     # -> Kong apikey gateway check
        options=ClientOptions(headers={"Authorization": f"Bearer {token}"}),
    )

apiKey and Authorization end up genuinely independent — empirically
verified (not just read from source) with a live `create_client()` call
whose resulting `client.postgrest.session.headers` had `apiKey ==
anon_key` and `Authorization == f"Bearer {scoped_token}"` on supabase-py
2.4.3, 2.7.4, 2.24.0 and 2.31.0 alike. No private attribute, no
monkeypatch, no version-pinned internal to re-verify on every bump.

Why this module still can't track supabase-py HEAD (or Dependabot PR
#157's 2.31.0 target): python-telegram-bot 20.7 hard-pins
`httpx~=0.25.2` (see requirements.txt). Starting with the transitive deps
that ship alongside supabase-py ~2.8.1-2.9.x (postgrest>=0.17.0,
gotrue>=2.9.0), those packages call `httpx.Client(..., proxy=...)` — the
`proxy` (singular) kwarg that httpx only added in 0.26, replacing the old
`proxies` (plural) kwarg. Under httpx<0.26 this crashes at client
construction with `TypeError: Client.__init__() got an unexpected keyword
argument 'proxy'`, reproduced live. supabase-py's OWN declared PyPI
metadata bounds are not tight enough to catch this — its
`httpx>=0.24,<0.28` claim is technically satisfied by httpx 0.25.2 while
its pinned postgrest/gotrue at that release already require the newer
`proxy` kwarg; the version bound and the runtime behaviour disagree.
requirements.txt therefore pins `supabase==2.7.4` (the newest release
whose OWN postgrest bound, `<0.17.0`, still keeps postgrest below that
line) and `gotrue<2.9.0` explicitly, since supabase's own gotrue bound
(`>=1.3,<3.0`) is loose enough that pip otherwise resolves the newest
2.x gotrue and hits the same `proxy=` crash. This is a real, verified
`pip install` ResolutionImpossible / live TypeError, not a hypothetical —
see the knowledge record for the full version bisection.

Bottom line for any future re-attempt at PR #157's full 2.31.0 bump: it
needs python-telegram-bot upgraded past 20.7 to a version whose networking
no longer needs httpx<0.26 first. That is a separate, larger piece of work
(PTB's HTTPXRequest/proxy handling changed across major versions) and is
explicitly out of scope for this module's fix.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

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


def mint_scoped_token_from_jwk(
    private_jwk: str,
    role: str = SCOPED_ROLE,
    ttl_seconds: int = 300,
) -> str:
    """Mint a short-lived ES256 token from a Supabase-imported private JWK.

    The JWK's ``kid`` is required so Supabase can select the corresponding
    public verification key. ``exp`` is always present, as required by the
    signing-keys system. The private JWK must remain server-side.
    """
    import json

    import jwt  # PyJWT

    parsed = json.loads(private_jwk)
    kid = parsed.get("kid")
    if not kid:
        raise ValueError("XO_BOT_SIGNING_KEY_JWK is missing kid")
    if parsed.get("kty") != "EC" or parsed.get("crv") != "P-256":
        raise ValueError("XO_BOT_SIGNING_KEY_JWK must be an EC P-256 key")
    if "d" not in parsed:
        raise ValueError("XO_BOT_SIGNING_KEY_JWK must contain private key material")

    now = int(time.time())
    claims: dict[str, Any] = {
        "role": role,
        "iat": now,
        "exp": now + max(60, ttl_seconds),
    }
    key = jwt.PyJWK.from_dict(parsed).key
    token = jwt.encode(claims, key, algorithm="ES256", headers={"kid": kid, "typ": "JWT"})
    return token.decode("utf-8") if isinstance(token, bytes) else token


def _asymmetric_token_factory():
    """Return a fresh-token callable when an imported signing key is set."""
    private_jwk = os.environ.get("XO_BOT_SIGNING_KEY_JWK", "").strip()
    if not private_jwk:
        return None
    ttl = int(os.environ.get("XO_BOT_TOKEN_TTL_SECONDS", "300"))
    return lambda: mint_scoped_token_from_jwk(private_jwk, ttl_seconds=ttl)


def resolve_scoped_auth() -> str | None:
    """Return the bearer token to use for the scoped `xo_bot` role, or None
    if scoping isn't configured yet. The preferred source is an imported
    asymmetric signing key; the legacy JWT secret and a pre-minted token are
    migration fallbacks. Callers must fall back to the existing service_role
    path when this returns None, never silently use an under-scoped token."""
    token_factory = _asymmetric_token_factory()
    if token_factory:
        try:
            return token_factory()
        except Exception as exc:  # noqa: BLE001 - invalid secret material must fail closed
            log.error("[scoped-supabase] failed to mint xo_bot token from imported signing key: %s", exc)
            return None

    secret = os.environ.get("SUPABASE_JWT_SECRET", "").strip()
    if secret:
        try:
            return mint_scoped_token(secret)
        except Exception as exc:  # noqa: BLE001 - JWT mint surface (bad secret/lib error) is unpredictable, already logged, and callers correctly fall back on None
            log.error("[scoped-supabase] failed to mint xo_bot token from SUPABASE_JWT_SECRET: %s", exc)
            return None
    preminted = os.environ.get("XO_BOT_SCOPED_TOKEN", "").strip()
    return preminted or None


def _client_options_class():
    """The ClientOptions class create_client() expects.

    supabase-py 2.32.0's sync client reads `client_options.storage`, which only SyncClientOptions has
    (the base ClientOptions, used by 2.7.4 and older, does not): passing the base class on 2.32.0 fails
    with "'ClientOptions' object has no attribute 'storage'". Older releases only have ClientOptions.
    (USS-TJR-MSN-0412, found while testing the venv rebuild.)"""
    from supabase.lib import client_options as co

    return getattr(co, "SyncClientOptions", co.ClientOptions)


def _gateway_api_key() -> str:
    """Return the replacement gateway key, with a temporary legacy fallback."""
    return (
        os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
        or os.environ.get("SUPABASE_ANON_KEY", "").strip()
    )


class _RefreshingScopedClient:
    """Refresh the short-lived asymmetric bearer before each Data API call."""

    def __init__(self, client, token_factory):
        self._client = client
        self._token_factory = token_factory

    def _refresh(self) -> None:
        self._client.postgrest.auth(self._token_factory())

    def table(self, table_name: str):
        self._refresh()
        return self._client.table(table_name)

    def rpc(self, function_name: str, params: dict | None = None):
        self._refresh()
        return self._client.rpc(function_name, params)

    def __getattr__(self, name: str):
        return getattr(self._client, name)


def build_scoped_client(supabase_url: str):
    """Construct a supabase-py client authenticated as the scoped `xo_bot`
    Postgres role, or return None if scoping isn't configured OR the
    configured secret/token doesn't actually verify — caller should fall
    back to the legacy service_role client in either case (see
    telegram-bots/xo/app.py::_get_supabase()).

    Requires SUPABASE_PUBLISHABLE_KEY (or the temporary SUPABASE_ANON_KEY
    fallback) for the gateway apikey. The scoped role's own JWT is only for
    Authorization and must not be used as the apikey.

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
    gateway_key = _gateway_api_key()
    if not gateway_key:
        log.warning("[scoped-supabase] SUPABASE_PUBLISHABLE_KEY not set — cannot build scoped client")
        return None
    token_factory = _asymmetric_token_factory()
    token = resolve_scoped_auth()
    if not token:
        return None

    from supabase import create_client

    ClientOptions = _client_options_class()

    # See module docstring: since supabase-py 2.4.3, passing Authorization
    # via ClientOptions.headers is the public, supported way to give
    # Authorization a different value than the apikey (derived from
    # anon_key below) — no private-attribute patch needed. Every existing
    # .table()/.postgrest call site is unaffected; only construction
    # changes.
    client = create_client(
        supabase_url,
        gateway_key,
        options=ClientOptions(headers={"Authorization": f"Bearer {token}"}),
    )

    scoped_client = _RefreshingScopedClient(client, token_factory) if token_factory else client

    try:
        scoped_client.table("missions").select("mission_id").limit(1).execute()
    except Exception as exc:  # noqa: BLE001 - live Supabase verification query surface is unpredictable, already logged, and this is a deliberate fail-closed security check
        log.error(
            "[scoped-supabase] xo_bot token failed live verification (bad "
            "SUPABASE_JWT_SECRET/XO_BOT_SCOPED_TOKEN, or the secret doesn't "
            "match this project's actual signing key) — refusing to use it, "
            "falling back to service_role: %s", exc,
        )
        return None

    return scoped_client
