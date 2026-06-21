"""Scenario Planning (EXEC-008 WP5).

Models how different conditions change expected outcomes for the portfolio.
Stress-tests delivery assumptions before committing capacity.

Scenario types:
  BestCase            — tailwind; +30% velocity, capacity Green
  ExpectedCase        — base delivery assumptions unchanged
  StressedCase        — -30% velocity, 50% more blockers, capacity Amber
  ResourceConstrained — Red capacity with no relief expected
  StrategicShock      — critical resilience event forces portfolio triage

ScenarioResult tracks: initiatives on-track / at-risk / delayed, expected
benefit realisation, capacity utilisation, objectives coverage, and timeline
shift vs expected case.

Reuse: EXEC-006 initiatives + outcomes, WP2 value_realisation,
EXEC-007 forecasting. Read-only. No new tables.

Public API:
    ScenarioType
    ScenarioResult
    model_scenario(scenario_type, inputs) -> ScenarioResult
    compare_scenarios(inputs)             -> list[ScenarioResult]
    format_scenario(result)               -> str
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

from lib.strategy.initiatives import list_initiatives


class ScenarioType(str, Enum):
    BEST_CASE            = "best_case"
    EXPECTED_CASE        = "expected_case"
    STRESSED_CASE        = "stressed_case"
    RESOURCE_CONSTRAINED = "resource_constrained"
    STRATEGIC_SHOCK      = "strategic_shock"


@dataclass
class ScenarioResult:
    scenario: ScenarioType
    label: str
    initiatives_on_track: int
    initiatives_at_risk: int
    initiatives_delayed: int
    expected_benefit_realisation_pct: float   # 0.0–1.0
    capacity_utilisation_pct: float           # 0.0–1.0
    objectives_coverage_pct: float            # fraction of objectives with ≥1 on-track initiative
    timeline_shift_weeks: int                 # delta vs expected case (negative = faster)
    key_risks: list[str] = field(default_factory=list)
    opportunities: list[str] = field(default_factory=list)
    headline: str = ""


# ── Scenario parameter modifiers ──────────────────────────────────────────────

_SCENARIO_PARAMS: dict[ScenarioType, dict[str, Any]] = {
    ScenarioType.BEST_CASE: {
        "velocity_multiplier": 1.3,
        "capacity_override": "Green",
        "benefit_multiplier": 1.2,
        "timeline_shift": -2,
    },
    ScenarioType.EXPECTED_CASE: {
        "velocity_multiplier": 1.0,
        "capacity_override": None,    # use actual capacity
        "benefit_multiplier": 1.0,
        "timeline_shift": 0,
    },
    ScenarioType.STRESSED_CASE: {
        "velocity_multiplier": 0.7,
        "capacity_override": "Amber",
        "benefit_multiplier": 0.75,
        "timeline_shift": 4,
    },
    ScenarioType.RESOURCE_CONSTRAINED: {
        "velocity_multiplier": 0.5,
        "capacity_override": "Red",
        "benefit_multiplier": 0.5,
        "timeline_shift": 8,
    },
    ScenarioType.STRATEGIC_SHOCK: {
        "velocity_multiplier": 0.4,
        "capacity_override": "Red",
        "benefit_multiplier": 0.3,
        "timeline_shift": 12,
    },
}

_SCENARIO_LABELS = {
    ScenarioType.BEST_CASE:            "Best Case",
    ScenarioType.EXPECTED_CASE:        "Expected Case",
    ScenarioType.STRESSED_CASE:        "Stressed Case",
    ScenarioType.RESOURCE_CONSTRAINED: "Resource Constrained",
    ScenarioType.STRATEGIC_SHOCK:      "Strategic Shock",
}


def model_scenario(
    scenario_type: ScenarioType,
    inputs: dict[str, Any] | None = None,
) -> ScenarioResult:
    """Model delivery and value outcomes under the given scenario."""
    inputs = inputs or {}
    params = _SCENARIO_PARAMS[scenario_type]
    label  = _SCENARIO_LABELS[scenario_type]

    cap_override      = params["capacity_override"]
    effective_cap     = cap_override or str(inputs.get("capacity_status", "Unknown"))
    vel_mult          = params["velocity_multiplier"]
    benefit_mult      = params["benefit_multiplier"]

    initiatives = list_initiatives(include_closed=False)
    if not initiatives:
        return ScenarioResult(
            scenario=scenario_type, label=label,
            initiatives_on_track=0, initiatives_at_risk=0, initiatives_delayed=0,
            expected_benefit_realisation_pct=0.0, capacity_utilisation_pct=0.0,
            objectives_coverage_pct=0.0, timeline_shift_weeks=params["timeline_shift"],
            headline="No initiatives — no scenario to model.",
        )

    on_track = 0
    at_risk  = 0
    delayed  = 0
    objectives_with_on_track: set[str] = set()
    all_objectives: set[str] = set()
    total_benefit   = 0.0
    benefit_count   = 0
    key_risks: list[str]    = []
    opportunities: list[str] = []

    for init in initiatives:
        if init.objective_id:
            all_objectives.add(init.objective_id)
        try:
            from lib.program.forecasting import forecast_initiative, DeliveryForecast
            from lib.strategy.value_realisation import assess_initiative_value

            modified_inputs = {**inputs, "capacity_status": effective_cap}
            fr = forecast_initiative(init.initiative_id, modified_inputs)

            # Shift the forecast band based on velocity modifier
            if fr:
                base_band = fr.forecast
                if vel_mult >= 1.2:
                    if base_band == DeliveryForecast.AT_RISK:
                        base_band = DeliveryForecast.ON_TRACK
                    elif base_band == DeliveryForecast.LIKELY_DELAYED:
                        base_band = DeliveryForecast.AT_RISK
                elif vel_mult <= 0.5:
                    # Two-band downgrade for severe scenarios
                    if base_band == DeliveryForecast.ON_TRACK:
                        base_band = DeliveryForecast.LIKELY_DELAYED
                    else:
                        base_band = DeliveryForecast.CRITICAL
                elif vel_mult <= 0.7:
                    if base_band == DeliveryForecast.ON_TRACK:
                        base_band = DeliveryForecast.AT_RISK
                    elif base_band == DeliveryForecast.AT_RISK:
                        base_band = DeliveryForecast.LIKELY_DELAYED
                    elif base_band == DeliveryForecast.LIKELY_DELAYED:
                        base_band = DeliveryForecast.CRITICAL

                if base_band == DeliveryForecast.ON_TRACK:
                    on_track += 1
                    if init.objective_id:
                        objectives_with_on_track.add(init.objective_id)
                elif base_band == DeliveryForecast.AT_RISK:
                    at_risk += 1
                else:
                    delayed += 1
                    if (scenario_type in (ScenarioType.STRESSED_CASE, ScenarioType.STRATEGIC_SHOCK)
                            and init.objective_id):
                        key_risks.append(
                            f"{init.title[:40]} delayed — objective {init.objective_id} at risk"
                        )

            # Benefit realisation under scenario
            vr = assess_initiative_value(init.initiative_id)
            if vr and vr.total_count > 0:
                adjusted = min(1.5, vr.overall_realisation_pct * benefit_mult)
                total_benefit += adjusted
                benefit_count += 1

        except Exception as exc:
            log.debug("[strategy.scenario] initiative %s failed: %s", init.initiative_id, exc)
            at_risk += 1

    # Capacity utilisation proxy under effective capacity
    _cap_util = {"Green": 0.65, "Amber": 0.85, "Red": 1.0}.get(effective_cap, 0.75)
    cap_util = round(min(1.0, _cap_util * (1.0 + max(0.0, 1.0 - vel_mult))), 3)

    obj_cov = round(
        len(objectives_with_on_track) / max(len(all_objectives), 1), 3
    ) if all_objectives else 0.0

    avg_benefit = round(total_benefit / max(benefit_count, 1), 3) if benefit_count else 0.0

    total = len(initiatives)
    if on_track == total:
        headline = f"All {total} initiatives on track"
    elif delayed + at_risk > total // 2:
        headline = f"Portfolio under stress: {delayed} delayed, {at_risk} at risk"
    else:
        headline = f"{on_track}/{total} on track ({at_risk} at risk, {delayed} delayed)"

    if scenario_type == ScenarioType.BEST_CASE and on_track > 0:
        opportunities.append(
            f"Accelerate high-priority initiatives — {on_track} have delivery headroom"
        )
    if scenario_type == ScenarioType.RESOURCE_CONSTRAINED:
        key_risks.append("Critical capacity constraint — prioritise and defer low-value work")
    if scenario_type == ScenarioType.STRATEGIC_SHOCK:
        key_risks.append("Reprioritise portfolio immediately — shock demands triage")
        opportunities.append("Identify resilient initiatives to maintain through shock conditions")

    return ScenarioResult(
        scenario=scenario_type,
        label=label,
        initiatives_on_track=on_track,
        initiatives_at_risk=at_risk,
        initiatives_delayed=delayed,
        expected_benefit_realisation_pct=avg_benefit,
        capacity_utilisation_pct=cap_util,
        objectives_coverage_pct=obj_cov,
        timeline_shift_weeks=params["timeline_shift"],
        key_risks=key_risks[:3],
        opportunities=opportunities[:2],
        headline=headline,
    )


def compare_scenarios(inputs: dict[str, Any] | None = None) -> list[ScenarioResult]:
    """Model all scenario types for side-by-side comparison."""
    results: list[ScenarioResult] = []
    for stype in ScenarioType:
        try:
            results.append(model_scenario(stype, inputs))
        except Exception as exc:
            log.debug("[strategy.scenario] %s failed: %s", stype.value, exc)
    return results


def format_scenario(result: ScenarioResult) -> str:
    _icons = {
        ScenarioType.BEST_CASE:            ":large_green_circle:",
        ScenarioType.EXPECTED_CASE:        ":large_blue_circle:",
        ScenarioType.STRESSED_CASE:        ":large_yellow_circle:",
        ScenarioType.RESOURCE_CONSTRAINED: ":large_orange_circle:",
        ScenarioType.STRATEGIC_SHOCK:      ":red_circle:",
    }
    icon = _icons.get(result.scenario, "•")
    lines = [
        f"{icon} *{result.label}* — {result.headline}",
        f"  On track: {result.initiatives_on_track} | At risk: {result.initiatives_at_risk} | Delayed: {result.initiatives_delayed}",
        f"  Benefit realisation: {result.expected_benefit_realisation_pct:.0%} | Objective coverage: {result.objectives_coverage_pct:.0%}",
    ]
    if result.timeline_shift_weeks > 0:
        lines.append(f"  Timeline shift: +{result.timeline_shift_weeks}w vs expected")
    elif result.timeline_shift_weeks < 0:
        lines.append(f"  Timeline shift: {result.timeline_shift_weeks}w (ahead of expected)")
    if result.key_risks:
        lines.append(f"  Risks: {'; '.join(result.key_risks[:2])}")
    if result.opportunities:
        lines.append(f"  Opportunity: {result.opportunities[0]}")
    return "\n".join(lines)


__all__ = [
    "ScenarioType",
    "ScenarioResult",
    "model_scenario",
    "compare_scenarios",
    "format_scenario",
]
