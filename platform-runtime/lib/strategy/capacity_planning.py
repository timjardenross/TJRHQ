"""Capacity & Resource Planning (EXEC-010 WP4).

Assesses delivery capacity across the portfolio at initiative level.
Tracks initiative demand vs available capacity and produces a utilisation
profile. Reuses EXEC-008 tradeoff analysis and EXEC-007 resource conflict
detection for mission-level depth.

Capacity states:
  UNDER_CAPACITY  — significant unused capacity available
  BALANCED        — demand approximately matches supply
  CONSTRAINED     — demand exceeds comfortable capacity
  OVERLOADED      — demand severely exceeds capacity; delivery at risk

No new tables. Reads from existing missions, initiatives, and resource
conflict data. Optionally reads human systems capacity entry.

Public API:
    CapacityState, InitiativeCapacityDemand
    PortfolioCapacityPlan
    assess_portfolio_capacity(capacity_status, inputs)  -> PortfolioCapacityPlan
    format_capacity_plan(plan)                          -> str
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


class CapacityState(str, Enum):
    UNDER_CAPACITY = "under_capacity"
    BALANCED       = "balanced"
    CONSTRAINED    = "constrained"
    OVERLOADED     = "overloaded"


@dataclass
class InitiativeCapacityDemand:
    initiative_id: str
    title: str
    mission_count: int = 0          # active missions
    blocked_count: int = 0          # blocked missions
    owner_count: int = 0            # distinct owners
    demand_score: float = 0.0       # relative demand index (0–10)
    forecast: str = "unknown"


@dataclass
class PortfolioCapacityPlan:
    state: CapacityState = CapacityState.BALANCED
    total_active_missions: int = 0
    total_blocked_missions: int = 0
    total_initiatives: int = 0
    utilisation_pct: float = 0.0     # estimated 0.0–1.0+
    overloaded_owners: list[str] = field(default_factory=list)
    demand_by_initiative: list[InitiativeCapacityDemand] = field(default_factory=list)
    resource_conflict_count: int = 0
    signals: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


def assess_portfolio_capacity(
    capacity_status: str = "Unknown",
    inputs: dict[str, Any] | None = None,
) -> PortfolioCapacityPlan:
    """Assess portfolio-wide delivery capacity."""
    inputs = inputs or {}
    plan = PortfolioCapacityPlan()

    # ── Initiative + mission load ─────────────────────────────────────────────
    try:
        from lib.strategy.initiatives import list_initiatives
        from lib.program.wbs import build_wbs
        from lib.program.forecasting import forecast_initiative

        initiatives = list_initiatives(include_closed=False)
        plan.total_initiatives = len(initiatives)
        owners_seen: dict[str, int] = {}
        demand_items: list[InitiativeCapacityDemand] = []

        for init in initiatives:
            demand = InitiativeCapacityDemand(
                initiative_id=init.initiative_id,
                title=getattr(init, "title", init.initiative_id),
            )
            try:
                wbs = build_wbs(init.initiative_id)
                if wbs:
                    demand.mission_count = wbs.total_missions
                    demand.blocked_count = len(wbs.blocked_missions)
                    plan.total_active_missions += wbs.total_missions
                    plan.total_blocked_missions += len(wbs.blocked_missions)
                    for owner in (getattr(m, "owner", "") for m in (wbs.missions or [])):
                        if owner:
                            owners_seen[owner] = owners_seen.get(owner, 0) + 1
            except Exception:
                pass

            try:
                fc = forecast_initiative(init.initiative_id)
                if fc:
                    demand.forecast = fc.forecast.value
            except Exception:
                pass

            demand.demand_score = min(10.0, demand.mission_count * 0.8 + demand.blocked_count * 2.0)
            demand_items.append(demand)

        plan.demand_by_initiative = sorted(demand_items, key=lambda d: d.demand_score, reverse=True)

        # Owners with > 3 concurrent missions = overloaded
        plan.overloaded_owners = [owner for owner, count in owners_seen.items() if count > 3]

    except Exception as exc:
        log.debug("[capacity_planning] initiative/wbs data unavailable: %s", exc)

    # ── Resource conflict count ───────────────────────────────────────────────
    try:
        from lib.program.resource_conflict import detect_resource_conflicts
        conflicts = detect_resource_conflicts(capacity_status)
        plan.resource_conflict_count = len(conflicts)
        high_conflicts = [c for c in conflicts if c.severity == "high"]
        if high_conflicts:
            plan.signals.append(f"{len(high_conflicts)} high-severity resource conflict(s)")
    except Exception as exc:
        log.debug("[capacity_planning] resource conflict data unavailable: %s", exc)

    # ── Utilisation estimate ──────────────────────────────────────────────────
    # Heuristic: base utilisation from capacity status, adjusted for blocked/conflicts
    base_util = {"Green": 0.60, "Amber": 0.80, "Red": 1.05, "Unknown": 0.70}.get(capacity_status, 0.70)
    if plan.total_blocked_missions > 3:
        base_util += 0.10
    if plan.overloaded_owners:
        base_util += len(plan.overloaded_owners) * 0.05
    if plan.resource_conflict_count > 2:
        base_util += 0.08
    plan.utilisation_pct = round(min(base_util, 1.5), 2)

    # ── State classification ──────────────────────────────────────────────────
    if plan.utilisation_pct >= 1.20:
        plan.state = CapacityState.OVERLOADED
    elif plan.utilisation_pct >= 0.90:
        plan.state = CapacityState.CONSTRAINED
    elif plan.utilisation_pct >= 0.55:
        plan.state = CapacityState.BALANCED
    else:
        plan.state = CapacityState.UNDER_CAPACITY

    # ── Signals and recommendations ───────────────────────────────────────────
    if plan.state == CapacityState.OVERLOADED:
        plan.signals.append("Portfolio delivery capacity severely exceeded")
        plan.recommendations.append("Pause or terminate lowest-priority initiatives to reduce load")
        plan.recommendations.append("Resolve blocked missions to release capacity")
    elif plan.state == CapacityState.CONSTRAINED:
        plan.signals.append("Portfolio delivery capacity constrained")
        plan.recommendations.append("Defer new initiatives until capacity frees")
    if plan.overloaded_owners:
        plan.signals.append(f"{len(plan.overloaded_owners)} owner(s) carrying >3 concurrent missions")
        plan.recommendations.append("Redistribute mission assignments across team")
    if plan.total_blocked_missions > 5:
        plan.signals.append(f"{plan.total_blocked_missions} missions blocked portfolio-wide")
        plan.recommendations.append("Priority: unblock stalled missions before new starts")

    # Reuse EXEC-008 tradeoff to detect displacement risk
    if plan.state in (CapacityState.CONSTRAINED, CapacityState.OVERLOADED):
        try:
            from lib.strategy.tradeoffs import analyse_tradeoff
            from lib.strategy.prioritisation import rank_initiatives
            ranked = rank_initiatives(inputs)
            if ranked:
                top_id = ranked[0].initiative_id
                ta = analyse_tradeoff(top_id)
                if ta and ta.displaced_count >= 2:
                    plan.signals.append(
                        f"Accelerating top initiative displaces {ta.displaced_count} other(s)"
                    )
        except Exception:
            pass

    log.info(
        "[capacity_planning] state=%s util=%.0f%% missions=%d blocked=%d conflicts=%d",
        plan.state.value, plan.utilisation_pct * 100,
        plan.total_active_missions, plan.total_blocked_missions,
        plan.resource_conflict_count,
    )
    return plan


def format_capacity_plan(plan: PortfolioCapacityPlan) -> str:
    state_icons = {
        CapacityState.UNDER_CAPACITY: ":large_blue_circle:",
        CapacityState.BALANCED: ":large_green_circle:",
        CapacityState.CONSTRAINED: ":large_yellow_circle:",
        CapacityState.OVERLOADED: ":red_circle:",
    }
    icon = state_icons.get(plan.state, "•")
    lines = [
        f"*Portfolio Capacity Plan:* {icon} {plan.state.value.replace('_', ' ').upper()}",
        f"  Utilisation: {plan.utilisation_pct:.0%} | "
        f"{plan.total_initiatives} initiatives | "
        f"{plan.total_active_missions} missions | "
        f"{plan.total_blocked_missions} blocked",
    ]
    if plan.overloaded_owners:
        lines.append(f"  :warning: Overloaded owners: {', '.join(plan.overloaded_owners[:4])}")
    if plan.signals:
        for s in plan.signals[:3]:
            lines.append(f"  · {s}")
    if plan.recommendations:
        lines.append("  *Recommendations:*")
        for r in plan.recommendations[:3]:
            lines.append(f"    :white_square_button: {r}")
    if plan.demand_by_initiative:
        top = plan.demand_by_initiative[0]
        lines.append(f"  Highest demand: {top.title[:40]} (score {top.demand_score:.1f})")
    return "\n".join(lines)


__all__ = [
    "CapacityState",
    "InitiativeCapacityDemand",
    "PortfolioCapacityPlan",
    "assess_portfolio_capacity",
    "format_capacity_plan",
]
