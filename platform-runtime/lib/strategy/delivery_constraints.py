"""Delivery Constraint Analysis (EXEC-010 WP8).

Identifies portfolio-wide bottlenecks ranked by impact. Analyses:
  - Capability shortages (weak/missing capabilities blocking delivery)
  - Architecture blockers (high-risk current-state entities)
  - Technical debt constraints (critical debt limiting velocity)
  - Resource shortages (owner overallocation, capacity overload)
  - Dependency congestion (blocked chains, circular dependencies)

Reads from EXEC-007 through EXEC-010 modules. No new tables.

Public API:
    ConstraintType, ConstraintSeverity
    DeliveryConstraint
    PortfolioConstraintReport
    analyse_delivery_constraints(inputs)    -> PortfolioConstraintReport
    format_constraint_report(report)        -> str
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


class ConstraintType(str, Enum):
    CAPABILITY_SHORTAGE    = "capability_shortage"
    ARCHITECTURE_BLOCKER   = "architecture_blocker"
    TECH_DEBT              = "tech_debt"
    RESOURCE_SHORTAGE      = "resource_shortage"
    DEPENDENCY_CONGESTION  = "dependency_congestion"


class ConstraintSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"


@dataclass
class DeliveryConstraint:
    constraint_type: ConstraintType
    severity: ConstraintSeverity
    impact_score: float          # 0.0–10.0
    description: str
    affected_ids: list[str] = field(default_factory=list)    # initiative / capability IDs
    recommended_action: str = ""
    escalate_to: str = "number_one"

    @property
    def is_portfolio_blocking(self) -> bool:
        return self.severity == ConstraintSeverity.CRITICAL


@dataclass
class PortfolioConstraintReport:
    constraints: list[DeliveryConstraint] = field(default_factory=list)
    top_constraint: DeliveryConstraint | None = None
    critical_count: int = 0
    high_count: int = 0
    total_impact: float = 0.0

    @property
    def portfolio_risk(self) -> str:
        if self.critical_count >= 2:
            return "high"
        if self.critical_count >= 1 or self.high_count >= 3:
            return "medium"
        return "low"


def analyse_delivery_constraints(
    inputs: dict[str, Any] | None = None,
) -> PortfolioConstraintReport:
    """Analyse and rank all portfolio delivery constraints."""
    inputs = inputs or {}
    capacity_status = str(inputs.get("capacity_status", "Unknown"))
    constraints: list[DeliveryConstraint] = []

    # ── 1. Capability shortages ────────────────────────────────────────────────
    try:
        from lib.strategy.capability_gaps import analyse_capability_gaps, GapType, GapSeverity
        gaps = analyse_capability_gaps()
        threatening = [g for g in gaps if g.gap_type == GapType.THREATENING]
        missing_critical = [g for g in gaps if g.gap_type == GapType.MISSING and g.is_critical]
        weak_active = [g for g in gaps if g.gap_type == GapType.WEAK and g.severity == GapSeverity.HIGH]

        if threatening:
            constraints.append(DeliveryConstraint(
                constraint_type=ConstraintType.CAPABILITY_SHORTAGE,
                severity=ConstraintSeverity.CRITICAL,
                impact_score=9.5,
                description=f"{len(threatening)} weak capability/ies actively threatening initiative delivery",
                affected_ids=[g.capability_id for g in threatening[:5]],
                recommended_action="Urgently resource and mature threatening capabilities",
                escalate_to="captain",
            ))
        if missing_critical:
            constraints.append(DeliveryConstraint(
                constraint_type=ConstraintType.CAPABILITY_SHORTAGE,
                severity=ConstraintSeverity.HIGH,
                impact_score=8.0,
                description=f"{len(missing_critical)} required capabilities not yet built",
                affected_ids=[g.capability_id or g.objective_id for g in missing_critical[:5]],
                recommended_action="Initiate capability build programs for critical gaps",
                escalate_to="xo",
            ))
        if weak_active and not threatening:
            constraints.append(DeliveryConstraint(
                constraint_type=ConstraintType.CAPABILITY_SHORTAGE,
                severity=ConstraintSeverity.MEDIUM,
                impact_score=5.0,
                description=f"{len(weak_active)} active capabilities at Ad Hoc maturity",
                recommended_action="Maturity improvement plan required",
                escalate_to="number_one",
            ))
    except Exception as exc:
        log.debug("[delivery_constraints] capability gaps unavailable: %s", exc)

    # ── 2. Architecture blockers ──────────────────────────────────────────────
    try:
        from lib.strategy.enterprise_architecture import get_architecture_view
        av = get_architecture_view()
        if av.high_risk:
            sev = ConstraintSeverity.CRITICAL if len(av.high_risk) >= 2 else ConstraintSeverity.HIGH
            constraints.append(DeliveryConstraint(
                constraint_type=ConstraintType.ARCHITECTURE_BLOCKER,
                severity=sev,
                impact_score=8.5 if sev == ConstraintSeverity.CRITICAL else 6.5,
                description=f"{len(av.high_risk)} high-risk architecture entity/ies in current state",
                affected_ids=[e.entity_id for e in av.high_risk],
                recommended_action="De-risk or migrate high-risk architecture entities",
                escalate_to="captain" if sev == ConstraintSeverity.CRITICAL else "xo",
            ))
    except Exception as exc:
        log.debug("[delivery_constraints] architecture data unavailable: %s", exc)

    # ── 3. Technical debt constraints ─────────────────────────────────────────
    try:
        from lib.strategy.technical_debt import compute_debt_profile, DebtTrend, DebtSeverity
        dp = compute_debt_profile()
        increasing_critical = [d for d in dp.top_debts
                                if d.trend == DebtTrend.INCREASING and d.severity == DebtSeverity.CRITICAL]
        if dp.critical_count >= 2 or increasing_critical:
            sev = ConstraintSeverity.CRITICAL if dp.critical_count >= 3 else ConstraintSeverity.HIGH
            constraints.append(DeliveryConstraint(
                constraint_type=ConstraintType.TECH_DEBT,
                severity=sev,
                impact_score=7.5 + len(increasing_critical) * 0.5,
                description=(
                    f"Tech debt: {dp.critical_count} critical item(s), "
                    f"{len(increasing_critical)} increasing — limiting delivery velocity"
                ),
                recommended_action="Allocate dedicated capacity to tech debt reduction",
                escalate_to="xo",
            ))
        elif dp.portfolio_risk == "medium":
            constraints.append(DeliveryConstraint(
                constraint_type=ConstraintType.TECH_DEBT,
                severity=ConstraintSeverity.MEDIUM,
                impact_score=5.0,
                description=f"Tech debt portfolio risk medium — avg score {dp.average_score}/10",
                recommended_action="Include tech debt reduction in next initiative planning cycle",
                escalate_to="number_one",
            ))
    except Exception as exc:
        log.debug("[delivery_constraints] tech debt unavailable: %s", exc)

    # ── 4. Resource shortages ─────────────────────────────────────────────────
    try:
        from lib.strategy.capacity_planning import assess_portfolio_capacity, CapacityState
        capacity_plan = assess_portfolio_capacity(capacity_status, inputs)
        if capacity_plan.state == CapacityState.OVERLOADED:
            constraints.append(DeliveryConstraint(
                constraint_type=ConstraintType.RESOURCE_SHORTAGE,
                severity=ConstraintSeverity.CRITICAL,
                impact_score=9.0,
                description=(
                    f"Portfolio OVERLOADED at {capacity_plan.utilisation_pct:.0%} utilisation — "
                    f"{len(capacity_plan.overloaded_owners)} overloaded owner(s)"
                ),
                recommended_action="Immediate capacity intervention — pause or defer initiatives",
                escalate_to="captain",
            ))
        elif capacity_plan.state == CapacityState.CONSTRAINED:
            constraints.append(DeliveryConstraint(
                constraint_type=ConstraintType.RESOURCE_SHORTAGE,
                severity=ConstraintSeverity.HIGH,
                impact_score=6.5,
                description=f"Portfolio CONSTRAINED at {capacity_plan.utilisation_pct:.0%} utilisation",
                recommended_action="No new initiatives until current backlog reduces",
                escalate_to="xo",
            ))
    except Exception as exc:
        log.debug("[delivery_constraints] capacity data unavailable: %s", exc)

    # ── 5. Dependency congestion ──────────────────────────────────────────────
    try:
        from lib.strategy.dependency_management import analyse_dependencies
        dep_report = analyse_dependencies()
        if dep_report.has_circular:
            constraints.append(DeliveryConstraint(
                constraint_type=ConstraintType.DEPENDENCY_CONGESTION,
                severity=ConstraintSeverity.CRITICAL,
                impact_score=9.0,
                description=f"{len(dep_report.circular_chains)} circular dependency chain(s) — deadlock risk",
                recommended_action="Resolve circular dependencies immediately — cannot progress until broken",
                escalate_to="captain",
            ))
        elif dep_report.blocked_initiative_ids:
            sev = ConstraintSeverity.HIGH if len(dep_report.blocked_initiative_ids) >= 3 else ConstraintSeverity.MEDIUM
            constraints.append(DeliveryConstraint(
                constraint_type=ConstraintType.DEPENDENCY_CONGESTION,
                severity=sev,
                impact_score=7.0 if sev == ConstraintSeverity.HIGH else 4.0,
                description=f"{len(dep_report.blocked_initiative_ids)} blocked initiative(s) waiting on dependencies",
                affected_ids=dep_report.blocked_initiative_ids[:5],
                recommended_action="Prioritise unblocking critical path initiatives",
                escalate_to="number_one",
            ))
    except Exception as exc:
        log.debug("[delivery_constraints] dependency data unavailable: %s", exc)

    # ── Build report ──────────────────────────────────────────────────────────
    constraints.sort(key=lambda c: c.impact_score, reverse=True)
    report = PortfolioConstraintReport(constraints=constraints)
    report.top_constraint = constraints[0] if constraints else None
    report.critical_count = sum(1 for c in constraints if c.severity == ConstraintSeverity.CRITICAL)
    report.high_count = sum(1 for c in constraints if c.severity == ConstraintSeverity.HIGH)
    report.total_impact = round(sum(c.impact_score for c in constraints), 1)

    log.info("[delivery_constraints] %d constraint(s) — %d critical, %d high, total impact %.1f",
             len(constraints), report.critical_count, report.high_count, report.total_impact)
    return report


def format_constraint_report(report: PortfolioConstraintReport) -> str:
    if not report.constraints:
        return "_No delivery constraints identified._"
    risk_icons = {
        ConstraintSeverity.CRITICAL: ":rotating_light:",
        ConstraintSeverity.HIGH: ":red_circle:",
        ConstraintSeverity.MEDIUM: ":large_yellow_circle:",
        ConstraintSeverity.LOW: ":large_blue_circle:",
    }
    lines = [
        f"*Portfolio Delivery Constraints ({len(report.constraints)} identified):*",
        f"  Portfolio risk: {report.portfolio_risk.upper()} | "
        f"{report.critical_count} critical · {report.high_count} high",
    ]
    for c in report.constraints[:6]:
        icon = risk_icons.get(c.severity, "•")
        lines.append(f"  {icon} [{c.constraint_type.value.replace('_', ' ').upper()}] {c.description[:80]}")
        if c.recommended_action:
            lines.append(f"    → {c.recommended_action[:70]}")
    return "\n".join(lines)


__all__ = [
    "ConstraintType",
    "ConstraintSeverity",
    "DeliveryConstraint",
    "PortfolioConstraintReport",
    "analyse_delivery_constraints",
    "format_constraint_report",
]
