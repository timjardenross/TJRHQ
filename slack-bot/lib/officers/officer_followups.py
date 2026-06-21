"""Officer Follow-Up & Tracking Engine (EXEC-010A WP5).

Officers track the outcomes of their actions. This module detects idle missions,
overdue actions, and stale follow-ups so that nothing slips through the cracks
without escalation.

Idle detection: mission idle ≥ 7 days without update → escalate to officer.
Overdue detection: follow-up past due date → advance to next escalation level.

Storage: decisions table
  owner = `officer_followup:{follow_up_id}`
  statement = `[OFFICER FOLLOWUP] {mission_id}: {officer}`
  rationale = `MISSION: {id} | OFFICER: {officer} | DUE: {date} | STATUS: {status} | CHECKS: {n}`

Public API:
    FollowUpStatus
    FollowUp
    register_follow_up(mission_id, officer, due_days, context)  -> FollowUp
    check_follow_ups()                                          -> list[FollowUp]
    resolve_follow_up(follow_up_id)                             -> None
    list_officer_follow_ups(officer)                            -> list[FollowUp]
    IDLE_THRESHOLD_DAYS
"""

from __future__ import annotations

import logging
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

IDLE_THRESHOLD_DAYS = 7
_FOLLOWUP_OWNER_PREFIX = "officer_followup:"


# ── Enums ─────────────────────────────────────────────────────────────────────

class FollowUpStatus(str, Enum):
    PENDING   = "pending"
    ACTIVE    = "active"
    RESOLVED  = "resolved"
    ESCALATED = "escalated"
    OVERDUE   = "overdue"


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class FollowUp:
    follow_up_id: str
    mission_id: str
    officer: str
    due_date: datetime
    status: FollowUpStatus = FollowUpStatus.PENDING
    check_count: int = 0
    context: str = ""
    registered_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_overdue(self) -> bool:
        return datetime.utcnow() > self.due_date and self.status not in (
            FollowUpStatus.RESOLVED, FollowUpStatus.ESCALATED
        )

    @property
    def days_overdue(self) -> int:
        if not self.is_overdue:
            return 0
        return (datetime.utcnow() - self.due_date).days


# ── Storage helpers ───────────────────────────────────────────────────────────

def _build_rationale(fu: FollowUp) -> str:
    return (
        f"MISSION: {fu.mission_id} | OFFICER: {fu.officer} | "
        f"DUE: {fu.due_date.date().isoformat()} | STATUS: {fu.status.value} | "
        f"CHECKS: {fu.check_count}"
    )


def _row_to_followup(row: dict[str, Any]) -> FollowUp | None:
    """Parse a decisions table row into a FollowUp."""
    try:
        owner = row.get("owner", "")
        follow_up_id = owner.replace(_FOLLOWUP_OWNER_PREFIX, "", 1)
        rationale = row.get("rationale", "")
        parts: dict[str, str] = {}
        for part in rationale.split("|"):
            part = part.strip()
            if ":" in part:
                k, v = part.split(":", 1)
                parts[k.strip()] = v.strip()

        def _date(s: str) -> datetime:
            return datetime.fromisoformat(s) if s else datetime.utcnow()

        return FollowUp(
            follow_up_id=follow_up_id,
            mission_id=parts.get("MISSION", ""),
            officer=parts.get("OFFICER", ""),
            due_date=_date(parts.get("DUE", "")),
            status=_try_enum(FollowUpStatus, parts.get("STATUS", ""), FollowUpStatus.PENDING),
            check_count=int(parts.get("CHECKS", "0") or "0"),
        )
    except Exception:
        return None


def _try_enum(cls: type, val: str, default: Any) -> Any:
    try:
        return cls(val)
    except (ValueError, KeyError):
        return default


# ── Public API ────────────────────────────────────────────────────────────────

def register_follow_up(
    mission_id: str,
    officer: str,
    due_days: int = IDLE_THRESHOLD_DAYS,
    context: str = "",
) -> FollowUp:
    """Register a follow-up tracking record for an officer action."""
    follow_up_id = uuid.uuid4().hex[:12]
    due_date = datetime.utcnow() + timedelta(days=due_days)
    fu = FollowUp(
        follow_up_id=follow_up_id,
        mission_id=mission_id,
        officer=officer,
        due_date=due_date,
        context=context,
    )
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if c.is_enabled() and c.raw_client:
            owner = f"{_FOLLOWUP_OWNER_PREFIX}{follow_up_id}"
            existing = (
                c.raw_client.table("decisions")
                .select("id")
                .ilike("statement", f"%[OFFICER FOLLOWUP] {mission_id}: {officer}%")
                .eq("status", "active")
                .limit(1)
                .execute()
            )
            if not list(existing.data or []):
                c.raw_client.table("decisions").insert({
                    "owner": owner,
                    "statement": f"[OFFICER FOLLOWUP] {mission_id}: {officer}",
                    "rationale": _build_rationale(fu),
                    "decision_type": "officer_followup",
                    "status": "active",
                }).execute()
        log.info("[officer_followups] Registered follow-up %s: %s due %s",
                 follow_up_id, mission_id, due_date.date())
    except Exception as exc:
        log.debug("[officer_followups] Register failed %s: %s", mission_id, exc)
    return fu


def check_follow_ups() -> list[FollowUp]:
    """Return all overdue or pending-idle follow-ups requiring officer attention."""
    overdue: list[FollowUp] = []
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return []

        res = (
            c.raw_client.table("decisions")
            .select("owner,statement,rationale")
            .ilike("owner", f"{_FOLLOWUP_OWNER_PREFIX}%")
            .neq("status", "resolved")
            .execute()
        )
        for row in res.data or []:
            fu = _row_to_followup(row)
            if fu and fu.is_overdue:
                overdue.append(fu)
        log.info("[officer_followups] %d overdue follow-up(s) detected", len(overdue))
    except Exception as exc:
        log.debug("[officer_followups] Check failed: %s", exc)
    return overdue


def resolve_follow_up(follow_up_id: str) -> None:
    """Mark a follow-up as resolved."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return
        owner = f"{_FOLLOWUP_OWNER_PREFIX}{follow_up_id}"
        c.raw_client.table("decisions").update({"status": "resolved"}).eq("owner", owner).execute()
        log.info("[officer_followups] Resolved follow-up %s", follow_up_id)
    except Exception as exc:
        log.debug("[officer_followups] Resolve failed %s: %s", follow_up_id, exc)


def list_officer_follow_ups(officer: str) -> list[FollowUp]:
    """Return all active follow-ups for a specific officer."""
    result: list[FollowUp] = []
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return []

        res = (
            c.raw_client.table("decisions")
            .select("owner,statement,rationale")
            .ilike("owner", f"{_FOLLOWUP_OWNER_PREFIX}%")
            .ilike("rationale", f"%OFFICER: {officer}%")
            .neq("status", "resolved")
            .execute()
        )
        for row in res.data or []:
            fu = _row_to_followup(row)
            if fu:
                result.append(fu)
    except Exception as exc:
        log.debug("[officer_followups] List failed for %s: %s", officer, exc)
    return result


def detect_idle_missions(missions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return missions that have had no update in ≥ IDLE_THRESHOLD_DAYS.

    Reads from the provided missions list (passed from daily cycle) rather than
    querying independently — avoids parallel data fetching.
    """
    idle: list[dict[str, Any]] = []
    cutoff = datetime.utcnow() - timedelta(days=IDLE_THRESHOLD_DAYS)
    for m in missions:
        updated = m.get("updated_at") or m.get("created_at") or ""
        try:
            if updated:
                dt = datetime.fromisoformat(str(updated).rstrip("Z"))
                if dt < cutoff:
                    idle.append(m)
        except (ValueError, TypeError):
            pass
    return idle


__all__ = [
    "FollowUpStatus",
    "FollowUp",
    "IDLE_THRESHOLD_DAYS",
    "register_follow_up",
    "check_follow_ups",
    "resolve_follow_up",
    "list_officer_follow_ups",
    "detect_idle_missions",
]
