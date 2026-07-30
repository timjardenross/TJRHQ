"""Weekly Improvement Review (EXEC-002 WP6).

Produces a ship-wide improvement brief every week:
  - XO Section:          All improvement missions pending approval
  - Number One Section:  All improvement missions ready for assignment
  - Captain Section:     Top 3 improvement opportunities by composite score

The weekly review is the cadence. The daily review is the observation engine.

Missions are created automatically for High-band opportunities after D-057 checks.
Medium-band opportunities are logged as decisions for this review.
Low-band opportunities are silently recorded.

Public API:
    run_weekly_improvement_review(ctx) -> WeeklyImprovementBrief
    format_weekly_brief(brief)         -> str   (Slack-ready)
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.improvement.framework import ImprovementBand, ImprovementOpportunity
from lib.improvement.officer_reviews import run_all_reviews
from lib.improvement.scoring import score_and_rank


# ── Data structure ────────────────────────────────────────────────────────────

@dataclass
class WeeklyImprovementBrief:
    """Ship-wide improvement review output."""
    reviewed_at: datetime = field(default_factory=datetime.utcnow)
    total_opportunities: int = 0
    high_band: list[ImprovementOpportunity] = field(default_factory=list)
    medium_band: list[ImprovementOpportunity] = field(default_factory=list)
    low_band: list[ImprovementOpportunity] = field(default_factory=list)
    missions_created: list[str] = field(default_factory=list)   # mission IDs
    missions_failed: int = 0
    outcomes_this_week: list[dict] = field(default_factory=list)

    @property
    def top_3(self) -> list[ImprovementOpportunity]:
        all_scored = self.high_band + self.medium_band
        return all_scored[:3]


# ── Core function ─────────────────────────────────────────────────────────────

def run_weekly_improvement_review(ctx: Any) -> WeeklyImprovementBrief:
    """Run ship-wide weekly improvement review.

    Steps:
      1. Run all officer domain reviews (or use pre-computed ctx)
      2. Score and rank all opportunities
      3. D-057 pre-flight check on High-band items
      4. Create missions for items that pass D-057 checks
      5. Log Medium-band items as decisions
      6. Retrieve recent improvement outcomes
      7. Return WeeklyImprovementBrief

    Non-blocking: each step degrades gracefully.
    """
    brief = WeeklyImprovementBrief()

    # Step 1+2: Collect and score observations
    try:
        raw_context = _build_score_context(ctx)
        opportunities = run_all_reviews(ctx)
        opportunities = score_and_rank(opportunities, raw_context)

        brief.total_opportunities = len(opportunities)
        brief.high_band   = [o for o in opportunities if o.band == ImprovementBand.HIGH]
        brief.medium_band = [o for o in opportunities if o.band == ImprovementBand.MEDIUM]
        brief.low_band    = [o for o in opportunities if o.band == ImprovementBand.LOW]

        log.info(
            "[improvement.weekly] %d opportunities: %d High, %d Medium, %d Low",
            len(opportunities), len(brief.high_band), len(brief.medium_band), len(brief.low_band),
        )
    except Exception as exc:
        log.warning("[improvement.weekly] Review collection failed: %s", exc)
        return brief

    # Steps 3+4: D-057 check and mission creation for High-band items
    _create_high_band_missions(brief)

    # Step 5: Log Medium-band items as decisions
    _log_medium_band_decisions(brief)

    # Step 6: Fetch recent outcomes
    try:
        from lib.improvement.validation import get_improvement_outcomes
        brief.outcomes_this_week = get_improvement_outcomes(limit=5)
    except Exception as exc:
        log.debug("[improvement.weekly] Outcome retrieval skipped: %s", exc)

    return brief


def _build_score_context(ctx: Any) -> dict[str, Any]:
    """Extract scoring context from CycleContext."""
    return {
        "capacity_status":    getattr(ctx, "capacity_status", "Unknown"),
        "orphan_count":       getattr(ctx, "orphan_count", 0),
        "engineering_blocked": getattr(ctx, "engineering_blocked", 0),
        "comms_ready_count":  getattr(ctx, "comms_ready_count", 0),
        "resilience_risk":    getattr(ctx, "resilience_risk", "Unknown"),
    }


def _create_high_band_missions(brief: WeeklyImprovementBrief) -> None:
    """Create missions for High-band opportunities after D-057 checks."""
    try:
        from lib.improvement.framework import d057_check, ImprovementBand
        from command_memory_integration import create_mission_from_officer
    except ImportError as exc:
        log.warning("[improvement.weekly] Cannot import mission creation tools: %s", exc)
        return

    for opp in brief.high_band:
        try:
            check = d057_check(
                title=opp.suggested_action,
                description=opp.observation,
                officer=opp.source_officer,
            )

            if not check.all_clear:
                log.info(
                    "[improvement.weekly] D-057 flag for %s / %s — %s",
                    opp.source_officer, opp.suggested_action[:60], check.recommendation,
                )
                continue

            mission_id = create_mission_from_officer(
                officer=opp.source_officer,
                title=f"[IMPROVE] {opp.suggested_action}",
                summary=(
                    f"D-057 improvement mission. Category: {opp.category.value}. "
                    f"Observation: {opp.observation} "
                    f"Expected benefit: {opp.expected_benefit}"
                ),
                priority="P2",
                strategic_alignment="D-057 Continuous Improvement First",
                expected_outcome=opp.expected_benefit,
                success_criteria=f"Benefit realised: {opp.expected_benefit}",
                requires_approval="xo",
            )

            if mission_id:
                opp.mission_id = mission_id
                brief.missions_created.append(mission_id)
                log.info(
                    "[improvement.weekly] Mission created: %s (%s)",
                    mission_id, opp.source_officer,
                )
            else:
                brief.missions_failed += 1
        except Exception as exc:
            log.warning(
                "[improvement.weekly] Mission creation failed for %s: %s",
                opp.source_officer, exc,
            )
            brief.missions_failed += 1


def _log_medium_band_decisions(brief: WeeklyImprovementBrief) -> None:
    """Log Medium-band items as decisions in Command Memory for weekly review."""
    if not brief.medium_band:
        return
    try:
        from command_memory_integration import log_decision_to_command_memory

        for opp in brief.medium_band:
            log_decision_to_command_memory(
                statement=(
                    f"Improvement opportunity (Medium): "
                    f"{opp.source_officer} — {opp.suggested_action[:100]}"
                ),
                rationale=(
                    f"Category: {opp.category.value}. "
                    f"Observation: {opp.observation} "
                    f"Expected benefit: {opp.expected_benefit}. "
                    f"Score: {round(opp.score.composite, 1) if opp.score else 'unscored'}. "
                    f"Effort: {opp.estimated_effort}."
                ),
                owner=f"improvement:{opp.source_officer}",
            )
    except Exception as exc:
        log.debug("[improvement.weekly] Medium-band decision log skipped: %s", exc)


# ── Formatting ────────────────────────────────────────────────────────────────

def format_weekly_brief(brief: WeeklyImprovementBrief) -> str:
    """Format WeeklyImprovementBrief into a Slack-ready string.

    Sections:
      - Header with date and summary stats
      - Top 3 improvement opportunities for Captain
      - Missions created this cycle (for XO queue)
      - Outcomes completed this week
    """
    lines = [
        "*WEEKLY IMPROVEMENT REVIEW*",
        f"_{brief.reviewed_at.strftime('%Y-%m-%d')} — D-057 Continuous Improvement First_",
        "",
        f"*Summary:* {brief.total_opportunities} observations | "
        f"{len(brief.high_band)} High | {len(brief.medium_band)} Medium | {len(brief.low_band)} Low",
        f"*Missions created:* {len(brief.missions_created)}"
        + (f" | {brief.missions_failed} failed" if brief.missions_failed else ""),
        "",
    ]

    # Top 3 for Captain
    top3 = brief.top_3
    if top3:
        lines.append("*Top Improvement Opportunities (Captain):*")
        for i, opp in enumerate(top3, 1):
            score_str = f" [score: {round(opp.score.composite, 1)}]" if opp.score else ""
            band_icon = ":large_red_circle:" if opp.band == ImprovementBand.HIGH else ":large_yellow_circle:"
            mission_note = f" — mission `{opp.mission_id}` created" if opp.mission_id else ""
            lines.append(
                f"  {i}. {band_icon} *[{opp.source_officer.upper()}]* "
                f"{opp.suggested_action[:100]}{score_str}{mission_note}"
            )
            lines.append(f"     _{opp.observation[:120]}_")
        lines.append("")

    # Missions created — routes to XO
    if brief.missions_created:
        lines.append(f"*Improvement Missions in XO Queue ({len(brief.missions_created)}):*")
        for mid in brief.missions_created:
            lines.append(f"  :white_square_button: `{mid}` — awaiting XO approval")
        lines.append("")

    # Outcomes completed
    if brief.outcomes_this_week:
        lines.append(f"*Outcomes Validated ({len(brief.outcomes_this_week)}):*")
        for outcome in brief.outcomes_this_week[:3]:
            stmt = outcome.get("statement", "")
            lines.append(f"  :white_check_mark: {stmt}")
        lines.append("")

    if not (top3 or brief.missions_created or brief.outcomes_this_week):
        lines.append("_No improvement opportunities identified this cycle._")

    return "\n".join(lines)


__all__ = [
    "WeeklyImprovementBrief",
    "run_weekly_improvement_review",
    "format_weekly_brief",
]
