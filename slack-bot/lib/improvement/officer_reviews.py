"""Officer Improvement Reviews (EXEC-002 WP2).

Each officer runs a structured domain review to identify improvement opportunities.
Reviews are heuristic — they look for patterns, gaps, waste, and automatable work.

Officers produce observations; observations become ImprovementOpportunity objects.
The scoring engine (WP4) then bands them High / Medium / Low.
High-band items route to mission creation via create_mission_from_officer().

Sequence within the daily cycle:
  _step_improvement_review(ctx) calls each review function,
  passing pre-computed CycleContext fields rather than re-querying Supabase.

Public API:
    review_human_systems(ctx)   -> list[ImprovementOpportunity]
    review_strategic_planning(ctx) -> list[ImprovementOpportunity]
    review_engineering(ctx)     -> list[ImprovementOpportunity]
    review_communications(ctx)  -> list[ImprovementOpportunity]
    review_ori(ctx)             -> list[ImprovementOpportunity]
    review_number_one(ctx)      -> list[ImprovementOpportunity]
    run_all_reviews(ctx)        -> list[ImprovementOpportunity]
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, TYPE_CHECKING

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.improvement.framework import ImprovementCategory, ImprovementOpportunity

if TYPE_CHECKING:
    from lib.daily_ops_cycle import CycleContext


# ── Human Systems Review ──────────────────────────────────────────────────────

def review_human_systems(ctx: Any) -> list[ImprovementOpportunity]:
    """Human Systems Officer — capacity governance improvement review."""
    opportunities: list[ImprovementOpportunity] = []

    status = getattr(ctx, "capacity_status", "Unknown")
    score = getattr(ctx, "capacity_score", None)
    actions = getattr(ctx, "capacity_actions", [])

    # Missing capacity data — no log entry for today
    if status == "Unknown" or score is None:
        opportunities.append(ImprovementOpportunity(
            source_officer="human_systems",
            domain="capacity_governance",
            observation="Capacity score unavailable — daily log entry may be missing",
            category=ImprovementCategory.AUTOMATION,
            suggested_action="Automate daily capacity log entry or create reminder mission",
            estimated_effort="low",
            expected_benefit="Capacity gate runs every cycle with valid data",
        ))

    # Capacity in Amber/Red AND gate emitted more than 3 actions — complexity signal
    if status in ("Amber", "Red") and len(actions) > 3:
        opportunities.append(ImprovementOpportunity(
            source_officer="human_systems",
            domain="capacity_governance",
            observation=(
                f"Capacity at {status} with {len(actions)} gate actions emitted. "
                "Recovery pattern may benefit from structured protocol."
            ),
            category=ImprovementCategory.RISK,
            suggested_action="Define and implement documented capacity recovery protocol",
            estimated_effort="medium",
            expected_benefit="Faster, consistent recovery when capacity degrades",
        ))

    # Capacity Red but no recovery trigger found in actions
    if status == "Red":
        recovery_actions = [a for a in actions if a.get("type") == "trigger_recovery"]
        if not recovery_actions:
            opportunities.append(ImprovementOpportunity(
                source_officer="human_systems",
                domain="capacity_governance",
                observation="RED capacity detected but no recovery protocol triggered",
                category=ImprovementCategory.RISK,
                suggested_action="Review and test RED capacity recovery trigger mechanism",
                estimated_effort="low",
                expected_benefit="Recovery protocol fires reliably under RED conditions",
            ))

    return opportunities


# ── Strategic Planning Review ─────────────────────────────────────────────────

def review_strategic_planning(ctx: Any) -> list[ImprovementOpportunity]:
    """Strategic Planning Officer — portfolio alignment improvement review."""
    opportunities: list[ImprovementOpportunity] = []

    orphan_count = getattr(ctx, "orphan_count", 0)
    portfolio_items = getattr(ctx, "portfolio_items", [])

    # High orphan count — systemic alignment problem, not individual missions
    if orphan_count >= 5:
        opportunities.append(ImprovementOpportunity(
            source_officer="strategic_planning",
            domain="portfolio_alignment",
            observation=f"{orphan_count} missions with no strategic objective link",
            category=ImprovementCategory.ALIGNMENT,
            suggested_action=(
                "Create mission intake checklist that requires strategic objective "
                "selection before a mission can leave Idea state"
            ),
            estimated_effort="low",
            expected_benefit="New missions arrive with objective links; orphan count drops to 0",
        ))
    elif orphan_count >= 3:
        opportunities.append(ImprovementOpportunity(
            source_officer="strategic_planning",
            domain="portfolio_alignment",
            observation=f"{orphan_count} missions without strategic objective (threshold: 3)",
            category=ImprovementCategory.ALIGNMENT,
            suggested_action="Review and link current orphan missions during next portfolio review",
            estimated_effort="low",
            expected_benefit="Portfolio alignment score improves; decision support more accurate",
        ))

    # Excessive portfolio items surfaced — signal that decision support is generating noise
    underfunded = [i for i in portfolio_items if i.get("action") == "flag_underfunded_objective"]
    overloaded  = [i for i in portfolio_items if i.get("action") == "flag_overloaded_objective"]

    if len(overloaded) >= 2:
        opportunities.append(ImprovementOpportunity(
            source_officer="strategic_planning",
            domain="portfolio_balance",
            observation=(
                f"{len(overloaded)} strategic objectives are overloaded (>5 active missions). "
                "Portfolio is concentrated; risk of single-objective failure."
            ),
            category=ImprovementCategory.RISK,
            suggested_action="Review overloaded objectives for mission decomposition or deferral",
            estimated_effort="medium",
            expected_benefit="Portfolio distributed across objectives; resilience improves",
        ))

    if len(underfunded) >= 3:
        opportunities.append(ImprovementOpportunity(
            source_officer="strategic_planning",
            domain="portfolio_balance",
            observation=(
                f"{len(underfunded)} strategic objectives underfunded (<2 active missions). "
                "Strategic intent not resourced."
            ),
            category=ImprovementCategory.ALIGNMENT,
            suggested_action="Create a resource allocation review mission to address underfunding",
            estimated_effort="medium",
            expected_benefit="All active strategic objectives have at least 2 supporting missions",
        ))

    return opportunities


# ── Engineering Review ────────────────────────────────────────────────────────

def review_engineering(ctx: Any) -> list[ImprovementOpportunity]:
    """Engineering Officer — delivery improvement review."""
    opportunities: list[ImprovementOpportunity] = []

    blocked = getattr(ctx, "engineering_blocked", 0)
    in_progress = getattr(ctx, "engineering_in_progress", 0)
    all_items = getattr(ctx, "all_items", [])

    engineering_items = [i for i in all_items if i.get("source") == "engineering"]

    # Blocked missions — look for pattern (multiple blocked = systemic)
    if blocked >= 3:
        opportunities.append(ImprovementOpportunity(
            source_officer="engineering",
            domain="delivery",
            observation=(
                f"{blocked} missions currently blocked. "
                "Systemic blocker pattern — individual resolution is not enough."
            ),
            category=ImprovementCategory.RISK,
            suggested_action=(
                "Analyse blocker root causes and create a systemic unblocking mission "
                "(tooling, dependency, or process improvement)"
            ),
            estimated_effort="medium",
            expected_benefit="Blocker count reduces to 0 for same category within 2 weeks",
        ))
    elif blocked >= 1:
        opportunities.append(ImprovementOpportunity(
            source_officer="engineering",
            domain="delivery",
            observation=f"{blocked} mission(s) blocked — resolution should prevent recurrence",
            category=ImprovementCategory.RISK,
            suggested_action="Resolve blocker and log lesson learned to prevent recurrence",
            estimated_effort="low",
            expected_benefit="Blocker resolved with lesson learned captured",
        ))

    # No in-progress missions when there are portfolio items — execution gap
    if in_progress == 0 and len(engineering_items) > 2:
        opportunities.append(ImprovementOpportunity(
            source_officer="engineering",
            domain="delivery",
            observation=(
                "No missions in progress but portfolio shows active items. "
                "Possible execution gap or status staleness."
            ),
            category=ImprovementCategory.WASTE,
            suggested_action="Audit mission status accuracy and triage idle queue",
            estimated_effort="low",
            expected_benefit="Mission statuses reflect reality; execution resumes",
        ))

    return opportunities


# ── Communications Review ─────────────────────────────────────────────────────

def review_communications(ctx: Any) -> list[ImprovementOpportunity]:
    """Communications Officer — pipeline improvement review."""
    opportunities: list[ImprovementOpportunity] = []

    pipeline = getattr(ctx, "comms_pipeline", {})
    ready_count = getattr(ctx, "comms_ready_count", 0)

    if not isinstance(pipeline, dict):
        return opportunities

    review_count   = int(pipeline.get("review", 0))
    approved_count = int(pipeline.get("approved", 0))
    draft_count    = int(pipeline.get("draft", 0))

    # Items piling up in "review" — review bottleneck
    if review_count >= 3:
        opportunities.append(ImprovementOpportunity(
            source_officer="communications",
            domain="content_pipeline",
            observation=f"{review_count} items stuck in 'review' state — Captain review may be bottleneck",
            category=ImprovementCategory.CAPACITY,
            suggested_action=(
                "Introduce XO-level pre-review to filter content before Captain approval; "
                "reduces direct Captain review burden"
            ),
            estimated_effort="low",
            expected_benefit="Review backlog clears; Captain only reviews pre-screened content",
        ))

    # Items in "approved" but not published — publishing friction
    if approved_count >= 2:
        opportunities.append(ImprovementOpportunity(
            source_officer="communications",
            domain="content_pipeline",
            observation=(
                f"{approved_count} items approved but not yet confirmed for publishing. "
                "Captain confirmation may be manual friction."
            ),
            category=ImprovementCategory.AUTOMATION,
            suggested_action=(
                "Create automated Captain confirmation reminder for items "
                "that have been approved for >24h"
            ),
            estimated_effort="low",
            expected_benefit="Approved content reaches ready_to_publish within 24h of approval",
        ))

    # Empty pipeline — no opportunities being identified
    total_active = draft_count + review_count + approved_count + ready_count
    if total_active == 0:
        opportunities.append(ImprovementOpportunity(
            source_officer="communications",
            domain="content_pipeline",
            observation="No content in pipeline — opportunity identification may have stalled",
            category=ImprovementCategory.WASTE,
            suggested_action=(
                "Review opportunity gathering sources and ensure "
                "gather_opportunities() is surfacing content from active missions"
            ),
            estimated_effort="low",
            expected_benefit="Pipeline has at least 1 item in draft each week",
        ))

    return opportunities


# ── ORI Review ────────────────────────────────────────────────────────────────

def review_ori(ctx: Any) -> list[ImprovementOpportunity]:
    """ORI Officer — resilience improvement review."""
    opportunities: list[ImprovementOpportunity] = []

    risk = getattr(ctx, "resilience_risk", "Unknown")
    summary = getattr(ctx, "resilience_summary", None)
    available = getattr(ctx, "resilience_available", False)

    # No intelligence brief available
    if not available:
        opportunities.append(ImprovementOpportunity(
            source_officer="ori",
            domain="resilience_intelligence",
            observation="ORI intelligence brief unavailable — resilience monitoring gap",
            category=ImprovementCategory.RISK,
            suggested_action="Investigate intelligence_briefs table and ORI brief generation pipeline",
            estimated_effort="low",
            expected_benefit="ORI produces daily brief; resilience risk visible in every Captain brief",
        ))

    # Red resilience — structural issue, not just a flag
    if risk == "RED":
        opportunities.append(ImprovementOpportunity(
            source_officer="ori",
            domain="resilience_intelligence",
            observation=(
                f"ORI at RED: {(summary or '')[:120]}. "
                "RED resilience is a structural signal requiring a mission, not just a report."
            ),
            category=ImprovementCategory.RISK,
            suggested_action=(
                "Create a dedicated resilience improvement mission to address "
                "the root cause identified in the intelligence brief"
            ),
            estimated_effort="medium",
            expected_benefit="Resilience risk reduced from RED to AMBER or GREEN within mission timeline",
        ))

    # Amber resilience persisting — may need proactive mission
    if risk == "AMBER" and available:
        opportunities.append(ImprovementOpportunity(
            source_officer="ori",
            domain="resilience_intelligence",
            observation="ORI at AMBER — proactive risk reduction mission may be warranted",
            category=ImprovementCategory.RISK,
            suggested_action="Review AMBER risk factors and assess whether proactive mission prevents escalation to RED",
            estimated_effort="low",
            expected_benefit="Resilience maintained at GREEN; no escalation to RED",
        ))

    return opportunities


# ── Number One Review ─────────────────────────────────────────────────────────

def review_number_one(ctx: Any) -> list[ImprovementOpportunity]:
    """Number One — coordination improvement review.

    Number One has the widest visibility of all officers — can observe
    cross-domain patterns that individual officers cannot see.
    """
    opportunities: list[ImprovementOpportunity] = []

    all_items = getattr(ctx, "all_items", [])
    captain_items = [i for i in all_items if i.get("type") in {
        "strategic_decision", "governance_exception", "capacity_override",
        "priority_conflict", "resource_constraint",
    }]
    number_one_items = [i for i in all_items if i.get("type") in {
        "stale_mission", "missing_owner", "routine_escalation",
    }]

    # High Captain escalation volume — officers escalating too much
    if len(captain_items) > 5:
        opportunities.append(ImprovementOpportunity(
            source_officer="number_one",
            domain="escalation_management",
            observation=(
                f"{len(captain_items)} items routed to Captain this cycle. "
                "High Captain escalation volume may indicate delegation clarity gap."
            ),
            category=ImprovementCategory.CAPACITY,
            suggested_action=(
                "Review exception_router classification sets and authority manifests — "
                "some Captain items may be safely delegated to XO or Number One"
            ),
            estimated_effort="low",
            expected_benefit="Captain receives <3 items per cycle; officers resolve more independently",
        ))

    # Recurring stale missions — velocity problem
    stale_count = len([i for i in number_one_items if i.get("type") == "stale_mission"])
    if stale_count >= 4:
        opportunities.append(ImprovementOpportunity(
            source_officer="number_one",
            domain="mission_velocity",
            observation=(
                f"{stale_count} stale missions in Number One queue. "
                "Persistent staleness signals a velocity or ownership problem."
            ),
            category=ImprovementCategory.RISK,
            suggested_action=(
                "Run mission velocity review: identify systemic causes "
                "(unclear scope, missing owner, blocked dependencies)"
            ),
            estimated_effort="medium",
            expected_benefit="Stale mission count drops; missions progress through lifecycle consistently",
        ))

    # Missing owner pattern — onboarding/assignment gap
    missing_owner_count = len([i for i in number_one_items if i.get("type") == "missing_owner"])
    if missing_owner_count >= 2:
        opportunities.append(ImprovementOpportunity(
            source_officer="number_one",
            domain="assignment_management",
            observation=(
                f"{missing_owner_count} missions with no owner. "
                "Assignment process may have a gap before missions reach Number One."
            ),
            category=ImprovementCategory.WASTE,
            suggested_action=(
                "Ensure XO approval step includes owner recommendation; "
                "Number One assignment should be immediate on XO approval"
            ),
            estimated_effort="low",
            expected_benefit="No mission leaves XO approval without an owner assigned",
        ))

    # Cross-domain signal: high total items from multiple sources
    sources = {i.get("source") for i in all_items if i.get("source")}
    if len(sources) >= 4 and len(all_items) > 10:
        opportunities.append(ImprovementOpportunity(
            source_officer="number_one",
            domain="system_health",
            observation=(
                f"{len(all_items)} total items across {len(sources)} domains this cycle. "
                "High item volume may indicate systemic operational friction."
            ),
            category=ImprovementCategory.CAPACITY,
            suggested_action=(
                "Identify the single highest-leverage improvement across all domains "
                "and create a cross-domain improvement mission"
            ),
            estimated_effort="medium",
            expected_benefit="Item volume per cycle reduces by 30% within one month",
        ))

    return opportunities


# ── Composite ─────────────────────────────────────────────────────────────────

def run_all_reviews(ctx: Any) -> list[ImprovementOpportunity]:
    """Run all officer improvement reviews and return combined observations.

    Each review is non-blocking — individual failures don't stop others.
    """
    all_opportunities: list[ImprovementOpportunity] = []

    review_fns = [
        ("human_systems",      review_human_systems),
        ("strategic_planning", review_strategic_planning),
        ("engineering",        review_engineering),
        ("communications",     review_communications),
        ("ori",                review_ori),
        ("number_one",         review_number_one),
    ]

    for officer, fn in review_fns:
        try:
            ops = fn(ctx)
            all_opportunities.extend(ops)
            log.debug("[improvement] %s review: %d opportunity/ies", officer, len(ops))
        except Exception as exc:
            log.warning("[improvement] %s review failed (non-blocking): %s", officer, exc)

    return all_opportunities


__all__ = [
    "review_human_systems",
    "review_strategic_planning",
    "review_engineering",
    "review_communications",
    "review_ori",
    "review_number_one",
    "run_all_reviews",
]
