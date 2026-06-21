"""Portfolio Optimisation Engine (EXEC-008 WP4).

Answers: "Can we deliver this? Should we deliver this?"

Synthesises delivery confidence (EXEC-007 forecasting), strategic priority
(WP3), benefit realisation (WP2), capacity (EXEC-007 resource conflicts),
and program health (EXEC-007) into portfolio-level optimisation decisions.

Decisions: Accelerate / Maintain / Defer / Pause / Terminate

Principle: portfolios are finite. Every investment decision is also a
disinvestment decision. Choosing everything is choosing nothing.

Reuse: WP2 value_realisation, WP3 prioritisation, EXEC-007 forecasting +
program_health. No new tables.

Public API:
    OptimisationDecision
    InitiativeOptimisation
    PortfolioOptimisation
    optimise_initiative(initiative_id, inputs) -> InitiativeOptimisation | None
    optimise_portfolio(inputs)                 -> PortfolioOptimisation
    format_optimisation(opt)                   -> str
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

from lib.strategy.initiatives import list_initiatives, InitiativeHealth


class OptimisationDecision(str, Enum):
    ACCELERATE = "accelerate"
    MAINTAIN   = "maintain"
    DEFER      = "defer"
    PAUSE      = "pause"
    TERMINATE  = "terminate"


@dataclass
class InitiativeOptimisation:
    initiative_id: str
    title: str
    decision: OptimisationDecision
    confidence: str            # low | medium | high
    rationale: str
    priority_score: float = 0.0
    delivery_score: float = 0.0
    value_realisation_pct: float = 0.0
    signals: list[str] = field(default_factory=list)

    @property
    def is_disinvestment(self) -> bool:
        return self.decision in (OptimisationDecision.TERMINATE, OptimisationDecision.PAUSE)


@dataclass
class PortfolioOptimisation:
    decisions: list[InitiativeOptimisation] = field(default_factory=list)
    total: int = 0
    accelerate_count: int = 0
    maintain_count: int = 0
    defer_count: int = 0
    pause_count: int = 0
    terminate_count: int = 0
    capacity_released: int = 0    # estimated mission slots freed by disinvestment
    headline: str = ""

    @property
    def has_recommendations(self) -> bool:
        return bool(self.decisions)


def optimise_initiative(
    initiative_id: str,
    inputs: dict[str, Any] | None = None,
) -> InitiativeOptimisation | None:
    """Generate an optimisation decision for a single initiative."""
    inputs = inputs or {}
    try:
        from lib.strategy.initiatives import get_initiative
        from lib.program.forecasting import forecast_initiative, DeliveryForecast
        from lib.strategy.prioritisation import score_initiative
        from lib.strategy.value_realisation import assess_initiative_value

        init = get_initiative(initiative_id)
        if init is None:
            return None

        signals: list[str] = []

        # Priority (WP3)
        ps = score_initiative(initiative_id, inputs)
        priority = ps.composite_score if ps else 5.0
        if ps and ps.signals:
            signals.extend(ps.signals[:2])

        # Value realisation (WP2)
        value_report = assess_initiative_value(initiative_id)
        realisation_pct = value_report.overall_realisation_pct if value_report else 0.0
        if value_report and value_report.total_count > 0:
            signals.append(f"value: {realisation_pct:.0%} realised")

        # Delivery forecast (EXEC-007)
        forecast_score = 5.0
        forecast_band: DeliveryForecast | None = None
        try:
            fr = forecast_initiative(initiative_id, inputs)
            if fr:
                _band_scores = {
                    DeliveryForecast.ON_TRACK:       9.0,
                    DeliveryForecast.AT_RISK:        6.0,
                    DeliveryForecast.LIKELY_DELAYED: 3.0,
                    DeliveryForecast.CRITICAL:       0.0,
                }
                forecast_score = _band_scores.get(fr.forecast, 5.0)
                forecast_band = fr.forecast
                signals.append(f"forecast: {fr.forecast.value}")
        except Exception:
            pass

        # Program health (EXEC-007)
        program_healthy = True
        try:
            from lib.program.program_health import assess_program_health
            ph = assess_program_health(initiative_id, inputs)
            if ph and getattr(ph, "health", None) == "red":
                program_healthy = False
                signals.append("program health: red")
        except Exception:
            pass

        # ── Decision logic ────────────────────────────────────────────────────
        decision = OptimisationDecision.MAINTAIN
        confidence = "medium"
        rationale = "maintain current investment"

        if priority < 3.0 and realisation_pct < 0.2 and forecast_band == DeliveryForecast.CRITICAL:
            decision, confidence = OptimisationDecision.TERMINATE, "high"
            rationale = "low priority, low value, critical delivery — terminate and recover capacity"
        elif init.is_orphan and priority < 4.0:
            decision, confidence = OptimisationDecision.TERMINATE, "high"
            rationale = "no strategic objective linkage — cannot justify continued investment (D-062)"
        elif forecast_band == DeliveryForecast.CRITICAL and not program_healthy:
            decision, confidence = OptimisationDecision.PAUSE, "medium"
            rationale = "critical delivery and unhealthy program — pause and redesign"
        elif str(inputs.get("capacity_status", "")) == "Red" and priority < 5.0:
            decision, confidence = OptimisationDecision.PAUSE, "medium"
            rationale = "Red capacity + low priority — pause to protect Captain (D-055)"
        elif (priority < 5.0 and forecast_band in
              (DeliveryForecast.AT_RISK, DeliveryForecast.LIKELY_DELAYED)):
            decision, confidence = OptimisationDecision.DEFER, "medium"
            rationale = "low-to-medium priority with delivery uncertainty — defer until capacity stabilises"
        elif (priority >= 7.5 and
              forecast_band in (DeliveryForecast.ON_TRACK, None) and
              realisation_pct >= 0.3):
            decision, confidence = OptimisationDecision.ACCELERATE, "medium"
            rationale = "high priority, on track, value emerging — invest more to capture benefit sooner"
        else:
            confidence = "high" if priority >= 7.0 else ("low" if priority < 4.0 else "medium")
            fb_label = forecast_band.value if forecast_band else "unknown"
            rationale = f"maintain: priority {priority:.1f}/10, forecast {fb_label}"

        return InitiativeOptimisation(
            initiative_id=initiative_id,
            title=init.title,
            decision=decision,
            confidence=confidence,
            rationale=rationale,
            priority_score=priority,
            delivery_score=forecast_score,
            value_realisation_pct=realisation_pct,
            signals=signals,
        )

    except Exception as exc:
        log.debug("[strategy.portfolio_optimisation] optimise failed for %s: %s", initiative_id, exc)
        return None


def optimise_portfolio(inputs: dict[str, Any] | None = None) -> PortfolioOptimisation:
    """Run portfolio optimisation across all active initiatives."""
    decisions: list[InitiativeOptimisation] = []

    for init in list_initiatives(include_closed=False):
        try:
            opt = optimise_initiative(init.initiative_id, inputs)
            if opt:
                decisions.append(opt)
        except Exception as exc:
            log.debug("[strategy.portfolio_optimisation] %s failed: %s", init.initiative_id, exc)

    _order = {
        OptimisationDecision.TERMINATE: 0,
        OptimisationDecision.PAUSE:     1,
        OptimisationDecision.DEFER:     2,
        OptimisationDecision.ACCELERATE:3,
        OptimisationDecision.MAINTAIN:  4,
    }
    decisions.sort(key=lambda d: _order.get(d.decision, 9))

    terminate_count  = sum(1 for d in decisions if d.decision == OptimisationDecision.TERMINATE)
    pause_count      = sum(1 for d in decisions if d.decision == OptimisationDecision.PAUSE)
    defer_count      = sum(1 for d in decisions if d.decision == OptimisationDecision.DEFER)
    accelerate_count = sum(1 for d in decisions if d.decision == OptimisationDecision.ACCELERATE)
    maintain_count   = sum(1 for d in decisions if d.decision == OptimisationDecision.MAINTAIN)

    # Each terminated/paused initiative frees ~2 mission slots (rough estimate)
    capacity_released = (terminate_count + pause_count) * 2

    if terminate_count + pause_count + defer_count > len(decisions) // 2:
        headline = (
            f"Portfolio contraction recommended: "
            f"{terminate_count} terminate, {pause_count} pause, {defer_count} defer"
        )
    elif accelerate_count >= 2:
        headline = f"Selective acceleration: {accelerate_count} initiative(s) ready for increased investment"
    else:
        headline = f"Portfolio stable: {maintain_count} maintain, {accelerate_count} accelerate, {defer_count} defer"

    result = PortfolioOptimisation(
        decisions=decisions,
        total=len(decisions),
        accelerate_count=accelerate_count,
        maintain_count=maintain_count,
        defer_count=defer_count,
        pause_count=pause_count,
        terminate_count=terminate_count,
        capacity_released=capacity_released,
        headline=headline,
    )
    log.info(
        "[strategy.portfolio_optimisation] %d initiatives: terminate=%d, pause=%d, defer=%d, accelerate=%d, maintain=%d",
        len(decisions), terminate_count, pause_count, defer_count, accelerate_count, maintain_count,
    )
    return result


def format_optimisation(opt: PortfolioOptimisation) -> str:
    if not opt.decisions:
        return "*Portfolio Optimisation (D-064):* _No initiatives to optimise._"
    _icons = {
        OptimisationDecision.TERMINATE: ":octagonal_sign:",
        OptimisationDecision.PAUSE:     ":double_vertical_bar:",
        OptimisationDecision.DEFER:     ":clock3:",
        OptimisationDecision.ACCELERATE:":fast_forward:",
        OptimisationDecision.MAINTAIN:  ":arrow_forward:",
    }
    lines = [f"*Portfolio Optimisation (D-064):* {opt.headline}"]
    for d in opt.decisions[:8]:
        icon = _icons.get(d.decision, "•")
        lines.append(
            f"  {icon} *{d.decision.value.upper()}* [{d.confidence}] "
            f"{d.title[:55]} — {d.rationale[:60]}"
        )
    if opt.capacity_released:
        lines.append(
            f"  _Estimated capacity released by disinvestment: ~{opt.capacity_released} mission slot(s)_"
        )
    return "\n".join(lines)


__all__ = [
    "OptimisationDecision",
    "InitiativeOptimisation",
    "PortfolioOptimisation",
    "optimise_initiative",
    "optimise_portfolio",
    "format_optimisation",
]
