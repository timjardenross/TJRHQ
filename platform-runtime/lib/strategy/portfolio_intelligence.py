"""Stop / Continue / Accelerate Engine + Portfolio Intelligence
(EXEC-006 WP5 / WP8).

WP5 — For each initiative, generate a Stop / Pause / Merge / Continue /
Accelerate recommendation from evidence (alignment, outcome achievement,
resource consumption, capacity impact, learning generated, risk reduction).

WP8 — Reason about the portfolio as a whole: overloaded / underfunded
objectives, duplicate / stalled / weak-outcome / strong-outcome initiatives.

Principle: the system should continuously identify work that should stop.

Reuse: initiatives, outcomes, alignment, strategic_objective_progress. No new
tables.

Public API:
    Recommendation, InitiativeRecommendation, PortfolioAnalysis
    recommend_for_initiative(initiative, inputs) -> InitiativeRecommendation
    recommend_all(inputs)                        -> list[InitiativeRecommendation]
    analyse_portfolio()                          -> PortfolioAnalysis
    format_recommendations(recs)                -> str
    format_portfolio(analysis)                  -> str
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.strategy.initiatives import (
    Initiative, InitiativeHealth, OutcomeTrend, list_initiatives, get_linked_missions,
)
from lib.strategy.outcomes import assess_health, compute_progress, HealthAssessment


class Recommendation(str, Enum):
    STOP       = "stop"
    PAUSE      = "pause"
    MERGE      = "merge"
    CONTINUE   = "continue"
    ACCELERATE = "accelerate"


@dataclass
class InitiativeRecommendation:
    initiative_id: str
    title: str
    recommendation: Recommendation
    confidence: str               # low | medium | high
    rationale: str
    health: InitiativeHealth
    evidence: list[str] = field(default_factory=list)

    @property
    def is_disinvestment(self) -> bool:
        return self.recommendation in (Recommendation.STOP, Recommendation.PAUSE, Recommendation.MERGE)


@dataclass
class PortfolioAnalysis:
    overloaded_objectives: list[dict] = field(default_factory=list)
    underfunded_objectives: list[dict] = field(default_factory=list)
    duplicate_initiatives: list[tuple[str, str]] = field(default_factory=list)
    stalled_initiatives: list[str] = field(default_factory=list)
    weak_outcome_initiatives: list[str] = field(default_factory=list)
    strong_outcome_initiatives: list[str] = field(default_factory=list)
    total_initiatives: int = 0

    @property
    def has_findings(self) -> bool:
        return any([
            self.overloaded_objectives, self.underfunded_objectives,
            self.duplicate_initiatives, self.stalled_initiatives,
            self.weak_outcome_initiatives, self.strong_outcome_initiatives,
        ])


# ── WP5: Stop / Continue / Accelerate ─────────────────────────────────────────

def recommend_for_initiative(
    initiative: Initiative,
    inputs: dict[str, Any] | None = None,
) -> InitiativeRecommendation:
    """Generate a portfolio recommendation for a single initiative.

    Evaluation criteria (per mission spec):
      strategic alignment, outcome achievement, resource consumption,
      capacity impact, learning generated, risk reduction, reuse opportunity.
    """
    inputs = inputs or {}
    assessment: HealthAssessment = assess_health(initiative, inputs=inputs)
    progress = assessment.progress
    evidence: list[str] = []

    aligned = not initiative.is_orphan
    pct = progress.progress_pct
    trend = assessment.trend
    capacity = str(inputs.get("capacity_status", "") or "")
    linked = inputs.get("linked_mission_count")
    if linked is None:
        linked = len(get_linked_missions(initiative.initiative_id))

    evidence.append(f"health={assessment.health.value}")
    evidence.append(f"trend={trend.value}")
    if pct is not None:
        evidence.append(progress.progress_label)
    if not aligned:
        evidence.append("no objective linkage")
    if assessment.risk_flags:
        evidence.append(f"{len(assessment.risk_flags)} risk flag(s)")

    rec = Recommendation.CONTINUE
    confidence = "medium"
    reason = "default: continue with monitoring"

    # ── Decision logic ────────────────────────────────────────────────────────
    if not aligned:
        rec, confidence = Recommendation.STOP, "high"
        reason = "no strategic objective — work cannot explain why it exists (D-062)"
    elif progress.achieved:
        rec, confidence = Recommendation.STOP, "high"
        reason = "target outcome achieved — initiative complete, redirect capacity"
    elif pct is not None and pct <= 0.0 and trend == OutcomeTrend.DECLINING:
        rec, confidence = Recommendation.STOP, "high"
        reason = "no progress and declining — disinvest"
    elif assessment.health == InitiativeHealth.RED and trend == OutcomeTrend.DECLINING:
        rec, confidence = Recommendation.PAUSE, "medium"
        reason = "off track and declining — pause pending review/pivot"
    elif capacity == "Red" and assessment.health != InitiativeHealth.GREEN:
        rec, confidence = Recommendation.PAUSE, "medium"
        reason = "Red capacity — pause non-performing initiative to protect the Captain (D-055)"
    elif assessment.health == InitiativeHealth.GREEN and trend == OutcomeTrend.IMPROVING and linked and linked < 3:
        rec, confidence = Recommendation.ACCELERATE, "medium"
        reason = "strong outcomes, improving, under-resourced — invest more"
    elif assessment.health == InitiativeHealth.GREEN:
        rec, confidence = Recommendation.CONTINUE, "high"
        reason = "on track — continue at current investment"
    elif assessment.health == InitiativeHealth.AMBER:
        rec, confidence = Recommendation.CONTINUE, "low"
        reason = "at risk — continue but review closely"

    return InitiativeRecommendation(
        initiative_id=initiative.initiative_id,
        title=initiative.title,
        recommendation=rec,
        confidence=confidence,
        rationale=reason,
        health=assessment.health,
        evidence=evidence,
    )


def recommend_all(inputs: dict[str, Any] | None = None) -> list[InitiativeRecommendation]:
    """Generate recommendations for all active initiatives, disinvestment first."""
    recs: list[InitiativeRecommendation] = []
    for init in list_initiatives(include_closed=False):
        try:
            recs.append(recommend_for_initiative(init, inputs))
        except Exception as exc:
            log.debug("[strategy.portfolio] recommend failed for %s: %s", init.initiative_id, exc)
    order = {
        Recommendation.STOP: 0, Recommendation.PAUSE: 1, Recommendation.MERGE: 2,
        Recommendation.ACCELERATE: 3, Recommendation.CONTINUE: 4,
    }
    recs.sort(key=lambda r: order.get(r.recommendation, 9))
    return recs


# ── WP8: Portfolio intelligence ───────────────────────────────────────────────

def analyse_portfolio() -> PortfolioAnalysis:
    """Reason about the portfolio as a whole."""
    analysis = PortfolioAnalysis()
    initiatives = list_initiatives(include_closed=False)
    analysis.total_initiatives = len(initiatives)

    # Initiative-level signals
    by_objective: dict[str, list[Initiative]] = {}
    for init in initiatives:
        if init.objective_id:
            by_objective.setdefault(init.objective_id, []).append(init)

        progress = compute_progress(init)
        if init.health == InitiativeHealth.GREEN and (progress.progress_pct or 0) >= 0.5:
            analysis.strong_outcome_initiatives.append(init.initiative_id)
        elif init.health == InitiativeHealth.RED or (progress.progress_pct is not None and progress.progress_pct <= 0.1):
            analysis.weak_outcome_initiatives.append(init.initiative_id)

        if init.trend == OutcomeTrend.STABLE and init.review_overdue:
            analysis.stalled_initiatives.append(init.initiative_id)

    # Objective load balance via strategic_objective_progress view
    try:
        from lib.strategy.portfolio_queries import underfunded_objectives, overloaded_objectives
        analysis.underfunded_objectives = underfunded_objectives() or []
        analysis.overloaded_objectives = overloaded_objectives() or []
    except Exception as exc:
        log.debug("[strategy.portfolio] objective load query failed: %s", exc)

    # Objectives carrying many initiatives are overloaded at the initiative layer
    for obj_id, group in by_objective.items():
        if len(group) >= 4:
            analysis.overloaded_objectives.append({"objective_id": obj_id, "initiative_count": len(group)})

    log.info(
        "[strategy.portfolio] %d initiatives | strong: %d | weak: %d | stalled: %d",
        analysis.total_initiatives, len(analysis.strong_outcome_initiatives),
        len(analysis.weak_outcome_initiatives), len(analysis.stalled_initiatives),
    )
    return analysis


# ── Formatting ────────────────────────────────────────────────────────────────

def format_recommendations(recs: list[InitiativeRecommendation]) -> str:
    if not recs:
        return "_No initiative recommendations this cycle._"
    icons = {
        Recommendation.STOP: ":octagonal_sign:", Recommendation.PAUSE: ":double_vertical_bar:",
        Recommendation.MERGE: ":twisted_rightwards_arrows:", Recommendation.CONTINUE: ":arrow_forward:",
        Recommendation.ACCELERATE: ":fast_forward:",
    }
    lines = ["*Stop / Continue / Accelerate:*"]
    for r in recs[:8]:
        icon = icons.get(r.recommendation, "•")
        lines.append(
            f"  {icon} *{r.recommendation.value.upper()}* [{r.confidence}] {r.title[:60]} — {r.rationale}"
        )
    return "\n".join(lines)


def format_portfolio(analysis: PortfolioAnalysis) -> str:
    if not analysis.has_findings:
        return f"*Portfolio:* {analysis.total_initiatives} initiative(s), no structural issues."
    lines = [f"*Portfolio Intelligence:* {analysis.total_initiatives} active initiative(s)"]
    if analysis.strong_outcome_initiatives:
        lines.append(f"  :large_green_circle: {len(analysis.strong_outcome_initiatives)} strong-outcome")
    if analysis.weak_outcome_initiatives:
        lines.append(f"  :red_circle: {len(analysis.weak_outcome_initiatives)} weak-outcome")
    if analysis.stalled_initiatives:
        lines.append(f"  :double_vertical_bar: {len(analysis.stalled_initiatives)} stalled")
    if analysis.overloaded_objectives:
        lines.append(f"  :warning: {len(analysis.overloaded_objectives)} overloaded objective(s)")
    if analysis.underfunded_objectives:
        lines.append(f"  :small_orange_diamond: {len(analysis.underfunded_objectives)} underfunded objective(s)")
    return "\n".join(lines)


__all__ = [
    "Recommendation",
    "InitiativeRecommendation",
    "PortfolioAnalysis",
    "recommend_for_initiative",
    "recommend_all",
    "analyse_portfolio",
    "format_recommendations",
    "format_portfolio",
]
