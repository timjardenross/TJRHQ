"""Delivery Forecasting Engine (EXEC-007 WP5).

Estimates delivery outcomes before failure occurs, from mission velocity,
dependency health, blockers, capacity, escalations, review outcomes, and
initiative health.

Outputs: Likely On Track / At Risk / Likely Delayed / Critical, with a
confidence score.

Reuse: initiatives (EXEC-006), WBS (WP2), dependencies (WP1), critical path
(WP3). Read-only computation. No new tables.

Public API:
    DeliveryForecast
    ForecastResult
    forecast_initiative(initiative_id, inputs) -> ForecastResult | None
    forecast_all(inputs)                       -> list[ForecastResult]
    format_forecast(result)                    -> str
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

from lib.strategy.initiatives import get_initiative, list_initiatives, InitiativeHealth, OutcomeTrend
from lib.program.wbs import build_wbs, InitiativeWBS
from lib.program.critical_path import compute_critical_path


class DeliveryForecast(str, Enum):
    ON_TRACK       = "likely_on_track"
    AT_RISK        = "at_risk"
    LIKELY_DELAYED = "likely_delayed"
    CRITICAL       = "critical"


@dataclass
class ForecastResult:
    initiative_id: str
    title: str
    forecast: DeliveryForecast
    confidence: float                     # 0.0–1.0
    velocity: float = 0.0                 # completion rate
    blocker_count: int = 0
    signals: list[str] = field(default_factory=list)

    @property
    def forecast_label(self) -> str:
        return self.forecast.value.replace("_", " ").title()


# Numeric scoring: higher score = worse delivery outlook
_FORECAST_BANDS = [
    (0, DeliveryForecast.ON_TRACK),
    (3, DeliveryForecast.AT_RISK),
    (6, DeliveryForecast.LIKELY_DELAYED),
    (9, DeliveryForecast.CRITICAL),
]


def _band(score: int) -> DeliveryForecast:
    chosen = DeliveryForecast.ON_TRACK
    for threshold, band in _FORECAST_BANDS:
        if score >= threshold:
            chosen = band
    return chosen


def forecast_initiative(
    initiative_id: str,
    inputs: dict[str, Any] | None = None,
) -> ForecastResult | None:
    """Forecast delivery for a single initiative."""
    inputs = inputs or {}
    init = get_initiative(initiative_id)
    wbs: InitiativeWBS | None = build_wbs(initiative_id)
    if init is None or wbs is None:
        return None

    signals: list[str] = []
    score = 0

    # Velocity — completion rate of the portfolio
    velocity = wbs.completion_rate
    if wbs.total_missions == 0:
        score += 2
        signals.append("no missions linked — delivery undefined")
    elif velocity < 0.2 and wbs.total_missions >= 3:
        score += 2
        signals.append(f"low velocity ({round(velocity*100)}% complete)")
    elif velocity >= 0.6:
        score -= 1
        signals.append(f"strong velocity ({round(velocity*100)}% complete)")

    # Blockers
    blockers = len(wbs.blocked_missions)
    if blockers >= 2:
        score += 3
        signals.append(f"{blockers} blocked mission(s)")
    elif blockers == 1:
        score += 1
        signals.append("1 blocked mission")

    # Dependency / critical path health
    try:
        cp = compute_critical_path(initiative_id)
        if cp and cp.blocked_path:
            score += 3
            signals.append(f"{len(cp.blocked_path)} blocker(s) on the critical path")
        elif cp and cp.sequencing_risks:
            score += 1
            signals.append("sequencing risk on critical path")
    except Exception:
        pass

    # Capacity
    capacity = str(inputs.get("capacity_status", "") or "")
    if capacity == "Red":
        score += 2
        signals.append("Red capacity constrains delivery")
    elif capacity == "Amber":
        score += 1

    # Escalations
    escalations = int(inputs.get("escalations", 0) or 0)
    if escalations >= 2:
        score += 1
        signals.append(f"{escalations} active escalation(s)")

    # Initiative outcome health & trend (EXEC-006)
    if init.health == InitiativeHealth.RED:
        score += 2
        signals.append("initiative health Red")
    elif init.health == InitiativeHealth.GREEN:
        score -= 1
    if init.trend == OutcomeTrend.DECLINING:
        score += 1
        signals.append("outcome trend declining")
    elif init.trend == OutcomeTrend.IMPROVING:
        score -= 1

    # Review compliance
    if init.review_overdue:
        score += 1
        signals.append("review overdue")

    score = max(0, score)
    forecast = _band(score)

    # Confidence: more signals + more missions = more confident forecast
    base_conf = 0.5 + min(0.3, 0.05 * len(signals)) + min(0.15, 0.03 * wbs.total_missions)
    confidence = round(min(0.95, base_conf), 2)

    result = ForecastResult(
        initiative_id=initiative_id,
        title=init.title,
        forecast=forecast,
        confidence=confidence,
        velocity=velocity,
        blocker_count=blockers,
        signals=signals,
    )
    log.info(
        "[program.forecasting] %s: %s (score=%d, conf=%.2f)",
        initiative_id, forecast.value, score, confidence,
    )
    return result


def forecast_all(inputs: dict[str, Any] | None = None) -> list[ForecastResult]:
    """Forecast all active initiatives, worst outlook first."""
    results: list[ForecastResult] = []
    for init in list_initiatives(include_closed=False):
        r = forecast_initiative(init.initiative_id, inputs)
        if r:
            results.append(r)
    order = {
        DeliveryForecast.CRITICAL: 0, DeliveryForecast.LIKELY_DELAYED: 1,
        DeliveryForecast.AT_RISK: 2, DeliveryForecast.ON_TRACK: 3,
    }
    results.sort(key=lambda r: order.get(r.forecast, 9))
    return results


def format_forecast(result: ForecastResult) -> str:
    icon = {
        DeliveryForecast.ON_TRACK: ":large_green_circle:",
        DeliveryForecast.AT_RISK: ":large_yellow_circle:",
        DeliveryForecast.LIKELY_DELAYED: ":large_orange_circle:",
        DeliveryForecast.CRITICAL: ":red_circle:",
    }.get(result.forecast, ":white_circle:")
    head = f"{icon} *{result.title[:55]}* — {result.forecast_label} ({result.confidence:.0%} conf)"
    if result.signals:
        return head + "\n    " + "; ".join(result.signals[:3])
    return head


__all__ = [
    "DeliveryForecast",
    "ForecastResult",
    "forecast_initiative",
    "forecast_all",
    "format_forecast",
]
