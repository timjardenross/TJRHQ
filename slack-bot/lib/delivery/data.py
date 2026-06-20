"""EDO — Supabase data access (graceful, non-blocking).

Reads the delivery views and writes the instrumentation tables added in
migration 0023. Every function degrades to a safe empty/False result when
Supabase is unavailable, matching the bot-wide contract.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _client():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        return c if c.is_enabled() and c.raw_client is not None else None
    except Exception as exc:  # pragma: no cover - environment dependent
        log.warning("[edo.data] Supabase unavailable: %s", exc)
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_delivery_rows(limit: int = 200) -> list[dict]:
    """Rows from the mission_delivery view. Empty list when unavailable."""
    c = _client()
    if c is None:
        return []
    try:
        res = (
            c.raw_client.table("mission_delivery")
            .select("*").order("created_at", desc=True).limit(limit).execute()
        )
        return list(res.data or [])
    except Exception as exc:
        log.error("[edo.data] fetch_delivery_rows failed: %s", exc)
        return []


def fetch_metrics() -> dict | None:
    """The mission_delivery_metrics roll-up row, or None when unavailable."""
    c = _client()
    if c is None:
        return None
    try:
        res = c.raw_client.table("mission_delivery_metrics").select("*").limit(1).execute()
        rows = list(res.data or [])
        return rows[0] if rows else None
    except Exception as exc:
        log.error("[edo.data] fetch_metrics failed: %s", exc)
        return None


def fetch_capabilities() -> list[dict]:
    c = _client()
    if c is None:
        return []
    try:
        res = c.raw_client.table("capabilities").select("*").execute()
        return list(res.data or [])
    except Exception as exc:
        log.error("[edo.data] fetch_capabilities failed: %s", exc)
        return []


def record_transition(*, mission_id: str, to_state: str, from_state: str | None = None,
                      actor: str | None = None, evidence: str | None = None) -> bool:
    """Record a real mission state transition (MSN-EDO-004). Non-blocking."""
    c = _client()
    if c is None:
        return False
    payload = {
        "mission_id": mission_id, "from_state": from_state, "to_state": to_state,
        "actor": actor, "evidence": (evidence or "")[:1000] or None, "created_at": _now(),
    }
    try:
        res = c.insert("mission_state_transitions", payload)
        return bool(getattr(res, "ok", False))
    except Exception as exc:  # pragma: no cover
        log.warning("[edo.data] record_transition failed: %s", exc)
        return False


def register_capability(*, name: str, purpose: str, owner: str | None = None,
                        status: str = "Operational") -> bool:
    """Register/refresh a capability on mission closure (MSN-EDO-002 QW3).

    Non-blocking. Uses insert; duplicate names are tolerated (the registry is a
    log of capability events, deduped at read time).
    """
    c = _client()
    if c is None:
        return False
    now = _now()
    cap_id = "CAP-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    payload = {
        "id": cap_id, "name": name[:200], "purpose": purpose[:1000],
        "owner": owner or "Engineering & Delivery Officer", "status": status,
        "created_at": now, "updated_at": now,
    }
    try:
        res = c.insert("capabilities", payload)
        return bool(getattr(res, "ok", False))
    except Exception as exc:  # pragma: no cover
        log.warning("[edo.data] register_capability failed: %s", exc)
        return False
