"""Cross-Officer Handoff Framework (EXEC-010A WP8).

Officers hand off work to each other through defined channels. Handoffs are
typed (sequential, parallel, escalation, return) and tracked in the decisions
table. Standard handoff chains encode domain expertise routing.

Standard chains:
  Research → Knowledge → Engineering → QA  (investigation → knowledge → build → validate)
  Medical → Number One → XO               (health signal → coordination → governance)
  Engineering → QA → XO                  (build → validate → approve)
  Knowledge → Research                   (knowledge gap → research activation)

Storage: decisions table
  owner = `officer_handoff:{handoff_id}`
  statement = `[OFFICER HANDOFF] {from_officer} → {to_officer}: {item_type}`
  rationale = `FROM: | TO: | TYPE: | ITEM_COUNT: | STATUS: | CONTEXT:`

Public API:
    HandoffType
    HandoffStatus
    HandoffRecord
    STANDARD_HANDOFFS
    create_handoff(from_officer, to_officer, items, handoff_type, context) -> HandoffRecord
    accept_handoff(handoff_id, accepting_officer)                          -> bool
    complete_handoff(handoff_id)                                           -> bool
    get_pending_handoffs(officer)                                          -> list[HandoffRecord]
    process_handoffs(trigger_results, ctx)                                 -> list[HandoffRecord]
"""

from __future__ import annotations

import logging
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

_HANDOFF_OWNER_PREFIX = "officer_handoff:"


# ── Enums ─────────────────────────────────────────────────────────────────────

class HandoffType(str, Enum):
    SEQUENTIAL  = "sequential"    # A → B → C, one at a time
    PARALLEL    = "parallel"      # A → B and A → C simultaneously
    ESCALATION  = "escalation"    # officer → next authority level
    RETURN      = "return"        # B returns item to A after processing


class HandoffStatus(str, Enum):
    PENDING   = "pending"
    ACCEPTED  = "accepted"
    COMPLETED = "completed"
    REJECTED  = "rejected"


# ── Standard handoff chains ───────────────────────────────────────────────────

STANDARD_HANDOFFS: dict[str, list[str]] = {
    "investigation_chain":  ["research", "knowledge", "engineering", "qa"],
    "health_chain":         ["medical", "number_one", "xo"],
    "delivery_chain":       ["engineering", "qa", "xo"],
    "knowledge_gap_chain":  ["knowledge", "research"],
    "governance_chain":     ["qa", "number_one", "xo"],
    "capability_chain":     ["engineering", "number_one", "xo"],
}


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class HandoffRecord:
    handoff_id: str
    from_officer: str
    to_officer: str
    handoff_type: HandoffType
    items: list[dict[str, Any]] = field(default_factory=list)
    status: HandoffStatus = HandoffStatus.PENDING
    context: str = ""
    item_type: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    accepted_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def summary(self) -> str:
        return (
            f"{self.from_officer} → {self.to_officer} "
            f"[{self.handoff_type.value}] {len(self.items)} item(s) — {self.status.value}"
        )


# ── Rationale helpers ─────────────────────────────────────────────────────────

def _build_rationale(hr: HandoffRecord) -> str:
    return (
        f"FROM: {hr.from_officer} | TO: {hr.to_officer} | "
        f"TYPE: {hr.handoff_type.value} | ITEM_COUNT: {len(hr.items)} | "
        f"STATUS: {hr.status.value} | CONTEXT: {hr.context[:80]}"
    )


def _row_to_handoff(row: dict[str, Any]) -> HandoffRecord | None:
    try:
        owner = row.get("owner", "")
        handoff_id = owner.replace(_HANDOFF_OWNER_PREFIX, "", 1)
        rat = row.get("rationale", "")
        stmt = row.get("statement", "")
        parts: dict[str, str] = {}
        for part in rat.split("|"):
            part = part.strip()
            if ":" in part:
                k, v = part.split(":", 1)
                parts[k.strip()] = v.strip()

        def _en(cls: type, val: str, default: Any) -> Any:
            try:
                return cls(val)
            except (ValueError, KeyError):
                return default

        return HandoffRecord(
            handoff_id=handoff_id,
            from_officer=parts.get("FROM", ""),
            to_officer=parts.get("TO", ""),
            handoff_type=_en(HandoffType, parts.get("TYPE", ""), HandoffType.SEQUENTIAL),
            status=_en(HandoffStatus, parts.get("STATUS", ""), HandoffStatus.PENDING),
            context=parts.get("CONTEXT", ""),
            item_type=stmt,
        )
    except Exception:
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def create_handoff(
    from_officer: str,
    to_officer: str,
    items: list[dict[str, Any]],
    handoff_type: HandoffType = HandoffType.SEQUENTIAL,
    context: str = "",
    item_type: str = "",
) -> HandoffRecord:
    """Create a handoff record and persist to decisions table."""
    handoff_id = uuid.uuid4().hex[:12]
    hr = HandoffRecord(
        handoff_id=handoff_id,
        from_officer=from_officer,
        to_officer=to_officer,
        handoff_type=handoff_type,
        items=items,
        context=context,
        item_type=item_type or f"{from_officer}_output",
    )
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if c.is_enabled() and c.raw_client:
            owner = f"{_HANDOFF_OWNER_PREFIX}{handoff_id}"
            existing = (
                c.raw_client.table("decisions")
                .select("id")
                .ilike("rationale", f"%FROM: {from_officer}%TO: {to_officer}%")
                .ilike("owner", f"{_HANDOFF_OWNER_PREFIX}%")
                .eq("status", "active")
                .limit(1)
                .execute()
            )
            if not list(existing.data or []):
                c.raw_client.table("decisions").insert({
                    "owner": owner,
                    "statement": f"[OFFICER HANDOFF] {from_officer} → {to_officer}: {hr.item_type[:60]}",
                    "rationale": _build_rationale(hr),
                    "decision_type": "officer_handoff",
                    "status": "active",
                }).execute()
        log.info("[officer_handoffs] Created handoff %s: %s → %s (%d items)",
                 handoff_id, from_officer, to_officer, len(items))
    except Exception as exc:
        log.debug("[officer_handoffs] Create failed: %s", exc)
    return hr


def accept_handoff(handoff_id: str, accepting_officer: str) -> bool:
    """Mark a handoff as accepted by the receiving officer."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return False

        owner = f"{_HANDOFF_OWNER_PREFIX}{handoff_id}"
        res = c.raw_client.table("decisions").select("rationale").eq("owner", owner).limit(1).execute()
        rows = list(res.data or [])
        if not rows:
            return False

        rat = rows[0].get("rationale", "")
        new_rat = rat.replace(f"STATUS: {HandoffStatus.PENDING.value}", f"STATUS: {HandoffStatus.ACCEPTED.value}")
        c.raw_client.table("decisions").update({
            "rationale": new_rat,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("owner", owner).execute()
        log.info("[officer_handoffs] Accepted %s by %s", handoff_id, accepting_officer)
        return True
    except Exception as exc:
        log.debug("[officer_handoffs] Accept failed %s: %s", handoff_id, exc)
        return False


def complete_handoff(handoff_id: str) -> bool:
    """Mark a handoff as completed (receiving officer has actioned it)."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return False

        owner = f"{_HANDOFF_OWNER_PREFIX}{handoff_id}"
        c.raw_client.table("decisions").update({
            "status": "resolved",
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("owner", owner).execute()
        log.info("[officer_handoffs] Completed %s", handoff_id)
        return True
    except Exception as exc:
        log.debug("[officer_handoffs] Complete failed %s: %s", handoff_id, exc)
        return False


def get_pending_handoffs(officer: str) -> list[HandoffRecord]:
    """Return handoffs pending acceptance by a specific officer."""
    result: list[HandoffRecord] = []
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return []

        res = (
            c.raw_client.table("decisions")
            .select("owner,statement,rationale,status")
            .ilike("owner", f"{_HANDOFF_OWNER_PREFIX}%")
            .ilike("rationale", f"%TO: {officer}%")
            .ilike("rationale", f"%STATUS: {HandoffStatus.PENDING.value}%")
            .eq("status", "active")
            .execute()
        )
        for row in res.data or []:
            hr = _row_to_handoff(row)
            if hr:
                result.append(hr)
    except Exception as exc:
        log.debug("[officer_handoffs] Get pending failed %s: %s", officer, exc)
    return result


def process_handoffs(
    trigger_results: dict[str, list[Any]],
    ctx: Any = None,
) -> list[HandoffRecord]:
    """Create handoffs from fired trigger results based on STANDARD_HANDOFFS chains.

    Research triggers → forward to Knowledge.
    Medical triggers → forward to Number One if high severity.
    Engineering triggers → forward to QA after action.
    """
    created: list[HandoffRecord] = []
    if not trigger_results:
        return created

    # Research → Knowledge handoffs for investigation outputs
    research_fired = trigger_results.get("research", [])
    if research_fired:
        items = [{"trigger_id": tr.trigger_id, "title": tr.action_title} for tr in research_fired]
        hr = create_handoff(
            from_officer="research",
            to_officer="knowledge",
            items=items,
            handoff_type=HandoffType.SEQUENTIAL,
            context="Research triggers fired — knowledge capture required",
            item_type="investigation",
        )
        created.append(hr)

    # Medical → Number One handoffs for capacity signals
    medical_fired = trigger_results.get("medical", [])
    if medical_fired:
        items = [{"trigger_id": tr.trigger_id, "title": tr.action_title} for tr in medical_fired]
        hr = create_handoff(
            from_officer="medical",
            to_officer="number_one",
            items=items,
            handoff_type=HandoffType.ESCALATION,
            context="Capacity signal — Number One PMO coordination required",
            item_type="capacity",
        )
        created.append(hr)

    # Engineering → QA handoffs for technical reviews
    engineering_fired = [tr for tr in trigger_results.get("engineering", [])
                         if tr.action_type in ("technical_debt_review", "capability_improvement")]
    if engineering_fired:
        items = [{"trigger_id": tr.trigger_id, "title": tr.action_title} for tr in engineering_fired]
        hr = create_handoff(
            from_officer="engineering",
            to_officer="qa",
            items=items,
            handoff_type=HandoffType.SEQUENTIAL,
            context="Engineering assessment outputs — QA validation gate",
            item_type="technical",
        )
        created.append(hr)

    log.info("[officer_handoffs] %d handoff(s) created from %d officers", len(created), len(trigger_results))
    return created


__all__ = [
    "HandoffType",
    "HandoffStatus",
    "HandoffRecord",
    "STANDARD_HANDOFFS",
    "create_handoff",
    "accept_handoff",
    "complete_handoff",
    "get_pending_handoffs",
    "process_handoffs",
]
