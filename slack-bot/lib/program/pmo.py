"""Number One Program Management Office + Executive Delivery Review
(EXEC-007 WP7 / WP8).

WP7 — Expands Number One from mission coordination to program coordination.
The PMO continuously answers:
  What is blocked? What is at risk? What should be sequenced differently?
  What requires intervention? What threatens strategic outcomes?

WP8 — Executive Delivery Review: a delivery-focused executive review package
(critical dependencies, blocked work, resource conflicts, delivery risks,
forecast changes, capacity constraints, recommended interventions).

Number One coordinates execution — not merely assignment (D-063).

Reuse: all EXEC-007 engines + EXEC-006 initiatives + the Number One execution
engine. No new tables.

Public API:
    InterventionRecommendation, ProgramPortfolio, ExecutiveDeliveryReview
    coordinate_programs(inputs)              -> ProgramPortfolio
    run_executive_delivery_review(inputs)    -> ExecutiveDeliveryReview
    format_program_portfolio(portfolio)      -> str
    format_delivery_review(review)           -> str
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

from lib.strategy.initiatives import list_initiatives
from lib.program.wbs import build_all_wbs, InitiativeWBS
from lib.program.critical_path import compute_critical_path, CriticalPathResult
from lib.program.forecasting import forecast_all, ForecastResult, DeliveryForecast
from lib.program.resource_conflict import detect_resource_conflicts, ResourceConflict
from lib.program.program_health import assess_all_program_health, ProgramHealth
from lib.program.delivery_risk import detect_delivery_risks, DeliveryRisk


@dataclass
class InterventionRecommendation:
    initiative_id: str
    action: str           # unblock | resequence | reallocate | pause | escalate | review
    reason: str
    urgency: str          # high | medium | low
    route_to: str = "number_one"


@dataclass
class ProgramPortfolio:
    """Number One's PMO view across all initiatives."""
    program_health: list[ProgramHealth] = field(default_factory=list)
    forecasts: list[ForecastResult] = field(default_factory=list)
    delivery_risks: list[DeliveryRisk] = field(default_factory=list)
    resource_conflicts: list[ResourceConflict] = field(default_factory=list)
    blocked_work: list[str] = field(default_factory=list)          # mission ids
    critical_paths: dict[str, CriticalPathResult] = field(default_factory=dict)
    interventions: list[InterventionRecommendation] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.utcnow)

    # ── The five questions the PMO answers ────────────────────────────────────
    @property
    def what_is_blocked(self) -> list[str]:
        return self.blocked_work

    @property
    def what_is_at_risk(self) -> list[ForecastResult]:
        return [f for f in self.forecasts if f.forecast in (
            DeliveryForecast.AT_RISK, DeliveryForecast.LIKELY_DELAYED, DeliveryForecast.CRITICAL)]

    @property
    def what_threatens_outcomes(self) -> list[DeliveryRisk]:
        return [r for r in self.delivery_risks if r.threatens_outcome]

    @property
    def red_count(self) -> int:
        return len([p for p in self.program_health if p.health == "red"])


def coordinate_programs(inputs: dict[str, Any] | None = None) -> ProgramPortfolio:
    """Run the full PMO coordination pass across the initiative portfolio."""
    inputs = inputs or {}
    portfolio = ProgramPortfolio()

    initiatives = list_initiatives(include_closed=False)
    if not initiatives:
        return portfolio

    portfolio.program_health = assess_all_program_health(inputs)
    portfolio.forecasts = forecast_all(inputs)
    portfolio.delivery_risks = detect_delivery_risks(inputs)
    portfolio.resource_conflicts = detect_resource_conflicts(str(inputs.get("capacity_status", "Unknown")))

    all_wbs: list[InitiativeWBS] = build_all_wbs()
    for wbs in all_wbs:
        portfolio.blocked_work.extend(m["id"] for m in wbs.blocked_missions)
        cp = compute_critical_path(wbs.initiative_id)
        if cp and cp.has_critical_path:
            portfolio.critical_paths[wbs.initiative_id] = cp

    portfolio.interventions = _recommend_interventions(portfolio)

    log.info(
        "[program.pmo] Portfolio: %d initiatives, %d red, %d blocked, %d risks, %d interventions",
        len(initiatives), portfolio.red_count, len(portfolio.blocked_work),
        len(portfolio.delivery_risks), len(portfolio.interventions),
    )
    return portfolio


def _recommend_interventions(portfolio: ProgramPortfolio) -> list[InterventionRecommendation]:
    """Translate signals into concrete delivery interventions."""
    recs: list[InterventionRecommendation] = []

    # Blockers on critical paths → unblock (high urgency)
    for init_id, cp in portfolio.critical_paths.items():
        if cp.blocked_path:
            recs.append(InterventionRecommendation(
                initiative_id=init_id, action="unblock",
                reason=f"{len(cp.blocked_path)} blocker(s) on critical path: {', '.join(cp.blocked_path[:3])}",
                urgency="high", route_to="xo",
            ))
        elif cp.sequencing_risks:
            recs.append(InterventionRecommendation(
                initiative_id=init_id, action="resequence",
                reason=cp.sequencing_risks[0],
                urgency="medium",
            ))

    # Critical / delayed forecasts → escalate or review
    for fc in portfolio.what_is_at_risk:
        if fc.forecast == DeliveryForecast.CRITICAL:
            recs.append(InterventionRecommendation(
                initiative_id=fc.initiative_id, action="escalate",
                reason=f"forecast CRITICAL: {'; '.join(fc.signals[:2])}",
                urgency="high", route_to="captain",
            ))
        elif fc.forecast == DeliveryForecast.LIKELY_DELAYED:
            recs.append(InterventionRecommendation(
                initiative_id=fc.initiative_id, action="review",
                reason="likely delayed — schedule a delivery review",
                urgency="medium", route_to="xo",
            ))

    # Resource conflicts → reallocate / pause
    for conf in portfolio.resource_conflicts:
        if conf.conflict_type == "owner_overallocation":
            recs.append(InterventionRecommendation(
                initiative_id=(conf.subjects[1] if len(conf.subjects) > 1 else "portfolio"),
                action="reallocate", reason=conf.description, urgency="medium",
            ))
        elif conf.conflict_type == "capacity_constraint" and conf.severity == "high":
            recs.append(InterventionRecommendation(
                initiative_id="portfolio", action="pause",
                reason=conf.description, urgency="high", route_to="xo",
            ))

    # De-dupe by (initiative, action); urgency order
    seen: set[tuple[str, str]] = set()
    unique: list[InterventionRecommendation] = []
    order = {"high": 0, "medium": 1, "low": 2}
    for r in sorted(recs, key=lambda r: order.get(r.urgency, 9)):
        key = (r.initiative_id, r.action)
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    return unique


# ── WP8: Executive Delivery Review ────────────────────────────────────────────

@dataclass
class ExecutiveDeliveryReview:
    critical_dependencies: list[str] = field(default_factory=list)
    blocked_work: list[str] = field(default_factory=list)
    resource_conflicts: list[ResourceConflict] = field(default_factory=list)
    delivery_risks: list[DeliveryRisk] = field(default_factory=list)
    forecast_changes: list[ForecastResult] = field(default_factory=list)
    capacity_constraints: list[str] = field(default_factory=list)
    recommended_interventions: list[InterventionRecommendation] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.utcnow)


def run_executive_delivery_review(inputs: dict[str, Any] | None = None) -> ExecutiveDeliveryReview:
    """Produce the delivery-focused executive review package (WP8)."""
    portfolio = coordinate_programs(inputs)
    review = ExecutiveDeliveryReview()

    # Critical dependencies — bottlenecks across initiatives
    for init_id, cp in portfolio.critical_paths.items():
        for node, deps in cp.bottlenecks[:1]:
            review.critical_dependencies.append(f"{init_id}: {node} blocks {deps} item(s)")

    review.blocked_work = portfolio.blocked_work
    review.resource_conflicts = portfolio.resource_conflicts
    review.delivery_risks = portfolio.delivery_risks
    review.forecast_changes = portfolio.what_is_at_risk
    review.capacity_constraints = [
        c.description for c in portfolio.resource_conflicts if c.conflict_type == "capacity_constraint"
    ]
    review.recommended_interventions = portfolio.interventions
    return review


# ── Formatting ────────────────────────────────────────────────────────────────

def format_program_portfolio(portfolio: ProgramPortfolio) -> str:
    if not portfolio.program_health:
        return "*Program Coordination:* _No initiatives to coordinate._"
    reds = portfolio.red_count
    lines = [
        "*:clipboard: PROGRAM COORDINATION (Number One PMO)*",
        f"  Initiatives: {len(portfolio.program_health)} "
        f"({reds} red) | Blocked: {len(portfolio.blocked_work)} | "
        f"Risks: {len(portfolio.delivery_risks)} | Conflicts: {len(portfolio.resource_conflicts)}",
    ]
    at_risk = portfolio.what_is_at_risk
    if at_risk:
        lines.append(f"  At risk: {', '.join(f.title[:30] for f in at_risk[:3])}")
    if portfolio.interventions:
        lines.append("  *Interventions:*")
        for r in portfolio.interventions[:4]:
            lines.append(f"    [{r.urgency}] {r.action.upper()} {r.initiative_id} — {r.reason[:60]} → {r.route_to}")
    return "\n".join(lines)


def format_delivery_review(review: ExecutiveDeliveryReview) -> str:
    lines = ["*:ship: EXECUTIVE DELIVERY REVIEW*", ""]
    if review.critical_dependencies:
        lines.append(f"*Critical dependencies ({len(review.critical_dependencies)}):*")
        for d in review.critical_dependencies[:4]:
            lines.append(f"  • {d}")
    if review.blocked_work:
        lines.append(f"*Blocked work:* {len(review.blocked_work)} mission(s) — {', '.join(review.blocked_work[:5])}")
    if review.delivery_risks:
        lines.append(f"*Delivery risks ({len(review.delivery_risks)}):*")
        for r in review.delivery_risks[:4]:
            lines.append(f"  • [{r.severity}] {r.risk_type}: {r.detail[:60]}")
    if review.forecast_changes:
        lines.append("*Forecasts at risk:*")
        for f in review.forecast_changes[:4]:
            lines.append(f"  • {f.title[:40]} — {f.forecast_label}")
    if review.capacity_constraints:
        lines.append(f"*Capacity constraints:* {'; '.join(review.capacity_constraints[:2])}")
    if review.recommended_interventions:
        lines.append("*Recommended interventions:*")
        for r in review.recommended_interventions[:5]:
            lines.append(f"  :arrow_right: [{r.urgency}] {r.action.upper()} {r.initiative_id} — {r.reason[:55]}")
    return "\n".join(lines)


__all__ = [
    "InterventionRecommendation",
    "ProgramPortfolio",
    "ExecutiveDeliveryReview",
    "coordinate_programs",
    "run_executive_delivery_review",
    "format_program_portfolio",
    "format_delivery_review",
]
