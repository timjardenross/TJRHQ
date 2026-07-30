"""Officer Escalation Framework (EXEC-010A WP6).

Officers escalate items through a six-level chain rather than going direct to
the Captain. The exception router (core/coordination/exception_router.py) handles
the final routing decision; this module governs the escalation lifecycle within
the officer layer.

Escalation levels:
  L0 OBSERVE        — officer notes the signal; no action yet
  L1 FLAG           — officer flags to self / own queue; monitoring begins
  L2 COORDINATE     — officer notifies Number One; PMO aware
  L3 ESCALATE       — Number One escalates to XO; approval or resolution expected
  L4 CRITICAL       — XO surfaces to Captain brief with recommended action
  L5 CAPTAIN        — Captain decision required; enters approval queue

Age-out rules:
  L0 → L1 if unresolved after 1 day
  L1 → L2 if unresolved after 3 days
  L2 → L3 if unresolved after 5 days
  L3 → L4 if unresolved after 3 days
  L4 → L5 immediately (XO escalation to Captain)

Storage: decisions table
  owner = `officer_esc:{esc_id}`
  statement = `[OFFICER ESC] L{level} {officer}: {item_type}`
  rationale = `OFFICER: | ITEM_TYPE: | LEVEL: | ESCALATED_AT: | RESOLVE_BY: | REASON:`

Public API:
    EscalationLevel
    EscalationItem
    EscalationChain
    create_escalation(officer, item_type, title, severity, ctx)  -> EscalationItem
    advance_escalation(esc_id)                                   -> EscalationItem | None
    resolve_escalation(esc_id)                                   -> None
    get_overdue_escalations()                                    -> list[EscalationItem]
    build_escalation_chain(esc_item, ctx)                        -> EscalationChain
"""

from __future__ import annotations

import logging
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

_ESC_OWNER_PREFIX = "officer_esc:"

# Days before automatic level advancement
_ADVANCE_AFTER_DAYS: dict[int, int] = {0: 1, 1: 3, 2: 5, 3: 3, 4: 0}


# ── Escalation level ──────────────────────────────────────────────────────────

class EscalationLevel(IntEnum):
    L0_OBSERVE    = 0
    L1_FLAG       = 1
    L2_COORDINATE = 2
    L3_ESCALATE   = 3
    L4_CRITICAL   = 4
    L5_CAPTAIN    = 5

    @property
    def label(self) -> str:
        return {
            0: "L0 Observe",
            1: "L1 Flag",
            2: "L2 Coordinate",
            3: "L3 Escalate",
            4: "L4 Critical",
            5: "L5 Captain",
        }[self.value]

    @property
    def requires_captain(self) -> bool:
        return self.value >= 5

    @property
    def requires_xo(self) -> bool:
        return self.value >= 4

    @property
    def days_before_advance(self) -> int:
        return _ADVANCE_AFTER_DAYS.get(self.value, 0)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class EscalationItem:
    esc_id: str
    officer: str
    item_type: str
    title: str
    level: EscalationLevel
    severity: str = "medium"      # low / medium / high / critical
    reason: str = ""
    escalated_at: datetime = field(default_factory=datetime.utcnow)
    resolve_by: datetime | None = None
    resolved: bool = False

    @property
    def is_overdue(self) -> bool:
        if self.resolved or self.resolve_by is None:
            return False
        return datetime.utcnow() > self.resolve_by

    @property
    def route_hint(self) -> str:
        if self.level.requires_captain:
            return "captain"
        if self.level.requires_xo:
            return "xo"
        if self.level >= EscalationLevel.L2_COORDINATE:
            return "number_one"
        return "officer"


@dataclass
class EscalationChain:
    current: EscalationItem
    history: list[EscalationItem] = field(default_factory=list)
    can_advance: bool = True
    next_level: EscalationLevel | None = None


# ── Rationale helpers ─────────────────────────────────────────────────────────

def _build_rationale(ei: EscalationItem) -> str:
    resolve_str = ei.resolve_by.isoformat() if ei.resolve_by else ""
    return (
        f"OFFICER: {ei.officer} | ITEM_TYPE: {ei.item_type} | "
        f"LEVEL: {ei.level.value} | ESCALATED_AT: {ei.escalated_at.isoformat()} | "
        f"RESOLVE_BY: {resolve_str} | REASON: {ei.reason[:80]}"
    )


def _row_to_escalation(row: dict[str, Any]) -> EscalationItem | None:
    try:
        owner = row.get("owner", "")
        esc_id = owner.replace(_ESC_OWNER_PREFIX, "", 1)
        rationale = row.get("rationale", "")
        title = row.get("statement", "")
        parts: dict[str, str] = {}
        for part in rationale.split("|"):
            part = part.strip()
            if ":" in part:
                k, v = part.split(":", 1)
                parts[k.strip()] = v.strip()

        def _dt(s: str) -> datetime | None:
            try:
                return datetime.fromisoformat(s) if s else None
            except ValueError:
                return None

        level = EscalationLevel(int(parts.get("LEVEL", "0")))
        resolved = row.get("status", "") == "resolved"
        return EscalationItem(
            esc_id=esc_id,
            officer=parts.get("OFFICER", ""),
            item_type=parts.get("ITEM_TYPE", ""),
            title=title,
            level=level,
            reason=parts.get("REASON", ""),
            escalated_at=_dt(parts.get("ESCALATED_AT", "")) or datetime.utcnow(),
            resolve_by=_dt(parts.get("RESOLVE_BY", "")),
            resolved=resolved,
        )
    except Exception:
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def create_escalation(
    officer: str,
    item_type: str,
    title: str,
    severity: str = "medium",
    reason: str = "",
    ctx: Any = None,
) -> EscalationItem:
    """Create a new escalation starting at L0 Observe."""
    esc_id = uuid.uuid4().hex[:12]
    level = EscalationLevel.L0_OBSERVE
    resolve_by = datetime.utcnow() + timedelta(days=level.days_before_advance) if level.days_before_advance else None
    ei = EscalationItem(
        esc_id=esc_id,
        officer=officer,
        item_type=item_type,
        title=title[:120],
        level=level,
        severity=severity,
        reason=reason,
        resolve_by=resolve_by,
    )
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if c.is_enabled() and c.raw_client:
            existing = (
                c.raw_client.table("decisions")
                .select("id")
                .ilike("statement", f"%{title[:40]}%")
                .ilike("owner", f"{_ESC_OWNER_PREFIX}%")
                .neq("status", "resolved")
                .limit(1)
                .execute()
            )
            if not list(existing.data or []):
                c.raw_client.table("decisions").insert({
                    "owner": f"{_ESC_OWNER_PREFIX}{esc_id}",
                    "statement": f"[OFFICER ESC] L{level.value} {officer}: {item_type}",
                    "rationale": _build_rationale(ei),
                    "decision_type": "officer_escalation",
                    "status": "active",
                }).execute()
        log.info("[officer_escalations] Created L0 escalation %s: %s/%s", esc_id, officer, item_type)
    except Exception as exc:
        log.debug("[officer_escalations] Create failed: %s", exc)
    return ei


def advance_escalation(esc_id: str) -> EscalationItem | None:
    """Advance an escalation to the next level. Returns updated item or None."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return None

        owner = f"{_ESC_OWNER_PREFIX}{esc_id}"
        res = c.raw_client.table("decisions").select("owner,statement,rationale,status").eq("owner", owner).limit(1).execute()
        rows = list(res.data or [])
        if not rows:
            return None

        ei = _row_to_escalation(rows[0])
        if not ei or ei.resolved or ei.level >= EscalationLevel.L5_CAPTAIN:
            return ei

        new_level = EscalationLevel(ei.level.value + 1)
        ei.level = new_level
        ei.escalated_at = datetime.utcnow()
        ei.resolve_by = (
            datetime.utcnow() + timedelta(days=new_level.days_before_advance)
            if new_level.days_before_advance else None
        )

        c.raw_client.table("decisions").update({
            "statement": f"[OFFICER ESC] L{new_level.value} {ei.officer}: {ei.item_type}",
            "rationale": _build_rationale(ei),
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("owner", owner).execute()

        log.info("[officer_escalations] Advanced %s to %s", esc_id, new_level.label)
        return ei
    except Exception as exc:
        log.debug("[officer_escalations] Advance failed %s: %s", esc_id, exc)
        return None


def resolve_escalation(esc_id: str) -> None:
    """Mark an escalation as resolved."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if c.is_enabled() and c.raw_client:
            owner = f"{_ESC_OWNER_PREFIX}{esc_id}"
            c.raw_client.table("decisions").update({"status": "resolved"}).eq("owner", owner).execute()
        log.info("[officer_escalations] Resolved %s", esc_id)
    except Exception as exc:
        log.debug("[officer_escalations] Resolve failed %s: %s", esc_id, exc)


def get_overdue_escalations() -> list[EscalationItem]:
    """Return all active escalations that have exceeded their age-out threshold."""
    overdue: list[EscalationItem] = []
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return []

        res = (
            c.raw_client.table("decisions")
            .select("owner,statement,rationale,status")
            .ilike("owner", f"{_ESC_OWNER_PREFIX}%")
            .eq("status", "active")
            .execute()
        )
        for row in res.data or []:
            ei = _row_to_escalation(row)
            if ei and ei.is_overdue and not ei.resolved:
                overdue.append(ei)
    except Exception as exc:
        log.debug("[officer_escalations] Get overdue failed: %s", exc)
    return overdue


def build_escalation_chain(esc_item: EscalationItem, ctx: Any = None) -> EscalationChain:
    """Build the escalation chain view for an item."""
    can_advance = (
        not esc_item.resolved
        and esc_item.level < EscalationLevel.L5_CAPTAIN
    )
    next_level = (
        EscalationLevel(esc_item.level.value + 1) if can_advance else None
    )
    return EscalationChain(current=esc_item, can_advance=can_advance, next_level=next_level)


__all__ = [
    "EscalationLevel",
    "EscalationItem",
    "EscalationChain",
    "create_escalation",
    "advance_escalation",
    "resolve_escalation",
    "get_overdue_escalations",
    "build_escalation_chain",
]
