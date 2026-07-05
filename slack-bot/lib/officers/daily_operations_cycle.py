"""Autonomous Officer Daily Operations Cycle (EXEC-010A WP9).

Officers run an 8-step autonomous cycle each day. This is the officer-layer
cycle — it runs INSIDE the executive daily cycle (daily_ops_cycle.py step 7.2)
after all data is fresh. Officers consume the CycleContext produced by the
executive cycle rather than gathering data independently.

8-Step Officer Autonomous Cycle:
  Step 1. Research Scan          — Research Officer processes intelligence signals
  Step 2. Knowledge Capture      — Knowledge Officer advances lifecycle records
  Step 3. Operational Review     — Number One sweeps mission assignments & blockers
  Step 4. Readiness Assessment   — Medical Officer assesses capacity health
  Step 5. Engineering Assessment — Chief Engineer scans delivery & tech signals
  Step 6. Assignment Resolution  — Number One makes / validates mission assignments
  Step 7. Escalation Processing  — All officers advance overdue escalations
  Step 8. XO Synthesis           — XO synthesises officer outputs for brief injection

Principle: Officers act, then report. The executive cycle receives officer outputs
as structured signals, not raw data dumps.

Public API:
    OfficerCycleResult
    run_officer_cycle(ctx, missions)          -> OfficerCycleResult
    format_officer_cycle_summary(result)      -> str
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ── Output data class ─────────────────────────────────────────────────────────

@dataclass
class OfficerCycleResult:
    """Structured output from the officer autonomous cycle."""
    # Trigger outcomes
    triggers_fired: int = 0
    triggered_officers: list[str] = field(default_factory=list)

    # Action outcomes
    actions_created: int = 0
    actions_requiring_approval: int = 0
    autonomous_actions: int = 0

    # Handoff outcomes
    handoffs_created: int = 0

    # Follow-up / escalation outcomes
    overdue_followups: int = 0
    escalations_advanced: int = 0
    escalations_to_captain: int = 0

    # Assignment outcomes
    idle_missions: int = 0
    assignments_made: int = 0

    # Schedule outcomes
    due_activities: int = 0
    activities_run: int = 0

    # Synthesis
    xo_synthesis_available: bool = False
    cycle_summary: str = ""
    officer_signals: list[dict[str, Any]] = field(default_factory=list)
    cycle_ran_at: datetime = field(default_factory=datetime.utcnow)


# ── Step 1: Research Scan ─────────────────────────────────────────────────────

def _step_research_scan(ctx: Any, result: OfficerCycleResult) -> None:
    """Research Officer: process intelligence signals from ORI and investigations."""
    try:
        from core.platform.unified_memory import MemoryType, recall
        results = recall(MemoryType.OFFICER_CONTEXT, officer="research")
        oc = results[0] if results else {"has_context": False, "relevant_memories": []}
        if not oc["has_context"] and not getattr(ctx, "high_confidence_findings", []):
            return

        findings = getattr(ctx, "high_confidence_findings", [])
        ori_risk = getattr(ctx, "resilience_risk", "Unknown")
        if findings or ori_risk in ("RED", "AMBER"):
            signal = {
                "officer": "research",
                "type": "intelligence_scan",
                "findings": len(findings),
                "ori_risk": ori_risk,
                "context_memories": len(oc["relevant_memories"]),
            }
            result.officer_signals.append(signal)
            log.info("[officer_cycle] Research scan: %d finding(s), ORI=%s", len(findings), ori_risk)
    except Exception as exc:
        log.debug("[officer_cycle] Research scan failed: %s", exc)


# ── Step 2: Knowledge Capture ─────────────────────────────────────────────────

def _step_knowledge_capture(ctx: Any, result: OfficerCycleResult) -> None:
    """Knowledge Officer: advance lesson lifecycle records, capture patterns."""
    try:
        lesson_candidates = getattr(ctx, "lesson_candidates_pending", 0)
        lessons_generated = getattr(ctx, "lessons_generated_this_cycle", 0)
        patterns = getattr(ctx, "patterns_detected", [])

        if lesson_candidates > 0 or patterns:
            signal = {
                "officer": "knowledge",
                "type": "knowledge_capture",
                "lesson_candidates": lesson_candidates,
                "lessons_generated": lessons_generated,
                "patterns": len(patterns),
            }
            result.officer_signals.append(signal)
            log.info("[officer_cycle] Knowledge capture: %d candidates, %d patterns",
                     lesson_candidates, len(patterns))
    except Exception as exc:
        log.debug("[officer_cycle] Knowledge capture failed: %s", exc)


# ── Step 3: Operational Review ────────────────────────────────────────────────

def _step_operational_review(ctx: Any, missions: list[dict[str, Any]], result: OfficerCycleResult) -> None:
    """Number One: sweep mission assignments and coordination blockers."""
    try:
        from lib.officers.officer_followups import detect_idle_missions

        idle = detect_idle_missions(missions)
        result.idle_missions = len(idle)
        blocked = getattr(ctx, "blocked_initiatives_count", 0)
        delivery_risks = getattr(ctx, "delivery_risks_count", 0)

        if idle or blocked or delivery_risks:
            signal = {
                "officer": "number_one",
                "type": "operational_review",
                "idle_missions": len(idle),
                "blocked_initiatives": blocked,
                "delivery_risks": delivery_risks,
            }
            result.officer_signals.append(signal)
            log.info("[officer_cycle] Operational review: idle=%d, blocked=%d, risks=%d",
                     len(idle), blocked, delivery_risks)
    except Exception as exc:
        log.debug("[officer_cycle] Operational review failed: %s", exc)


# ── Step 4: Readiness Assessment ─────────────────────────────────────────────

def _step_readiness_assessment(ctx: Any, result: OfficerCycleResult) -> None:
    """Medical Officer: assess capacity health and surface recovery needs."""
    try:
        capacity_status = getattr(ctx, "capacity_status", "Unknown")
        capacity_score = getattr(ctx, "capacity_score", None)
        actions = getattr(ctx, "capacity_actions", [])

        signal = {
            "officer": "medical",
            "type": "readiness_assessment",
            "capacity_status": capacity_status,
            "capacity_score": capacity_score,
            "gate_actions": len(actions),
        }
        result.officer_signals.append(signal)
        log.info("[officer_cycle] Readiness: status=%s, score=%s, actions=%d",
                 capacity_status, capacity_score, len(actions))
    except Exception as exc:
        log.debug("[officer_cycle] Readiness assessment failed: %s", exc)


# ── Step 5: Engineering Assessment ───────────────────────────────────────────

def _step_engineering_assessment(ctx: Any, result: OfficerCycleResult) -> None:
    """Chief Engineer: assess delivery status, tech debt, and capability gaps."""
    try:
        blocked = getattr(ctx, "engineering_blocked", 0)
        in_progress = getattr(ctx, "engineering_in_progress", 0)
        tech_debt = getattr(ctx, "tech_debt_critical_count", 0)
        cap_gaps = getattr(ctx, "capability_gap_count", 0)

        signal = {
            "officer": "engineering",
            "type": "engineering_assessment",
            "blocked": blocked,
            "in_progress": in_progress,
            "critical_tech_debt": tech_debt,
            "capability_gaps": cap_gaps,
        }
        result.officer_signals.append(signal)
        log.info("[officer_cycle] Engineering: blocked=%d, in_progress=%d, debt=%d, gaps=%d",
                 blocked, in_progress, tech_debt, cap_gaps)
    except Exception as exc:
        log.debug("[officer_cycle] Engineering assessment failed: %s", exc)


# ── Step 6: Assignment Resolution ────────────────────────────────────────────

def _step_assignment_resolution(ctx: Any, missions: list[dict[str, Any]], result: OfficerCycleResult) -> None:
    """Number One: process idle missions that require assignment or re-assignment."""
    try:
        from lib.officers.officer_assignment import assign_mission, get_available_assignees

        assigned = 0
        for m in missions[:5]:  # cap to 5 per cycle to bound latency
            status = str(m.get("status") or "").lower()
            owner = m.get("owner") or m.get("assigned_to") or ""
            if status in ("open", "proposed") and not owner:
                candidates = get_available_assignees(m.get("type", ""))
                if candidates:
                    target = candidates[0]
                    assign_mission(
                        mission_id=m.get("id") or m.get("mission_id", "unknown"),
                        mission_title=m.get("title", ""),
                        target_officer=target,
                        assigning_officer="number_one",
                        rationale="Auto-assigned by Number One (unassigned mission detected)",
                        mission_type=m.get("type", ""),
                    )
                    assigned += 1

        result.assignments_made = assigned
        if assigned:
            log.info("[officer_cycle] Assignment resolution: %d mission(s) assigned", assigned)
    except Exception as exc:
        log.debug("[officer_cycle] Assignment resolution failed: %s", exc)


# ── Step 7: Escalation Processing ────────────────────────────────────────────

def _step_escalation_processing(ctx: Any, result: OfficerCycleResult) -> None:
    """All officers: advance overdue escalations and surface L5 items to Captain."""
    try:
        from lib.officers.officer_escalations import get_overdue_escalations, advance_escalation, EscalationLevel

        overdue = get_overdue_escalations()
        result.overdue_followups = len(overdue)
        advanced = 0
        captain_items = 0

        for esc in overdue[:10]:  # cap to 10 per cycle
            updated = advance_escalation(esc.esc_id)
            if updated:
                advanced += 1
                if updated.level == EscalationLevel.L5_CAPTAIN:
                    captain_items += 1
                    ctx.all_items.append({
                        "type": "governance_exception",
                        "title": f"[L5 ESCALATION] {esc.officer}: {esc.title[:70]}",
                        "source": f"officer_escalation:{esc.officer}",
                        "priority": "P1",
                    })

        result.escalations_advanced = advanced
        result.escalations_to_captain = captain_items

        if advanced:
            log.info("[officer_cycle] Escalation processing: %d advanced, %d to Captain",
                     advanced, captain_items)
    except Exception as exc:
        log.debug("[officer_cycle] Escalation processing failed: %s", exc)


# ── Step 8: XO Synthesis ─────────────────────────────────────────────────────

def _step_xo_synthesis(ctx: Any, result: OfficerCycleResult) -> None:
    """XO: synthesise all officer signals for injection into the Captain brief."""
    try:
        from lib.officers.xo_orchestrator import synthesise_officer_outputs, format_xo_synthesis
        synthesis = synthesise_officer_outputs(result.officer_signals, ctx)
        summary = format_xo_synthesis(synthesis)
        result.xo_synthesis_available = bool(summary)
        result.cycle_summary = summary
        log.info("[officer_cycle] XO synthesis complete: risk_level=%s", synthesis.risk_level)
    except Exception as exc:
        log.debug("[officer_cycle] XO synthesis failed: %s", exc)
        if result.officer_signals:
            result.cycle_summary = _format_fallback_summary(result)


def _format_fallback_summary(result: OfficerCycleResult) -> str:
    """Minimal fallback summary when XO orchestrator unavailable."""
    parts = []
    for sig in result.officer_signals:
        officer = sig.get("officer", "?")
        sig_type = sig.get("type", "?")
        parts.append(f"• {officer}: {sig_type}")
    return "*Officer Cycle (fallback):*\n" + "\n".join(parts) if parts else ""


# ── Trigger + action evaluation ───────────────────────────────────────────────

def _evaluate_triggers_and_act(ctx: Any, result: OfficerCycleResult) -> None:
    """Evaluate all officer triggers and convert fired triggers to actions."""
    try:
        from lib.officers.officer_triggers import evaluate_all_triggers
        from lib.officers.officer_actions import execute_triggered_actions
        from lib.officers.officer_handoffs import process_handoffs

        trigger_results = evaluate_all_triggers(ctx)
        result.triggers_fired = sum(len(v) for v in trigger_results.values())
        result.triggered_officers = list(trigger_results.keys())

        # Convert to actions
        actions = execute_triggered_actions(trigger_results, ctx)
        result.actions_created = len(actions)
        result.autonomous_actions = sum(1 for a in actions if not a.requires_approval)
        result.actions_requiring_approval = sum(1 for a in actions if a.requires_approval)

        # Surface approval-required items to exception router
        for action in actions:
            if action.requires_approval:
                ctx.all_items.append({
                    "type": "officer_action_required",
                    "title": f"[OFFICER ACTION] {action.officer}: {action.title[:70]}",
                    "source": f"officer:{action.officer}",
                    "priority": "P2",
                })

        # Process cross-officer handoffs
        handoffs = process_handoffs(trigger_results, ctx)
        result.handoffs_created = len(handoffs)

    except Exception as exc:
        log.debug("[officer_cycle] Trigger evaluation failed: %s", exc)


# ── Scheduled activities check ────────────────────────────────────────────────

def _run_due_scheduled_activities(ctx: Any, result: OfficerCycleResult) -> None:
    """Check for due scheduled activities and record them as run."""
    try:
        from lib.officers.officer_schedules import get_due_activities, record_activity_run

        due = get_due_activities(ctx)
        result.due_activities = len(due)

        for activity in due[:5]:  # cap per cycle
            try:
                record_activity_run(activity.schedule.activity_id)
                result.activities_run += 1
            except Exception as exc:
                log.debug("[officer_cycle] Activity run record failed %s: %s",
                          activity.schedule.activity_id, exc)

        if due:
            log.info("[officer_cycle] %d/%d scheduled activities run", result.activities_run, len(due))
    except Exception as exc:
        log.debug("[officer_cycle] Scheduled activities check failed: %s", exc)


# ── Main entry point ──────────────────────────────────────────────────────────

def run_officer_cycle(
    ctx: Any,
    missions: list[dict[str, Any]] | None = None,
) -> OfficerCycleResult:
    """Run the full 8-step officer autonomous cycle.

    Consumes the CycleContext from the executive cycle. Non-blocking: each step
    degrades gracefully if data is unavailable. All officer actions are recorded
    in the decisions table for transparency.

    Args:
        ctx:      CycleContext from run_daily_cycle (all officer data populated)
        missions: Active missions list (same as passed to run_daily_cycle)
    """
    missions = missions or []
    result = OfficerCycleResult()

    # Trigger + action evaluation (cross-step, feeds all steps)
    _evaluate_triggers_and_act(ctx, result)

    # 8-step cycle
    _step_research_scan(ctx, result)                           # Step 1
    _step_knowledge_capture(ctx, result)                       # Step 2
    _step_operational_review(ctx, missions, result)            # Step 3
    _step_readiness_assessment(ctx, result)                    # Step 4
    _step_engineering_assessment(ctx, result)                  # Step 5
    _step_assignment_resolution(ctx, missions, result)         # Step 6
    _step_escalation_processing(ctx, result)                   # Step 7
    _step_xo_synthesis(ctx, result)                            # Step 8

    # Scheduled activities
    _run_due_scheduled_activities(ctx, result)

    log.info(
        "[officer_cycle] Complete: triggers=%d, actions=%d (autonomous=%d, approval=%d), "
        "handoffs=%d, escalations_advanced=%d, assignments=%d",
        result.triggers_fired, result.actions_created,
        result.autonomous_actions, result.actions_requiring_approval,
        result.handoffs_created, result.escalations_advanced, result.assignments_made,
    )
    return result


def format_officer_cycle_summary(result: OfficerCycleResult) -> str:
    """Format a concise officer cycle summary for the Captain brief."""
    if result.cycle_summary:
        return result.cycle_summary

    if not result.officer_signals and result.triggers_fired == 0:
        return ""

    lines = ["*Officer Autonomous Cycle:*"]
    if result.triggers_fired:
        lines.append(f"  Triggers fired: {result.triggers_fired} across {len(result.triggered_officers)} officer(s)")
    if result.actions_created:
        parts = []
        if result.autonomous_actions:
            parts.append(f"{result.autonomous_actions} autonomous")
        if result.actions_requiring_approval:
            parts.append(f"{result.actions_requiring_approval} pending approval")
        lines.append(f"  Actions: {result.actions_created} ({', '.join(parts)})")
    if result.handoffs_created:
        lines.append(f"  Handoffs: {result.handoffs_created}")
    if result.escalations_advanced:
        esc_str = f"{result.escalations_advanced} advanced"
        if result.escalations_to_captain:
            esc_str += f", {result.escalations_to_captain} to Captain"
        lines.append(f"  Escalations: {esc_str}")
    if result.idle_missions:
        lines.append(f"  Idle missions: {result.idle_missions}")
    if result.assignments_made:
        lines.append(f"  Assignments made: {result.assignments_made}")
    return "\n".join(lines)


__all__ = [
    "OfficerCycleResult",
    "run_officer_cycle",
    "format_officer_cycle_summary",
]
