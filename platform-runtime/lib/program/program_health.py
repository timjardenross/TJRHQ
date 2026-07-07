"""Program Health Framework (EXEC-007 WP6).

Measures execution quality across an initiative's program of work, combining
eight indicators into a Green / Amber / Red health classification:

  Dependency Health · Blocker Count · Mission Progress · Capacity Impact ·
  Risk Level · Forecast Confidence · Outcome Progress · Review Compliance

Distinct from EXEC-006 initiative *outcome* health (are we achieving the goal?)
— this is *execution* health (are we delivering well?).

Reuse: WBS (WP2), critical path (WP3), forecasting (WP5), initiatives +
outcomes (EXEC-006). Read-only. No new tables.

Public API:
    ProgramHealth
    assess_program_health(initiative_id, inputs) -> ProgramHealth | None
    assess_all_program_health(inputs)            -> list[ProgramHealth]
    format_program_health(ph)                    -> str
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lib.strategy.initiatives import get_initiative, list_initiatives, InitiativeHealth
from lib.program.wbs import build_wbs, InitiativeWBS
from lib.program.critical_path import compute_critical_path
from lib.program.forecasting import forecast_initiative, DeliveryForecast


@dataclass
class ProgramHealth:
    initiative_id: str
    title: str
    health: str = "unknown"           # green | amber | red | unknown
    score: float = 0.0                # 0.0 (perfect) – higher is worse
    indicators: dict[str, str] = field(default_factory=dict)
    summary: str = ""

    @property
    def is_red(self) -> bool:
        return self.health == "red"


def assess_program_health(
    initiative_id: str,
    inputs: dict[str, Any] | None = None,
) -> ProgramHealth | None:
    """Assess execution health across the eight program indicators."""
    inputs = inputs or {}
    init = get_initiative(initiative_id)
    wbs: InitiativeWBS | None = build_wbs(initiative_id)
    if init is None or wbs is None:
        return None

    ind: dict[str, str] = {}
    penalty = 0.0

    # 1. Dependency health (critical path / blocked path)
    cp = compute_critical_path(initiative_id)
    if cp and cp.blocked_path:
        ind["dependency_health"] = "red"; penalty += 2
    elif cp and cp.sequencing_risks:
        ind["dependency_health"] = "amber"; penalty += 1
    else:
        ind["dependency_health"] = "green"

    # 2. Blocker count
    blockers = len(wbs.blocked_missions)
    if blockers >= 2:
        ind["blocker_count"] = "red"; penalty += 2
    elif blockers == 1:
        ind["blocker_count"] = "amber"; penalty += 1
    else:
        ind["blocker_count"] = "green"

    # 3. Mission progress (velocity)
    vel = wbs.completion_rate
    if wbs.total_missions and vel < 0.2:
        ind["mission_progress"] = "red"; penalty += 1.5
    elif vel < 0.5:
        ind["mission_progress"] = "amber"; penalty += 0.5
    else:
        ind["mission_progress"] = "green"

    # 4. Capacity impact
    capacity = str(inputs.get("capacity_status", "") or "")
    if capacity == "Red":
        ind["capacity_impact"] = "red"; penalty += 1.5
    elif capacity == "Amber":
        ind["capacity_impact"] = "amber"; penalty += 0.5
    else:
        ind["capacity_impact"] = "green"

    # 5. Risk level (resilience proxy + negative findings)
    resilience = str(inputs.get("resilience_risk", "") or "")
    negative = int(inputs.get("negative_findings", 0) or 0)
    if resilience == "RED" or negative >= 2:
        ind["risk_level"] = "red"; penalty += 1.5
    elif resilience == "AMBER" or negative == 1:
        ind["risk_level"] = "amber"; penalty += 0.5
    else:
        ind["risk_level"] = "green"

    # 6. Forecast confidence
    fc = forecast_initiative(initiative_id, inputs)
    if fc:
        if fc.forecast in (DeliveryForecast.CRITICAL, DeliveryForecast.LIKELY_DELAYED):
            ind["forecast"] = "red"; penalty += 2
        elif fc.forecast == DeliveryForecast.AT_RISK:
            ind["forecast"] = "amber"; penalty += 1
        else:
            ind["forecast"] = "green"
    else:
        ind["forecast"] = "unknown"

    # 7. Outcome progress (EXEC-006 initiative health)
    if init.health == InitiativeHealth.RED:
        ind["outcome_progress"] = "red"; penalty += 1.5
    elif init.health == InitiativeHealth.AMBER:
        ind["outcome_progress"] = "amber"; penalty += 0.5
    else:
        ind["outcome_progress"] = "green" if init.health == InitiativeHealth.GREEN else "unknown"

    # 8. Review compliance
    ind["review_compliance"] = "red" if init.review_overdue else "green"
    if init.review_overdue:
        penalty += 0.5

    # Classification
    if penalty >= 5:
        health = "red"
    elif penalty >= 2:
        health = "amber"
    else:
        health = "green"

    reds = [k for k, v in ind.items() if v == "red"]
    summary = (
        f"{health.upper()} (score {round(penalty, 1)}); "
        + (f"red: {', '.join(reds)}" if reds else "no red indicators")
    )

    ph = ProgramHealth(
        initiative_id=initiative_id,
        title=init.title,
        health=health,
        score=round(penalty, 1),
        indicators=ind,
        summary=summary,
    )
    log.info("[program.health] %s: %s", initiative_id, summary)
    return ph


def assess_all_program_health(inputs: dict[str, Any] | None = None) -> list[ProgramHealth]:
    out: list[ProgramHealth] = []
    for init in list_initiatives(include_closed=False):
        ph = assess_program_health(init.initiative_id, inputs)
        if ph:
            out.append(ph)
    order = {"red": 0, "amber": 1, "green": 2, "unknown": 3}
    out.sort(key=lambda p: order.get(p.health, 9))
    return out


def format_program_health(ph: ProgramHealth) -> str:
    icon = {"green": ":large_green_circle:", "amber": ":large_yellow_circle:", "red": ":red_circle:"}.get(ph.health, ":white_circle:")
    return f"{icon} *{ph.title[:55]}* — {ph.summary}"


__all__ = [
    "ProgramHealth",
    "assess_program_health",
    "assess_all_program_health",
    "format_program_health",
]
