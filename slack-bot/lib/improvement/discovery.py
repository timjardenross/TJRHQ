"""Improvement Discovery Automation (EXEC-002A WP10).

Self-generating improvement behaviour. Officers discover opportunities without
Captain prompting, on a defined schedule, and convert qualifying observations
into missions automatically via the improvement budget gate.

Review Schedule (WP10):
  Daily:   human_systems, ori, number_one
  Weekly:  engineering, strategic_planning, communications, knowledge

Discovery Workflow:
  Observation → Candidate → Score → Budget Check → Mission Draft →
  Number One Triage → XO Approval → Execution

The budget gate (WP8) prevents improvement overload.
The scorecard (WP9) is created at mission creation for tracking.

Public API:
    REVIEW_SCHEDULE                — officer → frequency mapping
    DiscoveryResult                — result dataclass
    run_discovery(ctx, weekly_run) -> DiscoveryResult
    format_discovery_summary(...)  -> str
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.improvement.framework import ImprovementBand, ImprovementOpportunity
from lib.improvement.scoring import score_and_rank

if TYPE_CHECKING:
    from lib.improvement.budget import ImprovementBudget


# ── Schedule ──────────────────────────────────────────────────────────────────

REVIEW_SCHEDULE: dict[str, str] = {
    "human_systems":      "daily",
    "ori":                "daily",
    "number_one":         "daily",
    "engineering":        "weekly",
    "strategic_planning": "weekly",
    "communications":     "weekly",
    "knowledge":          "weekly",
}


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class DiscoveryResult:
    """Output of a discovery run."""
    daily_reviews_run: list[str]   = field(default_factory=list)
    weekly_reviews_run: list[str]  = field(default_factory=list)

    candidates: list[ImprovementOpportunity] = field(default_factory=list)
    high_band:  list[ImprovementOpportunity] = field(default_factory=list)
    medium_band: list[ImprovementOpportunity] = field(default_factory=list)
    low_band:   list[ImprovementOpportunity] = field(default_factory=list)

    missions_created: list[str] = field(default_factory=list)   # mission IDs
    missions_deferred: int = 0   # budget gate prevented creation
    missions_failed: int = 0     # creation error

    budget: Any = None           # ImprovementBudget (typed loosely to avoid circular)
    discovered_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def total_candidates(self) -> int:
        return len(self.candidates)

    @property
    def reviews_run(self) -> list[str]:
        return self.daily_reviews_run + self.weekly_reviews_run


# ── Review runners ────────────────────────────────────────────────────────────

def _run_daily_reviews(ctx: Any) -> tuple[list[str], list[ImprovementOpportunity]]:
    """Run daily officer reviews. Returns (officers_run, opportunities)."""
    from lib.improvement.officer_reviews import (
        review_human_systems, review_ori, review_number_one,
    )

    daily_fns = [
        ("human_systems", review_human_systems),
        ("ori",           review_ori),
        ("number_one",    review_number_one),
    ]

    officers_run: list[str] = []
    opportunities: list[ImprovementOpportunity] = []

    for officer, fn in daily_fns:
        try:
            ops = fn(ctx)
            opportunities.extend(ops)
            officers_run.append(officer)
            log.debug("[improvement.discovery] Daily review %s: %d opportunity/ies", officer, len(ops))
        except Exception as exc:
            log.warning("[improvement.discovery] Daily review %s failed: %s", officer, exc)

    return officers_run, opportunities


def _run_weekly_reviews(ctx: Any) -> tuple[list[str], list[ImprovementOpportunity]]:
    """Run weekly officer reviews. Returns (officers_run, opportunities)."""
    from lib.improvement.officer_reviews import (
        review_engineering, review_strategic_planning,
        review_communications, review_knowledge,
    )

    weekly_fns = [
        ("engineering",        review_engineering),
        ("strategic_planning", review_strategic_planning),
        ("communications",     review_communications),
        ("knowledge",          review_knowledge),
    ]

    officers_run: list[str] = []
    opportunities: list[ImprovementOpportunity] = []

    for officer, fn in weekly_fns:
        try:
            ops = fn(ctx)
            opportunities.extend(ops)
            officers_run.append(officer)
            log.debug("[improvement.discovery] Weekly review %s: %d opportunity/ies", officer, len(ops))
        except Exception as exc:
            log.warning("[improvement.discovery] Weekly review %s failed: %s", officer, exc)

    return officers_run, opportunities


# ── Mission creation with budget gate ────────────────────────────────────────

def _create_missions_within_budget(
    high_band: list[ImprovementOpportunity],
    budget: Any,  # ImprovementBudget
    result: DiscoveryResult,
) -> None:
    """Create missions for High-band opportunities, gated by improvement budget.

    Processes in composite score order (highest first).
    Stops when budget is exhausted.
    Runs D-057 pre-flight check on each candidate.
    Creates scorecard at mission creation.
    """
    try:
        from lib.improvement.framework import d057_check
        from lib.improvement.budget import ImprovementBudgetEngine
        from lib.improvement.scorecard import create_scorecard
        from command_memory_integration import create_mission_from_officer
    except ImportError as exc:
        log.warning("[improvement.discovery] Cannot import mission tools: %s", exc)
        return

    engine = ImprovementBudgetEngine()
    slots_used = 0
    max_slots = max(0, budget.budget_remaining)

    for opp in high_band:
        if slots_used >= max_slots:
            result.missions_deferred += 1
            _log_deferred(opp, "Budget exhausted")
            continue

        # D-057 pre-flight
        try:
            check = d057_check(
                title=opp.suggested_action,
                description=opp.observation,
                officer=opp.source_officer,
            )
            if not check.all_clear:
                result.missions_deferred += 1
                _log_deferred(opp, check.recommendation)
                continue
        except Exception as exc:
            log.debug("[improvement.discovery] D-057 check failed for %s: %s", opp.source_officer, exc)

        # Budget gate
        can_create, reason = engine.can_create_mission(budget, opp.category.value)
        if not can_create:
            result.missions_deferred += 1
            _log_deferred(opp, reason)
            continue

        # Create mission
        try:
            mission_id = create_mission_from_officer(
                officer=opp.source_officer,
                title=f"[IMPROVE] {opp.suggested_action[:80]}",
                summary=(
                    f"D-057 improvement mission. Category: {opp.category.value}. "
                    f"Observation: {opp.observation} "
                    f"Expected benefit: {opp.expected_benefit}"
                ),
                priority="P2",
                strategic_alignment="D-057 Continuous Improvement First",
                expected_outcome=opp.expected_benefit,
                success_criteria=f"Benefit: {opp.expected_benefit}",
                requires_approval="xo",
            )

            if mission_id:
                opp.mission_id = mission_id
                result.missions_created.append(mission_id)
                slots_used += 1

                # Create scorecard at mission start (WP9)
                try:
                    create_scorecard(
                        mission_id=mission_id,
                        officer=opp.source_officer,
                        baseline_state=opp.observation,
                        target_state=opp.expected_benefit,
                    )
                except Exception as exc:
                    log.debug("[improvement.discovery] Scorecard creation skipped: %s", exc)

                log.info(
                    "[improvement.discovery] Mission %s created (%s / score %.1f)",
                    mission_id, opp.source_officer,
                    opp.score.composite if opp.score else 0,
                )
            else:
                result.missions_failed += 1
        except Exception as exc:
            log.warning(
                "[improvement.discovery] Mission creation failed for %s: %s",
                opp.source_officer, exc,
            )
            result.missions_failed += 1


def _log_deferred(opp: ImprovementOpportunity, reason: str) -> None:
    """Log a deferred improvement candidate to Command Memory (non-blocking)."""
    try:
        sys.path.insert(0, str(_BOT))
        from command_memory_integration import log_decision_to_command_memory

        log_decision_to_command_memory(
            statement=(
                f"Improvement deferred ({opp.source_officer}): "
                f"{opp.suggested_action[:80]}"
            ),
            rationale=(
                f"Deferred reason: {reason}. "
                f"Category: {opp.category.value}. "
                f"Score: {round(opp.score.composite, 1) if opp.score else 'unscored'}. "
                f"Observation: {opp.observation[:120]}. "
                f"Will surface in next weekly review when budget allows."
            ),
            owner=f"improvement_deferred:{opp.source_officer}",
        )
    except Exception:
        pass


# ── Main entry point ──────────────────────────────────────────────────────────

def run_discovery(
    ctx: Any,
    *,
    weekly_run: bool = False,
    captain_override: bool = False,
) -> DiscoveryResult:
    """Run improvement discovery for all officers due for review.

    Args:
        ctx:              CycleContext with current operational state
        weekly_run:       If True, weekly officers also run (default: daily only)
        captain_override: If True, bypass Red capacity budget gate for critical items

    Returns:
        DiscoveryResult with all candidates, created missions, and budget state.
    """
    result = DiscoveryResult()

    # Step 1: Determine budget
    try:
        from lib.improvement.budget import get_current_budget

        capacity_status = getattr(ctx, "capacity_status", "Unknown")
        result.budget = get_current_budget(
            capacity_status, captain_override=captain_override
        )
        log.info(
            "[improvement.discovery] Budget: %s — %d/%d slots used",
            result.budget.status_label,
            result.budget.active_improvement_missions,
            result.budget.max_improvement_missions,
        )
    except Exception as exc:
        log.warning("[improvement.discovery] Budget unavailable: %s", exc)

    # Step 2: Run due reviews
    daily_officers, daily_opps = _run_daily_reviews(ctx)
    result.daily_reviews_run = daily_officers
    all_opps = list(daily_opps)

    if weekly_run:
        weekly_officers, weekly_opps = _run_weekly_reviews(ctx)
        result.weekly_reviews_run = weekly_officers
        all_opps.extend(weekly_opps)

    # Step 3: Score and band
    score_context = {
        "capacity_status":     getattr(ctx, "capacity_status", "Unknown"),
        "orphan_count":        getattr(ctx, "orphan_count", 0),
        "engineering_blocked": getattr(ctx, "engineering_blocked", 0),
        "comms_ready_count":   getattr(ctx, "comms_ready_count", 0),
        "resilience_risk":     getattr(ctx, "resilience_risk", "Unknown"),
    }
    all_opps = score_and_rank(all_opps, score_context)

    result.candidates  = all_opps
    result.high_band   = [o for o in all_opps if o.band == ImprovementBand.HIGH]
    result.medium_band = [o for o in all_opps if o.band == ImprovementBand.MEDIUM]
    result.low_band    = [o for o in all_opps if o.band == ImprovementBand.LOW]

    log.info(
        "[improvement.discovery] %d candidates: %d High, %d Medium, %d Low",
        len(all_opps), len(result.high_band), len(result.medium_band), len(result.low_band),
    )

    # Step 4: Create missions within budget
    if result.budget is not None and result.budget.can_create and result.high_band:
        _create_missions_within_budget(result.high_band, result.budget, result)
    elif result.high_band:
        log.info(
            "[improvement.discovery] %d High-band opportunities deferred — budget closed",
            len(result.high_band),
        )
        result.missions_deferred += len(result.high_band)

    # Step 5: Log Medium-band as decisions for weekly review
    _log_medium_band(result.medium_band)

    return result


def _log_medium_band(medium_band: list[ImprovementOpportunity]) -> None:
    """Log Medium-band items as Command Memory decisions (non-blocking)."""
    if not medium_band:
        return
    try:
        sys.path.insert(0, str(_BOT))
        from command_memory_integration import log_decision_to_command_memory

        for opp in medium_band:
            log_decision_to_command_memory(
                statement=(
                    f"Improvement candidate (Medium): "
                    f"{opp.source_officer} — {opp.suggested_action[:80]}"
                ),
                rationale=(
                    f"Category: {opp.category.value}. "
                    f"Observation: {opp.observation[:120]}. "
                    f"Expected benefit: {opp.expected_benefit}. "
                    f"Score: {round(opp.score.composite, 1) if opp.score else 'unscored'}. "
                    f"Effort: {opp.estimated_effort}. "
                    f"Review in next weekly improvement cycle."
                ),
                owner=f"improvement_candidate:{opp.source_officer}",
            )
    except Exception as exc:
        log.debug("[improvement.discovery] Medium-band log skipped: %s", exc)


# ── Formatting ────────────────────────────────────────────────────────────────

def format_discovery_summary(result: DiscoveryResult) -> str:
    """Format discovery result as a brief summary line for Captain brief."""
    if not result.candidates:
        return "_Improvement discovery: no opportunities identified this cycle._"

    parts = [
        f"*Improvement Discovery:* {result.total_candidates} candidate(s) — "
        f"{len(result.high_band)} High / {len(result.medium_band)} Medium / {len(result.low_band)} Low"
    ]

    if result.missions_created:
        parts.append(f"{len(result.missions_created)} mission(s) created (XO queue)")
    if result.missions_deferred:
        parts.append(f"{result.missions_deferred} deferred (budget or D-057 gate)")

    if result.budget:
        parts.append(
            f"Budget: {result.budget.active_improvement_missions}/{result.budget.max_improvement_missions} "
            f"slots ({result.budget.capacity_status})"
        )

    reviews = result.daily_reviews_run + result.weekly_reviews_run
    parts.append(f"Reviews run: {', '.join(reviews)}")

    return " | ".join(parts)


__all__ = [
    "REVIEW_SCHEDULE",
    "DiscoveryResult",
    "run_discovery",
    "format_discovery_summary",
]
