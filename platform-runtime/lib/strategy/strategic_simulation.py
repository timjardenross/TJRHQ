"""Strategic Simulation Engine (EXEC-009 WP7).

Extends EXEC-008 scenario_planning with six capability-aware simulation types
targeting structural strategic risks:

  Growth                — rapid scale-up pressure on capabilities
  CapacityReduction     — sustained capacity shortfall
  TechnologyFailure     — key system/platform failure or obsolescence
  MarketChange          — strategic context shift requiring rapid pivot
  StrategicOpportunity  — unexpected high-value opportunity requiring capacity
  BlackSwan             — low-probability, high-impact event

Simulations stress-test capability readiness, architectural resilience, and
initiative viability under each scenario. Results surface which capabilities
are resilient, which are fragile, and where investment is most urgent.

No new tables. Results held in-memory (transient). Reads from:
  - list_capabilities()           (WP1)
  - build_capability_map()        (WP2)
  - assess_all_maturity()         (WP3)
  - compute_debt_profile()        (WP5)
  - EXEC-008 scenario_planning    (reused for initiative-level modelling)

Public API:
    SimulationType, SimulationResult, SimulationReport
    run_simulation(sim_type, inputs)   -> SimulationResult
    run_all_simulations(inputs)        -> SimulationReport
    format_simulation_report(report)   -> str
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


class SimulationType(str, Enum):
    GROWTH                = "growth"
    CAPACITY_REDUCTION    = "capacity_reduction"
    TECHNOLOGY_FAILURE    = "technology_failure"
    MARKET_CHANGE         = "market_change"
    STRATEGIC_OPPORTUNITY = "strategic_opportunity"
    BLACK_SWAN            = "black_swan"


# Simulation parameters: velocity_multiplier, capacity_override, benefit_multiplier,
# debt_impact_multiplier (scales debt drag), capability_demand_multiplier
_SIM_PARAMS: dict[SimulationType, dict[str, Any]] = {
    SimulationType.GROWTH: {
        "velocity_multiplier": 1.4,
        "capacity_override": "Red",   # demand exceeds current supply
        "benefit_multiplier": 1.3,
        "debt_impact_multiplier": 2.0,  # debt pain amplified under growth pressure
        "capability_demand_multiplier": 1.5,
    },
    SimulationType.CAPACITY_REDUCTION: {
        "velocity_multiplier": 0.5,
        "capacity_override": "Red",
        "benefit_multiplier": 0.6,
        "debt_impact_multiplier": 1.5,
        "capability_demand_multiplier": 1.0,
    },
    SimulationType.TECHNOLOGY_FAILURE: {
        "velocity_multiplier": 0.4,
        "capacity_override": "Amber",
        "benefit_multiplier": 0.5,
        "debt_impact_multiplier": 3.0,  # debt becomes critical failure vector
        "capability_demand_multiplier": 1.2,
    },
    SimulationType.MARKET_CHANGE: {
        "velocity_multiplier": 0.7,
        "capacity_override": "Amber",
        "benefit_multiplier": 0.8,
        "debt_impact_multiplier": 1.2,
        "capability_demand_multiplier": 1.3,
    },
    SimulationType.STRATEGIC_OPPORTUNITY: {
        "velocity_multiplier": 1.2,
        "capacity_override": "Amber",  # opportunity competes with current capacity
        "benefit_multiplier": 1.5,
        "debt_impact_multiplier": 1.0,
        "capability_demand_multiplier": 1.4,
    },
    SimulationType.BLACK_SWAN: {
        "velocity_multiplier": 0.3,
        "capacity_override": "Red",
        "benefit_multiplier": 0.3,
        "debt_impact_multiplier": 4.0,
        "capability_demand_multiplier": 2.0,
    },
}


@dataclass
class SimulationResult:
    sim_type: SimulationType
    resilient_capabilities: list[str] = field(default_factory=list)   # names
    fragile_capabilities: list[str] = field(default_factory=list)
    initiatives_at_risk_count: int = 0
    initiatives_viable_count: int = 0
    capability_coverage_pct: float = 0.0
    debt_risk_amplified: bool = False
    key_risks: list[str] = field(default_factory=list)
    strategic_actions: list[str] = field(default_factory=list)
    overall_readiness: str = "unknown"    # high | medium | low

    @property
    def label(self) -> str:
        return self.sim_type.value.replace("_", " ").title()


@dataclass
class SimulationReport:
    results: list[SimulationResult] = field(default_factory=list)
    most_resilient_sim: str = ""
    most_fragile_sim: str = ""
    common_fragile_caps: list[str] = field(default_factory=list)

    @property
    def low_readiness_count(self) -> int:
        return sum(1 for r in self.results if r.overall_readiness == "low")


def run_simulation(
    sim_type: SimulationType,
    inputs: dict[str, Any] | None = None,
) -> SimulationResult:
    """Run a single strategic simulation."""
    inputs = inputs or {}
    params = _SIM_PARAMS[sim_type]
    result = SimulationResult(sim_type=sim_type)

    # Load capability data
    caps = []
    maturity_map: dict[str, int] = {}
    try:
        from lib.strategy.capabilities import list_capabilities
        caps = list_capabilities()
        for cap in caps:
            maturity_map[cap.capability_id] = cap.maturity.value
    except Exception as exc:
        log.debug("[strategic_simulation] capabilities unavailable: %s", exc)

    # Capability coverage under demand pressure
    demand_mult = params["capability_demand_multiplier"]
    if caps:
        maturity_threshold = 3 if demand_mult <= 1.2 else 4 if demand_mult <= 1.5 else 5
        resilient = [c for c in caps if maturity_map.get(c.capability_id, 1) >= maturity_threshold]
        fragile = [c for c in caps if maturity_map.get(c.capability_id, 1) < maturity_threshold]
        result.resilient_capabilities = [c.name for c in resilient[:5]]
        result.fragile_capabilities = [c.name for c in fragile[:5]]
        result.capability_coverage_pct = len(resilient) / len(caps) if caps else 0.0

    # Technical debt amplification
    debt_mult = params["debt_impact_multiplier"]
    try:
        from lib.strategy.technical_debt import compute_debt_profile
        dp = compute_debt_profile()
        if debt_mult >= 2.0 and dp.portfolio_risk in ("high", "medium") or (debt_mult >= 3.0):
            result.debt_risk_amplified = True
            result.key_risks.append(
                f"Tech debt amplified {debt_mult:.0f}x under {sim_type.value.replace('_', ' ')}"
            )
    except Exception as exc:
        log.debug("[strategic_simulation] debt unavailable: %s", exc)

    # Reuse EXEC-008 scenario engine for initiative-level impact
    try:
        from lib.strategy.scenario_planning import model_scenario, ScenarioType
        # Map simulation type to closest scenario
        _sim_to_scenario = {
            SimulationType.GROWTH: ScenarioType.BEST_CASE,
            SimulationType.CAPACITY_REDUCTION: ScenarioType.RESOURCE_CONSTRAINED,
            SimulationType.TECHNOLOGY_FAILURE: ScenarioType.STRESSED_CASE,
            SimulationType.MARKET_CHANGE: ScenarioType.STRESSED_CASE,
            SimulationType.STRATEGIC_OPPORTUNITY: ScenarioType.BEST_CASE,
            SimulationType.BLACK_SWAN: ScenarioType.STRATEGIC_SHOCK,
        }
        scenario = _sim_to_scenario[sim_type]
        override_inputs = {**inputs, "capacity_status": params.get("capacity_override", "Amber")}
        sc_result = model_scenario(scenario, override_inputs)
        result.initiatives_at_risk_count = sc_result.initiatives_at_risk + sc_result.initiatives_delayed
        result.initiatives_viable_count = sc_result.initiatives_on_track
        if sc_result.key_risks:
            result.key_risks.extend(sc_result.key_risks[:2])
    except Exception as exc:
        log.debug("[strategic_simulation] scenario model unavailable: %s", exc)

    # Overall readiness
    frag_ratio = len(result.fragile_capabilities) / max(len(caps), 1)
    if result.capability_coverage_pct >= 0.7 and not result.debt_risk_amplified and frag_ratio < 0.3:
        result.overall_readiness = "high"
    elif result.capability_coverage_pct >= 0.4 or (not result.debt_risk_amplified and frag_ratio < 0.6):
        result.overall_readiness = "medium"
    else:
        result.overall_readiness = "low"

    # Strategic actions
    if result.fragile_capabilities:
        result.strategic_actions.append(
            f"Mature {len(result.fragile_capabilities)} fragile capability/ies before {sim_type.value.replace('_', ' ')} scenario"
        )
    if result.debt_risk_amplified:
        result.strategic_actions.append("Reduce critical/high tech debt to limit failure amplification")
    if result.initiatives_at_risk_count > result.initiatives_viable_count:
        result.strategic_actions.append("Reduce initiative count to preserve viable delivery under constraint")

    log.info("[strategic_simulation] %s → readiness: %s | fragile caps: %d",
             sim_type.value, result.overall_readiness, len(result.fragile_capabilities))
    return result


def run_all_simulations(inputs: dict[str, Any] | None = None) -> SimulationReport:
    """Run all 6 strategic simulations and return a consolidated report."""
    report = SimulationReport()
    for sim_type in SimulationType:
        try:
            result = run_simulation(sim_type, inputs)
            report.results.append(result)
        except Exception as exc:
            log.warning("[strategic_simulation] %s failed: %s", sim_type.value, exc)

    if report.results:
        by_readiness = {"high": 2, "medium": 1, "low": 0}
        sorted_r = sorted(report.results, key=lambda r: by_readiness.get(r.overall_readiness, 0))
        report.most_fragile_sim = sorted_r[0].sim_type.value if sorted_r else ""
        report.most_resilient_sim = sorted_r[-1].sim_type.value if sorted_r else ""

        # Find capabilities fragile across multiple simulations
        frag_counts: dict[str, int] = {}
        for r in report.results:
            for cap in r.fragile_capabilities:
                frag_counts[cap] = frag_counts.get(cap, 0) + 1
        report.common_fragile_caps = [c for c, n in frag_counts.items() if n >= 3]

    return report


def format_simulation_report(report: SimulationReport) -> str:
    if not report.results:
        return "_No simulation results available._"
    lines = ["*Strategic Simulation Report:*"]
    readiness_icons = {"high": ":large_green_circle:", "medium": ":large_yellow_circle:", "low": ":red_circle:"}
    for r in report.results:
        icon = readiness_icons.get(r.overall_readiness, "•")
        frag = f" | {len(r.fragile_capabilities)} fragile cap(s)" if r.fragile_capabilities else ""
        lines.append(f"  {icon} {r.label}: {r.overall_readiness} readiness{frag}")
    if report.common_fragile_caps:
        lines.append(f"  :warning: Cross-scenario fragile capabilities: {', '.join(report.common_fragile_caps[:4])}")
    if report.most_fragile_sim:
        lines.append(f"  Lowest readiness scenario: {report.most_fragile_sim.replace('_', ' ').title()}")
    return "\n".join(lines)


__all__ = [
    "SimulationType",
    "SimulationResult",
    "SimulationReport",
    "run_simulation",
    "run_all_simulations",
    "format_simulation_report",
]
