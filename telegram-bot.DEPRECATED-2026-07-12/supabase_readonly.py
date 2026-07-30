"""Restricted Supabase client for the Telegram agent.

Two layers of enforcement keep the agent within its mandate (read-only +
append-only build-request logging):

  1. **Database-enforced** (authoritative): the client authenticates with a
     scoped PostgREST JWT carrying ``role: telegram_engineer_ro``. That Postgres
     role is granted only SELECT on the Command-Memory read tables and INSERT on
     ``build_request_inbox`` (migration 0015). The database itself rejects
     anything else.

  2. **Code-enforced** (defense in depth): this wrapper refuses to issue any
     request other than ``select(...)`` and ``insert('build_request_inbox', ...)``
     so a bug can never even attempt a forbidden mutation.

The JWT is minted at startup from ``SUPABASE_JWT_SECRET`` (preferred), or a
pre-minted token may be supplied via ``TELEGRAM_SUPABASE_KEY``.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.supabase.supabase_client import SupabaseClient, SupabaseError  # noqa: E402

INBOX_TABLE = "build_request_inbox"
RESTRICTED_ROLE = "telegram_engineer_ro"

# The only tables the agent may read (must match the GRANT SELECT list in 0015).
ALLOWED_READ_TABLES = frozenset(
    {
        "commander_memory_events",
        "missions",
        "decisions",
        "lessons_learned",
        "research_memory",
    }
)


class RestrictedAccessError(RuntimeError):
    """Raised when code attempts an operation outside the agent's mandate."""


def mint_scoped_token(secret: str, role: str = RESTRICTED_ROLE, ttl_seconds: int = 0) -> str:
    """Mint a PostgREST JWT pinning the connection to ``role``.

    ttl_seconds <= 0 mints a non-expiring token (acceptable for a long-running
    service whose secret can be rotated). PyJWT is a hard requirement here.
    """
    import jwt  # PyJWT

    now = int(time.time())
    claims: dict[str, Any] = {"role": role, "iat": now}
    if ttl_seconds > 0:
        claims["exp"] = now + ttl_seconds
    token = jwt.encode(claims, secret, algorithm="HS256")
    # PyJWT < 2 returns bytes; normalise to str.
    return token.decode("utf-8") if isinstance(token, bytes) else token


class RestrictedSupabaseClient(SupabaseClient):
    """SupabaseClient locked to read-only + append-only-to-inbox.

    Overrides the auth key with the scoped role token and blocks every mutating
    method except the single permitted insert.
    """

    def __init__(self) -> None:
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        token = self._resolve_token()
        apikey = (
            os.environ.get("SUPABASE_ANON_KEY")
            or os.environ.get("SUPABASE_PUBLISHABLE_KEY")
            or ""
        ).strip()
        if not url or not token or not apikey:
            raise SupabaseError(
                "Telegram agent needs SUPABASE_URL, a scoped token (SUPABASE_JWT_SECRET "
                "to mint one, or TELEGRAM_SUPABASE_KEY), and SUPABASE_ANON_KEY "
                "(the gateway apikey — PostgREST rejects requests whose apikey is not a "
                "recognised project key)."
            )
        self.url = url
        self.key = token
        self._apikey = apikey
        self.role = RESTRICTED_ROLE

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Gateway apikey != role token. Kong authenticates the request via the
        ``apikey`` header (must be a real project key, e.g. anon); PostgREST then
        derives the role from the ``Authorization`` bearer JWT — our scoped token."""
        headers = {
            "apikey": self._apikey,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def _resolve_token() -> str:
        secret = os.environ.get("SUPABASE_JWT_SECRET", "").strip()
        if secret:
            return mint_scoped_token(secret)
        return os.environ.get("TELEGRAM_SUPABASE_KEY", "").strip()

    # --- permitted read -----------------------------------------------------
    def select(self, table: str, columns: str = "*", filters=None, limit=None):
        if table not in ALLOWED_READ_TABLES:
            raise RestrictedAccessError(
                f"Read denied: '{table}' is not in the agent's allowed read set."
            )
        return super().select(table, columns=columns, filters=filters, limit=limit)

    # --- permitted append-only write ---------------------------------------
    def append_build_request(self, row: dict[str, Any]) -> None:
        """Append one build-request row. Uses return=minimal so the role needs
        no SELECT on the inbox table — keeping it strictly append-only."""
        self.request(
            "POST",
            f"/rest/v1/{INBOX_TABLE}",
            [row],
            headers={"Prefer": "return=minimal"},
        )

    # --- everything else is blocked ----------------------------------------
    def insert(self, table: str, rows):  # type: ignore[override]
        if table != INBOX_TABLE:
            raise RestrictedAccessError(
                f"Insert denied: agent may only append to '{INBOX_TABLE}', not '{table}'."
            )
        return self.request(
            "POST", f"/rest/v1/{INBOX_TABLE}", rows, headers={"Prefer": "return=minimal"}
        )

    def upsert(self, *args, **kwargs):  # type: ignore[override]
        raise RestrictedAccessError("upsert is not permitted for the Telegram agent.")

    def update(self, *args, **kwargs):  # type: ignore[override]
        raise RestrictedAccessError("update is not permitted for the Telegram agent.")

    def delete(self, *args, **kwargs):  # type: ignore[override]
        raise RestrictedAccessError("delete is not permitted for the Telegram agent.")

    def rpc(self, *args, **kwargs):  # type: ignore[override]
        raise RestrictedAccessError("rpc is not permitted for the Telegram agent.")


def get_client_or_none() -> RestrictedSupabaseClient | None:
    """Construct the client, returning None if Supabase is not configured.

    Supabase reads/writes are best-effort: the filesystem is the primary context
    source and the markdown inbox file is the canonical build-request record.
    """
    try:
        return RestrictedSupabaseClient()
    except SupabaseError:
        return None
