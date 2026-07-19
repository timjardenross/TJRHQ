"""Officer Investigation Authority (EXEC-004 WP3).

Officers independently initiate investigations when they observe conditions
that warrant deeper examination. This is separate from improvement discovery
(D-057/D-058) — investigations explore questions, not just identify actions.

Principle: questions are not missions. Officers ask questions before acting.

Investigation triggers (per officer):
  Human Systems  — persistent capacity constraint, unexplained health pattern
  ORI            — elevated resilience risk, anomalous intelligence brief
  Number One     — escalation accumulation, mission coordination breakdown
  Engineering    — recurring technical blockers, delivery pattern anomaly
  Strategic      — orphan mission accumulation, strategic alignment drift
  Communications — publication pipeline stall, content decay pattern
  Knowledge      — knowledge gap accumulation, institutional memory erosion

Public API:
    investigate_human_systems(ctx)     -> list[str]  (inv_ids opened)
    investigate_ori(ctx)               -> list[str]
    investigate_number_one(ctx)        -> list[str]
    investigate_engineering(ctx)       -> list[str]
    investigate_strategic_planning(ctx)-> list[str]
    investigate_communications(ctx)    -> list[str]
    investigate_knowledge(ctx)         -> list[str]
    run_all_investigation_triggers(ctx)-> list[str]
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.investigation.framework import InvestigationType
from lib.investigation.registry import open_investigation


# ── Thresholds ────────────────────────────────────────────────────────────────

_BLOCKED_THRESHOLD     = 2   # missions blocked before Engineering investigates
_ORPHAN_THRESHOLD      = 3   # orphan count before Strategic investigates
_COMMS_STALL_THRESHOLD = 4   # comms ready count before Comms investigates
_N1_ESCALATION_THRESHOLD = 4  # escalation items before Number One investigates


# ── Per-officer triggers ──────────────────────────────────────────────────────

def investigate_human_systems(ctx: Any) -> list[str]:
    """Open investigation if persistent capacity constraint is detected."""
    opened: list[str] = []
    try:
        capacity = getattr(ctx, "capacity_status", "Unknown")
        blocked  = getattr(ctx, "engineering_blocked", 0)

        if capacity == "Red":
            inv_id = open_investigation(
                question="What is causing Red capacity status and how can it be resolved?",
                investigation_type=InvestigationType.HEALTH,
                source="human_systems_officer:auto_trigger",
                officer="human_systems",
                context=f"Capacity: {capacity} | Engineering blocked: {blocked}",
            )
            if inv_id:
                opened.append(inv_id)
                log.info("[investigation.officers] human_systems opened: %s (Red capacity)", inv_id)

        elif capacity == "Amber" and blocked >= _BLOCKED_THRESHOLD:
            inv_id = open_investigation(
                question="Why is capacity Amber while engineering has concurrent blockers — is there a compound constraint?",
                investigation_type=InvestigationType.OPERATIONAL,
                source="human_systems_officer:auto_trigger",
                officer="human_systems",
                context=f"Capacity: Amber | Blocked: {blocked}",
            )
            if inv_id:
                opened.append(inv_id)
                log.info("[investigation.officers] human_systems opened: %s (Amber+blocked)", inv_id)

    except Exception as exc:
        log.warning("[investigation.officers] human_systems trigger failed: %s", exc)
    return opened


def investigate_ori(ctx: Any) -> list[str]:
    """Open investigation if elevated resilience risk is detected."""
    opened: list[str] = []
    try:
        risk    = getattr(ctx, "resilience_risk", "Unknown")
        summary = getattr(ctx, "resilience_summary", "") or ""
        available = getattr(ctx, "resilience_available", False)

        if not available:
            return opened

        if risk == "RED":
            inv_id = open_investigation(
                question=f"What is driving RED resilience risk? Bottom line: {summary[:120]}",
                investigation_type=InvestigationType.RESILIENCE,
                source="ori_officer:auto_trigger",
                officer="ori",
                context=f"ORI risk: {risk}",
            )
            if inv_id:
                opened.append(inv_id)
                log.info("[investigation.officers] ori opened: %s (RED risk)", inv_id)

        elif risk == "AMBER":
            inv_id = open_investigation(
                question="What patterns are driving AMBER resilience status — is this trending toward RED?",
                investigation_type=InvestigationType.RESILIENCE,
                source="ori_officer:auto_trigger",
                officer="ori",
                context=f"ORI risk: AMBER | {summary[:100]}",
            )
            if inv_id:
                opened.append(inv_id)
                log.info("[investigation.officers] ori opened: %s (AMBER risk)", inv_id)

    except Exception as exc:
        log.warning("[investigation.officers] ori trigger failed: %s", exc)
    return opened


def investigate_number_one(ctx: Any) -> list[str]:
    """Open investigation if mission coordination shows breakdown signals."""
    opened: list[str] = []
    try:
        n1_items = getattr(ctx, "number_one_items", []) or []
        blocked  = getattr(ctx, "engineering_blocked", 0)
        capacity = getattr(ctx, "capacity_status", "Unknown")

        escalation_count = len([
            i for i in n1_items
            if str(i.get("type", "")).lower() in ("stale_mission", "routine_escalation")
        ])

        if escalation_count >= _N1_ESCALATION_THRESHOLD:
            inv_id = open_investigation(
                question=f"Why are {escalation_count} missions simultaneously escalating to Number One — is there a systemic coordination issue?",
                investigation_type=InvestigationType.OPERATIONAL,
                source="number_one_officer:auto_trigger",
                officer="number_one",
                context=f"Escalations: {escalation_count} | Blocked: {blocked} | Capacity: {capacity}",
            )
            if inv_id:
                opened.append(inv_id)
                log.info("[investigation.officers] number_one opened: %s (escalation buildup)", inv_id)

    except Exception as exc:
        log.warning("[investigation.officers] number_one trigger failed: %s", exc)
    return opened


def investigate_engineering(ctx: Any) -> list[str]:
    """Open investigation if engineering blockage pattern exceeds threshold."""
    opened: list[str] = []
    try:
        blocked = getattr(ctx, "engineering_blocked", 0)
        in_progress = getattr(ctx, "engineering_in_progress", 0)

        if blocked >= _BLOCKED_THRESHOLD:
            blocked_pct = round(blocked / max(blocked + in_progress, 1) * 100)
            inv_id = open_investigation(
                question=f"Why are {blocked} missions blocked ({blocked_pct}% of active work) — is there a recurring technical blocker?",
                investigation_type=InvestigationType.TECHNICAL,
                source="engineering_officer:auto_trigger",
                officer="engineering",
                context=f"Blocked: {blocked} | In progress: {in_progress}",
            )
            if inv_id:
                opened.append(inv_id)
                log.info("[investigation.officers] engineering opened: %s (%d blocked)", inv_id, blocked)

    except Exception as exc:
        log.warning("[investigation.officers] engineering trigger failed: %s", exc)
    return opened


def investigate_strategic_planning(ctx: Any) -> list[str]:
    """Open investigation if orphan missions accumulate above threshold."""
    opened: list[str] = []
    try:
        orphan_count = getattr(ctx, "orphan_count", 0)

        if orphan_count >= _ORPHAN_THRESHOLD:
            inv_id = open_investigation(
                question=f"Why are {orphan_count} missions not mapped to strategic objectives — is there a strategic alignment gap?",
                investigation_type=InvestigationType.STRATEGIC,
                source="strategic_planning_officer:auto_trigger",
                officer="strategic_planning",
                context=f"Orphan missions: {orphan_count}",
            )
            if inv_id:
                opened.append(inv_id)
                log.info("[investigation.officers] strategic_planning opened: %s (%d orphans)", inv_id, orphan_count)

    except Exception as exc:
        log.warning("[investigation.officers] strategic_planning trigger failed: %s", exc)
    return opened


def investigate_communications(ctx: Any) -> list[str]:
    """Open investigation if publication pipeline has stalled items."""
    opened: list[str] = []
    try:
        comms_ready = getattr(ctx, "comms_ready_count", 0)

        if comms_ready >= _COMMS_STALL_THRESHOLD:
            inv_id = open_investigation(
                question=f"Why are {comms_ready} communications items awaiting publication — is there a pipeline bottleneck or approval delay?",
                investigation_type=InvestigationType.COMMUNICATIONS,
                source="communications_officer:auto_trigger",
                officer="communications",
                context=f"Ready to publish: {comms_ready}",
            )
            if inv_id:
                opened.append(inv_id)
                log.info("[investigation.officers] communications opened: %s (%d ready)", inv_id, comms_ready)

    except Exception as exc:
        log.warning("[investigation.officers] communications trigger failed: %s", exc)
    return opened


def investigate_knowledge(ctx: Any) -> list[str]:
    """Open investigation if knowledge gaps are accumulating without closure."""
    opened: list[str] = []
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return opened

        # Count open knowledge gap decisions
        res = (
            c.raw_client.table("decisions")
            .select("id", count="exact")
            .ilike("statement", "%knowledge gap%")
            .not_.ilike("owner", "investigation%")
            .limit(1)
            .execute()
        )
        gap_count = int(getattr(res, "count", None) or 0)

        if gap_count >= 3:
            inv_id = open_investigation(
                question=f"Why are {gap_count} knowledge gaps open without closure — is institutional memory eroding?",
                investigation_type=InvestigationType.KNOWLEDGE,
                source="knowledge_officer:auto_trigger",
                officer="knowledge",
                context=f"Open knowledge gaps: {gap_count}",
            )
            if inv_id:
                opened.append(inv_id)
                log.info("[investigation.officers] knowledge opened: %s (%d gaps)", inv_id, gap_count)

    except Exception as exc:
        log.warning("[investigation.officers] knowledge trigger failed: %s", exc)
    return opened


def run_all_investigation_triggers(ctx: Any) -> list[str]:
    """Run all officer investigation triggers and return IDs of newly opened investigations.

    Each trigger is non-blocking. Failures in one officer don't affect others.
    Deduplication is handled inside open_investigation() — the same officer+type
    won't open a new investigation if one is already open.
    """
    all_opened: list[str] = []

    # Daily triggers
    for trigger_fn in [
        investigate_human_systems,
        investigate_ori,
        investigate_number_one,
    ]:
        try:
            opened = trigger_fn(ctx)
            all_opened.extend(opened)
        except Exception as exc:
            log.warning("[investigation.officers] Trigger %s failed: %s", trigger_fn.__name__, exc)

    # Domain triggers (run less frequently in practice but checked every cycle)
    for trigger_fn in [
        investigate_engineering,
        investigate_strategic_planning,
        investigate_communications,
        investigate_knowledge,
    ]:
        try:
            opened = trigger_fn(ctx)
            all_opened.extend(opened)
        except Exception as exc:
            log.warning("[investigation.officers] Trigger %s failed: %s", trigger_fn.__name__, exc)

    if all_opened:
        log.info(
            "[investigation.officers] %d new investigation(s) opened: %s",
            len(all_opened), ", ".join(all_opened),
        )
    return all_opened


__all__ = [
    "investigate_human_systems",
    "investigate_ori",
    "investigate_number_one",
    "investigate_engineering",
    "investigate_strategic_planning",
    "investigate_communications",
    "investigate_knowledge",
    "run_all_investigation_triggers",
]
