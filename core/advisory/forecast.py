"""Forecasting & Prediction — USS-TJR-MSN-0098 WP5.

Estimates future conditions from historical evidence:

    * confidence forecast   * risk forecast   * workload forecast
    * delay forecast        * capacity forecast

GUARDRAIL (non-goal: "no unsupported predictions"): every forecast is a
transparent extrapolation of an observed trend, carries its sample size and an
evidence basis, and returns "insufficient_evidence" when history is too thin.
No black-box prediction; evidence before prediction.

Reuse-only: timeline, signals, core/health/trend_utils. No new store.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_HEALTH = _HERE.parents[1] / "core" / "health"
if str(_HEALTH) not in sys.path:
    sys.path.insert(0, str(_HEALTH))

import timeline as _timeline

try:
    import trend_utils as _trend
except Exception:  # noqa: BLE001
    _trend = None

_MIN_SERIES = 4


@dataclass
class Forecast:
    metric: str
    direction: str               # improving | worsening | stable | insufficient_evidence
    projection: str              # plain-language estimate
    confidence: str              # low | moderate (never "high" — these are extrapolations)
    sample_size: int = 0
    basis: str = ""
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _series_from(kind: str) -> list[float]:
    return [float(e.score) for e in _timeline.load_events(kinds=[kind], newest_first=False)
            if e.score is not None]


def _trend_forecast(metric: str, series: list[float], higher_is_better: bool,
                    improving_msg: str, worsening_msg: str, stable_msg: str) -> Forecast:
    if len(series) < _MIN_SERIES or _trend is None:
        return Forecast(metric, "insufficient_evidence",
                        "Not enough history to forecast — evidence required first.",
                        "low", len(series),
                        basis=f"need ≥{_MIN_SERIES} data points, have {len(series)}")
    direction = _trend.compute_trend(series, higher_is_better=higher_is_better)
    msg = {"improving": improving_msg, "worsening": worsening_msg}.get(direction, stable_msg)
    # Confidence scales modestly with sample size; capped at "moderate".
    confidence = "moderate" if len(series) >= 8 else "low"
    return Forecast(
        metric=metric,
        direction=direction,
        projection=msg,
        confidence=confidence,
        sample_size=len(series),
        basis=f"trend extrapolation over {len(series)} observations",
        evidence=[f"{int(series[0]*100)}% → {int(series[-1]*100)}%"] if all(0 <= v <= 1 for v in series) else [],
    )


def confidence_forecast() -> Forecast:
    return _trend_forecast(
        "advisory_confidence", _series_from("advice"), True,
        "Advisory confidence is likely to keep rising if current inputs hold.",
        "Advisory confidence is likely to keep falling — review evidence quality.",
        "Advisory confidence is likely to stay broadly stable.",
    )


def success_forecast() -> Forecast:
    return _trend_forecast(
        "recommendation_success", _series_from("advisory_outcome"), True,
        "Recommendation success is trending up — likely to continue improving.",
        "Recommendation success is trending down — likely to continue without intervention.",
        "Recommendation success is likely to remain stable.",
    )


def risk_forecast() -> Forecast:
    """Escalation frequency trajectory (higher = more risk)."""
    advice = _timeline.load_events(kinds=["advice"], newest_first=False)
    if len(advice) < _MIN_SERIES:
        return Forecast("escalation_risk", "insufficient_evidence",
                        "Not enough advisory history to forecast risk.", "low", len(advice))
    series = [1.0 if (e.detail or {}).get("escalation_required") else 0.0 for e in advice]
    return _trend_forecast(
        "escalation_risk", series, False,
        "Escalation risk is trending down — fewer high-risk decisions expected.",
        "Escalation risk is trending up — expect more decisions to need escalation.",
        "Escalation risk is likely to remain steady.",
    )


def workload_forecast() -> Forecast:
    """Open-loop accumulation rate as a workload proxy."""
    records = sorted(_timeline.load_events(kinds=["advice"], newest_first=False), key=lambda e: e.ts)
    if len(records) < _MIN_SERIES:
        return Forecast("workload", "insufficient_evidence",
                        "Not enough advisory activity to forecast workload.", "low", len(records))
    # cumulative open-loop count over time
    cum = []
    open_count = 0
    for e in records:
        open_count += 0 if e.outcome else 1
        cum.append(float(open_count))
    return _trend_forecast(
        "workload", cum, False,
        "Open advisory workload is being cleared — load should ease.",
        "Open advisory workload is accumulating — load likely to rise.",
        "Advisory workload is steady.",
    )


def all_forecasts() -> dict[str, Any]:
    forecasts = [confidence_forecast(), success_forecast(), risk_forecast(), workload_forecast()]
    supported = [f for f in forecasts if f.direction != "insufficient_evidence"]
    return {
        "forecasts": [f.to_dict() for f in forecasts],
        "supported_count": len(supported),
        "narrative": (
            f"{len(supported)} of {len(forecasts)} forecasts are evidence-supported; "
            "the rest report insufficient evidence rather than guessing."
        ),
        "note": "Forecasts are transparent trend extrapolations, not guarantees. Advisory only.",
    }


def to_markdown() -> str:
    data = all_forecasts()
    L = ["# Forecasts", "", data["narrative"], ""]
    for f in data["forecasts"]:
        if f["direction"] == "insufficient_evidence":
            L.append(f"- **{f['metric']}**: insufficient evidence (n={f['sample_size']})")
        else:
            L.append(f"- **{f['metric']}** ({f['direction']}, {f['confidence']} confidence, "
                     f"n={f['sample_size']}): {f['projection']}")
    L.append(f"\n_{data['note']}_")
    return "\n".join(L)
