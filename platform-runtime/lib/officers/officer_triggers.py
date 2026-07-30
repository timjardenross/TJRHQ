"""Officer Trigger Framework (EXEC-010A WP1).

Provides a standard mechanism for officers to determine when to act.
Officers evaluate triggers each cycle; fired triggers produce action items
that flow through the autonomous cycle.

Trigger types:
  SCHEDULED        — time-based (daily / weekly / monthly)
  EVENT_DRIVEN     — a specific event in cycle context (e.g. Red capacity)
  THRESHOLD_BASED  — numeric metric crosses a bound
  LIFECYCLE_BASED  — entity transitions state (mission, benefit, initiative)
  ESCALATION_BASED — prior escalation ages out without resolution

Storage: decisions table, owner prefix `officer_trigger:{officer}:{trigger_id}`

Public API:
    TriggerType
    TriggerResult
    OfficerTrigger
    evaluate_trigger(trigger, ctx)  -> TriggerResult
    evaluate_all_triggers(ctx)      -> dict[str, list[TriggerResult]]
    OFFICER_TRIGGERS
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ── Enums ─────────────────────────────────────────────────────────────────────

class TriggerType(str, Enum):
    SCHEDULED        = "scheduled"
    EVENT_DRIVEN     = "event_driven"
    THRESHOLD_BASED  = "threshold_based"
    LIFECYCLE_BASED  = "lifecycle_based"
    ESCALATION_BASED = "escalation_based"


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class TriggerResult:
    fired: bool
    trigger_id: str
    officer: str
    trigger_type: TriggerType
    reason: str = ""
    action_type: str = ""          # maps to ActionCategory value in officer_actions
    action_title: str = ""
    action_context: dict[str, Any] = field(default_factory=dict)
    evaluated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class OfficerTrigger:
    trigger_id: str
    officer: str
    trigger_type: TriggerType
    description: str
    action_type: str
    condition: Callable[[Any], bool]   # (ctx) -> bool
    title_fn: Callable[[Any], str]     # (ctx) -> action title string
    context_fn: Callable[[Any], dict] = field(default_factory=lambda: lambda ctx: {})


# ── Trigger condition helpers ─────────────────────────────────────────────────

def _ctx(ctx: Any, attr: str, default: Any = None) -> Any:
    return getattr(ctx, attr, default)


# ── Trigger catalogue ─────────────────────────────────────────────────────────

OFFICER_TRIGGERS: dict[str, list[OfficerTrigger]] = {

    # ── Medical Officer (Human Systems) ───────────────────────────────────────
    "medical": [
        OfficerTrigger(
            trigger_id="med_red_capacity",
            officer="medical",
            trigger_type=TriggerType.EVENT_DRIVEN,
            description="Capacity at Red — initiate recovery assessment",
            action_type="review",
            condition=lambda ctx: _ctx(ctx, "capacity_status") == "Red",
            title_fn=lambda ctx: "Capacity Recovery Assessment — Red status requires medical officer intervention",
        ),
        OfficerTrigger(
            trigger_id="med_amber_persistent",
            officer="medical",
            trigger_type=TriggerType.THRESHOLD_BASED,
            description="Capacity Amber with ≥3 gate actions — compound constraint signal",
            action_type="investigation",
            condition=lambda ctx: (
                _ctx(ctx, "capacity_status") == "Amber"
                and len(_ctx(ctx, "capacity_actions", [])) >= 3
            ),
            title_fn=lambda ctx: f"Capacity constraint pattern investigation — {len(_ctx(ctx, 'capacity_actions', []))} gate actions emitted",
        ),
    ],

    # ── Research Officer ──────────────────────────────────────────────────────
    "research": [
        OfficerTrigger(
            trigger_id="research_high_confidence_finding",
            officer="research",
            trigger_type=TriggerType.LIFECYCLE_BASED,
            description="High-confidence investigation finding ready for research synthesis",
            action_type="investigation",
            condition=lambda ctx: len(_ctx(ctx, "high_confidence_findings", [])) > 0,
            title_fn=lambda ctx: (
                f"Research synthesis — {len(_ctx(ctx, 'high_confidence_findings', []))} "
                "high-confidence finding(s) require officer follow-through"
            ),
        ),
        OfficerTrigger(
            trigger_id="research_ori_red",
            officer="research",
            trigger_type=TriggerType.EVENT_DRIVEN,
            description="ORI RED — Research Officer activates threat analysis",
            action_type="investigation",
            condition=lambda ctx: _ctx(ctx, "resilience_risk") == "RED",
            title_fn=lambda ctx: f"Resilience threat research — ORI RED: {(_ctx(ctx, 'resilience_summary') or '')[:60]}",
        ),
    ],

    # ── Knowledge Officer ─────────────────────────────────────────────────────
    "knowledge": [
        OfficerTrigger(
            trigger_id="knowledge_lesson_candidates",
            officer="knowledge",
            trigger_type=TriggerType.THRESHOLD_BASED,
            description="Lesson candidates accumulating — knowledge capture required",
            action_type="improvement",
            condition=lambda ctx: _ctx(ctx, "lesson_candidates_pending", 0) >= 3,
            title_fn=lambda ctx: (
                f"Knowledge capture mission — {_ctx(ctx, 'lesson_candidates_pending', 0)} "
                "lesson candidates awaiting codification"
            ),
        ),
        OfficerTrigger(
            trigger_id="knowledge_cross_domain",
            officer="knowledge",
            trigger_type=TriggerType.LIFECYCLE_BASED,
            description="Cross-domain opportunities detected — knowledge officer synthesises",
            action_type="improvement",
            condition=lambda ctx: len(_ctx(ctx, "cross_domain_opportunities", [])) >= 2,
            title_fn=lambda ctx: (
                f"Cross-domain synthesis — {len(_ctx(ctx, 'cross_domain_opportunities', []))} "
                "opportunities identified for knowledge integration"
            ),
        ),
    ],

    # ── Chief Engineer ────────────────────────────────────────────────────────
    "engineering": [
        OfficerTrigger(
            trigger_id="eng_blocked_missions",
            officer="engineering",
            trigger_type=TriggerType.THRESHOLD_BASED,
            description="≥2 engineering missions blocked — Chief Engineer intervenes",
            action_type="investigation",
            condition=lambda ctx: _ctx(ctx, "engineering_blocked", 0) >= 2,
            title_fn=lambda ctx: (
                f"Engineering blocker investigation — {_ctx(ctx, 'engineering_blocked', 0)} "
                "missions blocked concurrently"
            ),
        ),
        OfficerTrigger(
            trigger_id="eng_critical_tech_debt",
            officer="engineering",
            trigger_type=TriggerType.THRESHOLD_BASED,
            description="Critical tech debt items detected — engineering assessment required",
            action_type="technical_debt_review",
            condition=lambda ctx: _ctx(ctx, "tech_debt_critical_count", 0) >= 1,
            title_fn=lambda ctx: (
                f"Technical debt remediation assessment — {_ctx(ctx, 'tech_debt_critical_count', 0)} "
                "critical item(s) identified"
            ),
        ),
        OfficerTrigger(
            trigger_id="eng_capability_gap",
            officer="engineering",
            trigger_type=TriggerType.THRESHOLD_BASED,
            description="Critical capability gaps — engineering capability improvement plan",
            action_type="capability_improvement",
            condition=lambda ctx: _ctx(ctx, "capability_gap_count", 0) >= 1,
            title_fn=lambda ctx: (
                f"Capability improvement plan — {_ctx(ctx, 'capability_gap_count', 0)} "
                "critical gap(s) require engineering investment"
            ),
        ),
    ],

    # ── Operations Officer (Number One) ───────────────────────────────────────
    "number_one": [
        OfficerTrigger(
            trigger_id="n1_blocked_initiatives",
            officer="number_one",
            trigger_type=TriggerType.THRESHOLD_BASED,
            description="Blocked initiatives — Number One coordinates dependency resolution",
            action_type="review",
            condition=lambda ctx: _ctx(ctx, "blocked_initiatives_count", 0) >= 2,
            title_fn=lambda ctx: (
                f"Dependency unblocking coordination — {_ctx(ctx, 'blocked_initiatives_count', 0)} "
                "initiatives blocked"
            ),
        ),
        OfficerTrigger(
            trigger_id="n1_delivery_risk",
            officer="number_one",
            trigger_type=TriggerType.THRESHOLD_BASED,
            description="Delivery risks accumulating — PMO intervention required",
            action_type="review",
            condition=lambda ctx: _ctx(ctx, "delivery_risks_count", 0) >= 3,
            title_fn=lambda ctx: (
                f"PMO delivery risk intervention — {_ctx(ctx, 'delivery_risks_count', 0)} "
                "active delivery risks"
            ),
        ),
        OfficerTrigger(
            trigger_id="n1_capacity_overload",
            officer="number_one",
            trigger_type=TriggerType.EVENT_DRIVEN,
            description="Portfolio capacity OVERLOADED — Number One rebalances",
            action_type="review",
            condition=lambda ctx: _ctx(ctx, "delivery_constraint_critical", 0) >= 2,
            title_fn=lambda ctx: "Portfolio capacity rebalancing — overload state requires Number One coordination",
        ),
    ],

    # ── QA Validation Officer ─────────────────────────────────────────────────
    "qa": [
        OfficerTrigger(
            trigger_id="qa_decision_packages",
            officer="qa",
            trigger_type=TriggerType.LIFECYCLE_BASED,
            description="Decision packages ready — QA validation gate",
            action_type="review",
            condition=lambda ctx: _ctx(ctx, "decision_packages_ready", 0) >= 1,
            title_fn=lambda ctx: (
                f"QA decision package validation — {_ctx(ctx, 'decision_packages_ready', 0)} "
                "package(s) awaiting quality gate"
            ),
        ),
        OfficerTrigger(
            trigger_id="qa_benefit_leakage",
            officer="qa",
            trigger_type=TriggerType.THRESHOLD_BASED,
            description="Critical benefit leakage — QA validates benefit tracking integrity",
            action_type="review",
            condition=lambda ctx: _ctx(ctx, "benefit_leakage_critical", 0) >= 1,
            title_fn=lambda ctx: (
                f"Benefit tracking integrity review — {_ctx(ctx, 'benefit_leakage_critical', 0)} "
                "critical leakage item(s)"
            ),
        ),
    ],

    # ── XO ────────────────────────────────────────────────────────────────────
    "xo": [
        OfficerTrigger(
            trigger_id="xo_stop_recommendations",
            officer="xo",
            trigger_type=TriggerType.THRESHOLD_BASED,
            description="Stop recommendations issued — XO initiates initiative closure review",
            action_type="review",
            condition=lambda ctx: _ctx(ctx, "stop_recommendations", 0) >= 1,
            title_fn=lambda ctx: (
                f"Initiative closure review — {_ctx(ctx, 'stop_recommendations', 0)} "
                "stop recommendation(s) requiring XO decision"
            ),
        ),
        OfficerTrigger(
            trigger_id="xo_investment_review",
            officer="xo",
            trigger_type=TriggerType.LIFECYCLE_BASED,
            description="Investment review flagged — XO synthesises executive investment brief",
            action_type="review",
            condition=lambda ctx: bool(_ctx(ctx, "investment_review_summary")),
            title_fn=lambda ctx: "Executive investment synthesis — XO aggregates portfolio investment signals",
        ),
    ],
}


# ── Evaluation engine ─────────────────────────────────────────────────────────

def evaluate_trigger(trigger: OfficerTrigger, ctx: Any) -> TriggerResult:
    """Evaluate a single officer trigger against the current cycle context."""
    try:
        fired = trigger.condition(ctx)
        if fired:
            title = trigger.title_fn(ctx)
            context = trigger.context_fn(ctx)
            log.info(
                "[officer_triggers] FIRED %s/%s: %s",
                trigger.officer, trigger.trigger_id, title[:60],
            )
            return TriggerResult(
                fired=True,
                trigger_id=trigger.trigger_id,
                officer=trigger.officer,
                trigger_type=trigger.trigger_type,
                reason=trigger.description,
                action_type=trigger.action_type,
                action_title=title,
                action_context=context,
            )
        return TriggerResult(
            fired=False,
            trigger_id=trigger.trigger_id,
            officer=trigger.officer,
            trigger_type=trigger.trigger_type,
        )
    except Exception as exc:
        log.debug("[officer_triggers] Evaluation error %s/%s: %s", trigger.officer, trigger.trigger_id, exc)
        return TriggerResult(
            fired=False,
            trigger_id=trigger.trigger_id,
            officer=trigger.officer,
            trigger_type=trigger.trigger_type,
            reason=f"evaluation_error: {exc}",
        )


def evaluate_all_triggers(ctx: Any) -> dict[str, list[TriggerResult]]:
    """Evaluate all officer triggers and return fired results grouped by officer."""
    results: dict[str, list[TriggerResult]] = {}
    for officer, triggers in OFFICER_TRIGGERS.items():
        fired = []
        for trigger in triggers:
            result = evaluate_trigger(trigger, ctx)
            if result.fired:
                fired.append(result)
        if fired:
            results[officer] = fired
            log.info("[officer_triggers] %s: %d trigger(s) fired", officer, len(fired))
    return results


__all__ = [
    "TriggerType",
    "TriggerResult",
    "OfficerTrigger",
    "OFFICER_TRIGGERS",
    "evaluate_trigger",
    "evaluate_all_triggers",
]
