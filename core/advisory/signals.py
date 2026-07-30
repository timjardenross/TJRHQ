"""Emerging Signal Detection — USS-TJR-MSN-0095 WP4.

Notices change over time:

    * worsening trends      (e.g. falling advice confidence / success)
    * improving trends
    * increasing risk        (rising escalation frequency)
    * repeated blockers      (recurring bottleneck themes)

Reuse-only: the unified timeline (timeline.py), the health trend math
(core/health/trend_utils.py) for direction, and patterns.py for repeated
blockers. No new memory store.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_HEALTH = _HERE.parents[1] / "core" / "health"
if str(_HEALTH) not in sys.path:
    sys.path.insert(0, str(_HEALTH))

import timeline as _timeline
import patterns as _patterns

try:
    import trend_utils as _trend
except Exception:  # noqa: BLE001
    _trend = None

_MIN_SERIES = 4


@dataclass
class Signal:
    name: str
    direction: str               # improving | worsening | increasing | stable | flat
    severity: str                # info | watch | concern
    detail: str = ""
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _confidence_signal() -> list[Signal]:
    advice = [e for e in _timeline.load_events(kinds=["advice"], newest_first=False) if e.score is not None]
    if len(advice) < _MIN_SERIES or _trend is None:
        return []
    series = [float(e.score) for e in advice]
    direction = _trend.compute_trend(series, higher_is_better=True)
    severity = "concern" if direction == "worsening" else "info"
    return [Signal(
        name="advisory_confidence",
        direction=direction,
        severity=severity,
        detail=f"Confidence trajectory across {len(series)} recommendations is {direction}.",
        evidence=[f"{int(series[0]*100)}% → {int(series[-1]*100)}%"],
    )]


def _success_signal() -> list[Signal]:
    outs = [e for e in _timeline.load_events(kinds=["advisory_outcome"], newest_first=False) if e.score is not None]
    if len(outs) < _MIN_SERIES or _trend is None:
        return []
    series = [float(e.score) for e in outs]
    direction = _trend.compute_trend(series, higher_is_better=True)
    severity = "concern" if direction == "worsening" else "info"
    return [Signal(
        name="recommendation_success",
        direction=direction,
        severity=severity,
        detail=f"Recommendation success rate is {direction} across {len(series)} closed outcomes.",
    )]


def _risk_signal() -> list[Signal]:
    """Rising escalation frequency over time = increasing risk."""
    advice = _timeline.load_events(kinds=["advice"], newest_first=False)
    if len(advice) < _MIN_SERIES:
        return []
    half = len(advice) // 2
    early = advice[:half]
    late = advice[half:]
    def rate(items):
        return sum(1 for e in items if (e.detail or {}).get("escalation_required")) / max(1, len(items))
    early_r, late_r = rate(early), rate(late)
    if late_r > early_r + 0.1:
        return [Signal(
            name="escalation_risk",
            direction="increasing",
            severity="concern",
            detail=f"Escalation frequency rose from {int(early_r*100)}% to {int(late_r*100)}%.",
        )]
    return []


def _blocker_signal() -> list[Signal]:
    recurring = [p for p in _patterns.detect_patterns() if p.pattern_type == "recurring_risk"]
    return [
        Signal(
            name="repeated_blocker",
            direction="increasing" if p.signal == "caution" else "stable",
            severity="concern" if p.signal == "caution" else "watch",
            detail=p.description,
            evidence=p.evidence,
        )
        for p in recurring[:3]
    ]


_DETECTORS = (_confidence_signal, _success_signal, _risk_signal, _blocker_signal)


def emerging_signals() -> list[Signal]:
    out: list[Signal] = []
    for d in _DETECTORS:
        try:
            out.extend(d())
        except Exception:  # noqa: BLE001
            continue
    sev_rank = {"concern": 2, "watch": 1, "info": 0}
    out.sort(key=lambda s: sev_rank.get(s.severity, 0), reverse=True)
    return out


def to_markdown(sigs: list[Signal] | None = None) -> str:
    sigs = emerging_signals() if sigs is None else sigs
    if not sigs:
        return "No emerging signals — trends are stable or there is insufficient history."
    L = ["# Emerging Signals", ""]
    icon = {"concern": "🔴", "watch": "🟠", "info": "🟢"}
    for s in sigs:
        L.append(f"- {icon.get(s.severity, '•')} **{s.name}** — {s.direction}: {s.detail}")
    return "\n".join(L)
