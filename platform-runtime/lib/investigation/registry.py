"""Investigation Registry (EXEC-004 WP2 / WP8).

Open, update, close, and query investigations in Command Memory.

Storage (decisions table):
  statement : "[INVESTIGATION] {type}: {question[:100]}"
  owner     : "investigation:{inv_id}"
  rationale : "SOURCE: {src} | TYPE: {type} | STATUS: {status} |
               OFFICER: {officer} | CONTEXT: {context[:150]} | OPENED: {ts}"

Status updates: rationale field updated in-place via Supabase.
Closed investigations: STATUS set to "closed", OUTCOME appended.

Public API:
    open_investigation(...)      -> str | None  (inv_id)
    update_investigation_status(...) -> bool
    close_investigation(...)     -> bool
    get_open_investigations(...) -> list[Investigation]
    get_investigation(...)       -> Investigation | None
    get_investigations_summary() -> dict
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.investigation.framework import (
    Investigation, InvestigationType, InvestigationStatus, InvestigationOutcome,
    INV_STATEMENT_PREFIX, INV_OWNER_PREFIX,
)


# ── Rationale helpers ─────────────────────────────────────────────────────────

def _parse_rationale(rationale: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for segment in (rationale or "").split(" | "):
        if ": " in segment:
            k, v = segment.split(": ", 1)
            parts[k.strip()] = v.strip()
    return parts


def _build_rationale(
    source: str,
    inv_type: str,
    status: str,
    officer: str,
    context: str,
    outcome: str = "",
    opened_at: datetime | None = None,
) -> str:
    ts = (opened_at or datetime.utcnow()).isoformat()
    parts = [
        f"SOURCE: {source}",
        f"TYPE: {inv_type}",
        f"STATUS: {status}",
        f"OFFICER: {officer}",
        f"CONTEXT: {str(context)[:150]}",
        f"OPENED: {ts}",
    ]
    if outcome:
        parts.append(f"OUTCOME: {outcome}")
    return " | ".join(parts)


def _row_to_investigation(row: dict[str, Any]) -> Investigation | None:
    owner = str(row.get("owner") or "")
    if not owner.startswith(INV_OWNER_PREFIX):
        return None

    inv_id = owner[len(INV_OWNER_PREFIX):]
    parts  = _parse_rationale(str(row.get("rationale") or ""))

    status_str  = parts.get("STATUS", "open")
    outcome_str = parts.get("OUTCOME", "")

    try:
        status = InvestigationStatus(status_str)
    except ValueError:
        status = InvestigationStatus.OPEN

    try:
        outcome: InvestigationOutcome | None = InvestigationOutcome(outcome_str) if outcome_str else None
    except ValueError:
        outcome = None

    try:
        inv_type = InvestigationType(parts.get("TYPE", "operational"))
    except ValueError:
        inv_type = InvestigationType.OPERATIONAL

    opened_raw = parts.get("OPENED", "")
    opened_at  = datetime.utcnow()
    if opened_raw:
        try:
            opened_at = datetime.fromisoformat(opened_raw.replace("Z", "+00:00"))
        except ValueError:
            pass

    statement   = str(row.get("statement") or "")
    type_prefix = f"{INV_STATEMENT_PREFIX} {inv_type.value}: "
    question    = statement[len(type_prefix):] if statement.startswith(type_prefix) else statement

    return Investigation(
        investigation_id=inv_id,
        question=question,
        investigation_type=inv_type,
        source=parts.get("SOURCE", ""),
        officer=parts.get("OFFICER", ""),
        status=status,
        context=parts.get("CONTEXT", ""),
        outcome=outcome,
        opened_at=opened_at,
    )


# ── Deduplication ─────────────────────────────────────────────────────────────

def _has_open_investigation(officer: str, inv_type: str, question_prefix: str) -> bool:
    """Return True if an open investigation already exists for this officer+type+question."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return False

        res = (
            c.raw_client.table("decisions")
            .select("rationale")
            .like("owner", f"{INV_OWNER_PREFIX}%")
            .ilike("statement", f"{INV_STATEMENT_PREFIX} {inv_type}%")
            .limit(10)
            .execute()
        )
        for row in res.data or []:
            p = _parse_rationale(str(row.get("rationale") or ""))
            if p.get("OFFICER") == officer and p.get("STATUS") not in ("closed",):
                return True
        return False
    except Exception as exc:
        log.debug("[investigation.registry] Dedup check failed: %s", exc)
        return False


# ── Public API ────────────────────────────────────────────────────────────────

def open_investigation(
    question: str,
    investigation_type: InvestigationType | str,
    source: str,
    officer: str,
    context: str = "",
    *,
    skip_dedup: bool = False,
) -> str | None:
    """Open a new investigation in Command Memory.

    Args:
        question:           The question being investigated
        investigation_type: InvestigationType or its string value
        source:             Who/what triggered the investigation
        officer:            Lead investigating officer
        context:            Additional context
        skip_dedup:         If True, bypass duplicate check (for forced re-investigations)

    Returns:
        investigation_id string (e.g. "inv-a1b2c3d4") or None on failure.
    """
    try:
        from command_memory_integration import log_decision_to_command_memory

        inv_type_str = (
            investigation_type.value
            if isinstance(investigation_type, InvestigationType)
            else str(investigation_type)
        )

        if not skip_dedup and _has_open_investigation(officer, inv_type_str, question[:40]):
            log.debug(
                "[investigation.registry] Skipping duplicate: %s / %s",
                officer, inv_type_str,
            )
            return None

        inv_id = f"inv-{uuid4().hex[:8]}"

        log_decision_to_command_memory(
            statement=f"{INV_STATEMENT_PREFIX} {inv_type_str}: {question[:100]}",
            rationale=_build_rationale(
                source=source,
                inv_type=inv_type_str,
                status="open",
                officer=officer,
                context=context,
            ),
            owner=f"{INV_OWNER_PREFIX}{inv_id}",
        )

        log.info(
            "[investigation.registry] Opened: %s — %s (%s / %s)",
            inv_id, question[:60], officer, inv_type_str,
        )
        return inv_id

    except Exception as exc:
        log.warning("[investigation.registry] open_investigation failed: %s", exc)
        return None


def update_investigation_status(
    investigation_id: str,
    new_status: InvestigationStatus,
    notes: str = "",
) -> bool:
    """Update the status of an open investigation."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return False

        owner = f"{INV_OWNER_PREFIX}{investigation_id}"
        res   = (
            c.raw_client.table("decisions")
            .select("id,rationale")
            .eq("owner", owner)
            .limit(1)
            .execute()
        )
        rows = list(res.data or [])
        if not rows:
            return False

        p = _parse_rationale(str(rows[0].get("rationale") or ""))
        p["STATUS"] = new_status.value
        if notes:
            p["NOTES"] = notes[:100]

        new_rationale = " | ".join(f"{k}: {v}" for k, v in p.items())
        c.raw_client.table("decisions").update(
            {"rationale": new_rationale}
        ).eq("id", rows[0]["id"]).execute()

        return True

    except Exception as exc:
        log.debug("[investigation.registry] update_status failed: %s", exc)
        return False


def close_investigation(
    investigation_id: str,
    outcome: InvestigationOutcome,
    notes: str = "",
    mission_id: str | None = None,
) -> bool:
    """Close an investigation with a recorded outcome."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return False

        owner = f"{INV_OWNER_PREFIX}{investigation_id}"
        res   = (
            c.raw_client.table("decisions")
            .select("id,rationale")
            .eq("owner", owner)
            .limit(1)
            .execute()
        )
        rows = list(res.data or [])
        if not rows:
            return False

        p = _parse_rationale(str(rows[0].get("rationale") or ""))
        p["STATUS"]  = InvestigationStatus.CLOSED.value
        p["OUTCOME"] = outcome.value
        p["CLOSED"]  = datetime.utcnow().isoformat()
        if notes:
            p["NOTES"] = notes[:100]
        if mission_id:
            p["MISSION"] = mission_id

        new_rationale = " | ".join(f"{k}: {v}" for k, v in p.items())
        c.raw_client.table("decisions").update(
            {"rationale": new_rationale}
        ).eq("id", rows[0]["id"]).execute()

        log.info(
            "[investigation.registry] Closed: %s — outcome: %s",
            investigation_id, outcome.value,
        )
        return True

    except Exception as exc:
        log.debug("[investigation.registry] close_investigation failed: %s", exc)
        return False


def get_open_investigations(limit: int = 20) -> list[Investigation]:
    """Return all investigations not yet closed, sorted by opened_at desc."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return []

        res = (
            c.raw_client.table("decisions")
            .select("id,statement,rationale,owner,created_at")
            .like("owner", f"{INV_OWNER_PREFIX}%")
            .order("created_at", desc=True)
            .limit(limit * 2)  # over-fetch to filter closed
            .execute()
        )

        investigations: list[Investigation] = []
        for row in res.data or []:
            inv = _row_to_investigation(row)
            if inv and inv.status != InvestigationStatus.CLOSED:
                investigations.append(inv)
            if len(investigations) >= limit:
                break

        return investigations

    except Exception as exc:
        log.debug("[investigation.registry] get_open_investigations failed: %s", exc)
        return []


def get_investigation(investigation_id: str) -> Investigation | None:
    """Fetch a specific investigation by ID."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return None

        res = (
            c.raw_client.table("decisions")
            .select("id,statement,rationale,owner,created_at")
            .eq("owner", f"{INV_OWNER_PREFIX}{investigation_id}")
            .limit(1)
            .execute()
        )
        rows = list(res.data or [])
        if not rows:
            return None
        return _row_to_investigation(rows[0])

    except Exception as exc:
        log.debug("[investigation.registry] get_investigation failed: %s", exc)
        return None


def get_investigations_summary() -> dict[str, Any]:
    """Return counts by status for the Captain/Number One view."""
    try:
        investigations = get_open_investigations(limit=100)
        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}
        for inv in investigations:
            by_status[inv.status.value] = by_status.get(inv.status.value, 0) + 1
            by_type[inv.investigation_type.value] = by_type.get(inv.investigation_type.value, 0) + 1
        return {
            "open_total": len(investigations),
            "by_status": by_status,
            "by_type": by_type,
        }
    except Exception:
        return {"open_total": 0, "by_status": {}, "by_type": {}}


__all__ = [
    "open_investigation",
    "update_investigation_status",
    "close_investigation",
    "get_open_investigations",
    "get_investigation",
    "get_investigations_summary",
]
