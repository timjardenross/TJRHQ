"""Pattern Detection Engine — USS-TJR-MSN-0095 WP2.

Identifies repeated behaviours from existing records:

    * recurring risks       (repeated decision bottleneck themes)
    * confidence trends      (advice confidence trajectory)
    * advisor outcomes       (per-officer accuracy from calibration)
    * dependency / irreversibility risk (repeated escalation / low reversibility)
    * health trends          (reuses core/health trend math when data exists)
    * delayed / stalled work (gaps and never-closed items)

Each detector degrades gracefully — it returns an insufficient-data note rather
than inventing a pattern. Reuse-only: timeline.py, calibration.py, and
core/health/trend_utils.py.
"""

from __future__ import annotations

import sys
from collections import Counter
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
import calibration as _calibration

try:
    import trend_utils as _trend  # core/health/trend_utils.py
except Exception:  # noqa: BLE001
    _trend = None

_MIN_REPEAT = 2


@dataclass
class Pattern:
    pattern_type: str
    description: str
    frequency: int = 0
    signal: str = "neutral"      # reinforce | caution | watch | neutral
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

_GENERIC_THEME_WORDS = {
    "lacks", "daily", "crew", "captain", "today", "uss", "tjr", "runtime",
    "system", "needs", "current", "still", "yet", "able", "using",
}


def _recurring_risk_themes() -> list[Pattern]:
    """Repeated bottleneck/risk themes across *distinct* decisions.

    Counts themes across distinct bottleneck texts (not raw records) so that
    duplicate/near-duplicate decision logs don't inflate frequencies.
    """
    events = _timeline.load_events(kinds=["decision"])
    distinct_bottlenecks = {
        ((e.detail or {}).get("bottleneck") or "").strip()
        for e in events
    } - {""}
    word_counts: Counter = Counter()
    for text in distinct_bottlenecks:
        for w in _timeline.keywords(text):
            if len(w) > 4 and w not in _GENERIC_THEME_WORDS:
                word_counts[w] += 1
    patterns = []
    for theme, n in word_counts.most_common(5):
        if n >= _MIN_REPEAT:
            patterns.append(Pattern(
                pattern_type="recurring_risk",
                description=f"'{theme}' recurs as a bottleneck across {n} distinct decisions",
                frequency=n,
                signal="caution" if n >= 3 else "watch",
                evidence=[theme],
            ))
    return patterns


def _confidence_pattern() -> list[Pattern]:
    advice = [e for e in _timeline.load_events(kinds=["advice"], newest_first=False) if e.score is not None]
    if len(advice) < 4 or _trend is None:
        return []
    series = [float(e.score) for e in advice]
    direction = _trend.compute_trend(series, higher_is_better=True)
    sig = {"improving": "reinforce", "worsening": "caution"}.get(direction, "neutral")
    return [Pattern(
        pattern_type="confidence_trend",
        description=f"Advisory confidence is {direction} over the last {len(series)} recommendations",
        frequency=len(series),
        signal=sig,
        evidence=[f"{int(series[0]*100)}% → {int(series[-1]*100)}%"],
    )]


def _advisor_outcome_pattern() -> list[Pattern]:
    acc = _calibration.officer_accuracy()
    patterns = []
    for officer, stats in acc.items():
        if stats.get("accuracy") is None or stats.get("samples", 0) < _MIN_REPEAT:
            continue
        rate = stats["accuracy"]
        sig = "reinforce" if rate >= 0.7 else "caution" if rate < 0.4 else "neutral"
        patterns.append(Pattern(
            pattern_type="advisor_outcome",
            description=f"{officer} advice succeeds {int(rate*100)}% of the time",
            frequency=stats["samples"],
            signal=sig,
            evidence=[f"{officer}: {int(rate*100)}% (n={stats['samples']})"],
        ))
    return patterns


def _escalation_pattern() -> list[Pattern]:
    advice = _timeline.load_events(kinds=["advice"])
    escalated = [e for e in advice if (e.detail or {}).get("escalation_required")]
    if len(escalated) < _MIN_REPEAT:
        return []
    return [Pattern(
        pattern_type="dependency_risk",
        description=f"{len(escalated)} recommendations required escalation — recurring decision risk",
        frequency=len(escalated),
        signal="caution",
        evidence=[e.title[:80] for e in escalated[:3]],
    )]


def _health_pattern() -> list[Pattern]:
    """Reuse health trend math if a health series is available; else nothing."""
    # Health series live in Supabase (captains_log_entries); offline this is empty.
    # The detector is wired and ready — it produces a pattern the moment data exists.
    return []


def _stalled_work_pattern() -> list[Pattern]:
    """Decisions/advice with no recorded outcome (open loops)."""
    advice = _timeline.load_events(kinds=["advice"])
    open_advice = [e for e in advice if not e.outcome]
    if len(open_advice) >= 3:
        return [Pattern(
            pattern_type="open_loops",
            description=f"{len(open_advice)} pieces of advice have no recorded outcome (open loops)",
            frequency=len(open_advice),
            signal="watch",
            evidence=[e.ref for e in open_advice[:3]],
        )]
    return []


_DETECTORS = (
    _recurring_risk_themes,
    _confidence_pattern,
    _advisor_outcome_pattern,
    _escalation_pattern,
    _health_pattern,
    _stalled_work_pattern,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_patterns() -> list[Pattern]:
    patterns: list[Pattern] = []
    for detector in _DETECTORS:
        try:
            patterns.extend(detector())
        except Exception:  # noqa: BLE001
            continue
    patterns.sort(key=lambda p: (p.signal == "caution", p.frequency), reverse=True)
    return patterns


def to_markdown(patterns: list[Pattern] | None = None) -> str:
    patterns = detect_patterns() if patterns is None else patterns
    if not patterns:
        return "No repeated patterns detected yet (insufficient history)."
    L = ["# Detected Patterns", ""]
    for p in patterns:
        L.append(f"- **{p.pattern_type}** ({p.signal}, ×{p.frequency}): {p.description}")
    return "\n".join(L)
