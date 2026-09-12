"""Advisory Health — USS-TJR-MSN-0096 WP5.

The system monitors itself. Aggregates the existing calibration + metrics +
signals into a single advisory-health read:

    * recommendation quality   (overall accuracy)
    * confidence trends         (calibration alignment + confidence signal)
    * advisor performance       (officer ranking)
    * outcome effectiveness     (success rate + outcome coverage)

Reuse-only. Pure measurement — no authority.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import calibration as _calibration
import metrics as _metrics
import signals as _signals


def advisory_health() -> dict[str, Any]:
    cal = _calibration.calibration_report()
    met = _metrics.advisory_metrics()
    sigs = _signals.emerging_signals()

    accuracy = cal.get("overall_accuracy")
    alignment = cal.get("confidence_alignment", {}).get("aligned")
    success_rate = met.get("recommendation_success_rate")
    coverage = met["totals"].get("outcome_coverage", 0.0)
    sufficient = cal.get("sufficient_data", False)

    # With too little closed-outcome history, health is "unknown" — never claim
    # "degraded" on an empty dataset (that would be a false alarm).
    if not sufficient:
        score = None
        status = "unknown"
    else:
        components: list[float] = []
        if accuracy is not None:
            components.append(accuracy)
        if success_rate is not None:
            components.append(success_rate)
        if alignment is True:
            components.append(0.9)
        elif alignment is False:
            components.append(0.4)
        components.append(min(1.0, coverage + 0.2))  # coverage rewards closing loops
        score = round(sum(components) / len(components), 3) if components else None
        status = (
            "unknown" if score is None
            else "healthy" if score >= 0.7
            else "watch" if score >= 0.5
            else "degraded"
        )

    worsening = [s.name for s in sigs if s.direction in ("worsening", "increasing")]

    return {
        "score": score,
        "status": status,
        "recommendation_quality": accuracy,
        "confidence_aligned": alignment,
        "outcome_effectiveness": success_rate,
        "outcome_coverage": coverage,
        "advisor_ranking": cal.get("officer_ranking", [])[:5],
        "worsening_signals": worsening,
        "sufficient_data": cal.get("sufficient_data", False),
        "narrative": _narrative(score, status, accuracy, success_rate, worsening, cal.get("sufficient_data")),
    }


def _narrative(score, status, accuracy, success_rate, worsening, sufficient) -> str:
    if not sufficient:
        return ("Advisory health is provisional — not enough closed outcomes yet. "
                "Close loops with /advisory-outcome to make this meaningful.")
    parts = [f"Advisory health: {status}" + (f" ({int(score*100)}/100)" if score is not None else "")]
    if accuracy is not None:
        parts.append(f"recommendation accuracy {int(accuracy*100)}%")
    if success_rate is not None:
        parts.append(f"outcome success {int(success_rate*100)}%")
    if worsening:
        parts.append("worsening: " + ", ".join(worsening))
    return "; ".join(parts) + "."


def to_markdown(health: dict[str, Any] | None = None) -> str:
    h = health or advisory_health()
    L = ["# Advisory Health", "", h["narrative"], ""]
    if h["advisor_ranking"]:
        L.append("## Advisor Ranking")
        for r in h["advisor_ranking"]:
            L.append(f"- {r['officer']}: {int(r['accuracy']*100)}% (n={r['samples']})")
    return "\n".join(L)
