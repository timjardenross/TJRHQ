"""Improvement Scoring Engine (EXEC-002 WP4).

Scores ImprovementOpportunity objects on six dimensions per D-057.
Returns a composite score and assigns a band (High / Medium / Low).

High-band items are candidates for automatic mission creation.
Medium-band items are logged as decisions for weekly review.
Low-band items are recorded as observations.

Public API:
    ImprovementScoringEngine.score(opportunity, context) -> ImprovementScore
    ImprovementScoringEngine.rank(opportunities)        -> list[ImprovementOpportunity]
    score_and_rank(opportunities, context)              -> list[ImprovementOpportunity]
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

from lib.improvement.framework import (
    ImprovementCategory,
    ImprovementOpportunity,
    ImprovementScore,
)


class ImprovementScoringEngine:
    """Six-dimension improvement scorer per D-057.

    Scoring is heuristic, not AI-generated. Each dimension is scored 0–10
    using observable signals from the opportunity data and execution context.

    Context keys used (all optional — defaults to conservative scores):
      capacity_status   — "Green" | "Amber" | "Red"
      orphan_count      — int (strategic misalignment signal)
      engineering_blocked — int
      comms_ready_count — int
      resilience_risk   — "GREEN" | "AMBER" | "RED"
      active_objectives — list of active strategic objectives (for alignment check)
    """

    def score(
        self,
        opportunity: ImprovementOpportunity,
        context: dict[str, Any] | None = None,
    ) -> ImprovementScore:
        """Score a single opportunity. Returns ImprovementScore."""
        ctx = context or {}
        cat = opportunity.category

        cci  = self._score_captain_capacity_impact(opportunity, ctx)
        orr  = self._score_operational_risk_reduction(opportunity, ctx)
        reuse = self._score_reuse_opportunity(opportunity, ctx)
        auto  = self._score_automation_opportunity(opportunity, ctx)
        align = self._score_strategic_alignment(opportunity, ctx)
        effort = self._score_implementation_effort(opportunity, ctx)

        return ImprovementScore(
            captain_capacity_impact=cci,
            operational_risk_reduction=orr,
            reuse_opportunity=reuse,
            automation_opportunity=auto,
            strategic_alignment=align,
            implementation_effort=effort,
        )

    def rank(
        self,
        opportunities: list[ImprovementOpportunity],
    ) -> list[ImprovementOpportunity]:
        """Return opportunities sorted by composite score descending."""
        return sorted(
            opportunities,
            key=lambda o: (o.score.composite if o.score else 0.0),
            reverse=True,
        )

    # ── Dimension scorers ─────────────────────────────────────────────────────

    def _score_captain_capacity_impact(
        self, opp: ImprovementOpportunity, ctx: dict
    ) -> int:
        """High when improvement directly reduces Captain escalation burden."""
        if opp.category in (ImprovementCategory.CAPACITY, ImprovementCategory.AUTOMATION):
            base = 8
        elif opp.category == ImprovementCategory.WASTE:
            base = 6
        else:
            base = 4

        # Amplify if current capacity is stressed
        status = ctx.get("capacity_status", "Unknown")
        if status == "Red":
            base = min(10, base + 2)
        elif status == "Amber":
            base = min(10, base + 1)

        return base

    def _score_operational_risk_reduction(
        self, opp: ImprovementOpportunity, ctx: dict
    ) -> int:
        if opp.category == ImprovementCategory.RISK:
            base = 9
        elif opp.category == ImprovementCategory.ALIGNMENT:
            base = 6
        elif opp.category in (ImprovementCategory.WASTE, ImprovementCategory.AUTOMATION):
            base = 4
        else:
            base = 3

        # Resilience signal amplifies risk-reduction value
        resilience = str(ctx.get("resilience_risk", "")).upper()
        if resilience == "RED" and opp.category == ImprovementCategory.RISK:
            base = min(10, base + 1)

        return base

    def _score_reuse_opportunity(
        self, opp: ImprovementOpportunity, ctx: dict
    ) -> int:
        if opp.category == ImprovementCategory.REUSE:
            return 9
        # Automation improvements typically exploit existing infrastructure
        if opp.category == ImprovementCategory.AUTOMATION:
            return 7
        return 3

    def _score_automation_opportunity(
        self, opp: ImprovementOpportunity, ctx: dict
    ) -> int:
        if opp.category == ImprovementCategory.AUTOMATION:
            return 9
        if opp.category == ImprovementCategory.WASTE:
            return 6
        return 2

    def _score_strategic_alignment(
        self, opp: ImprovementOpportunity, ctx: dict
    ) -> int:
        if opp.category == ImprovementCategory.ALIGNMENT:
            return 9
        # High orphan count means alignment is a live strategic concern
        orphan_count = int(ctx.get("orphan_count", 0))
        if orphan_count > 3:
            return 6
        return 4

    def _score_implementation_effort(
        self, opp: ImprovementOpportunity, ctx: dict
    ) -> int:
        """Higher = LESS effort (inverted). Low-effort → high score."""
        effort_map = {"low": 9, "medium": 5, "high": 2}
        return effort_map.get(opp.estimated_effort.lower(), 5)


def score_and_rank(
    opportunities: list[ImprovementOpportunity],
    context: dict[str, Any] | None = None,
) -> list[ImprovementOpportunity]:
    """Score all opportunities and return sorted by composite descending."""
    engine = ImprovementScoringEngine()
    for opp in opportunities:
        opp.score = engine.score(opp, context)
    return engine.rank(opportunities)


__all__ = [
    "ImprovementScoringEngine",
    "score_and_rank",
]
