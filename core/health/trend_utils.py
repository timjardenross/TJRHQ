"""
Health Trend Utility — WP-4 (Phase 1 Consolidation)

Single canonical implementation of numeric trend classification.
Replaces three divergent inline implementations:
  - weekly_synthesis._numeric_trend()        (delta threshold 0.4)
  - health_synthesis._pain_trend()           (delta threshold 0.5, different small-N algorithm)
  - health_context_adapter inline trend      (delta threshold 0.4, no named constant)

All three are replaced with imports from this module.

Public API:
    TREND_DELTA_THRESHOLD   float  (0.4)
    MIN_DAYS_FOR_TREND      int    (4)
    compute_trend(values, higher_is_better) -> str
    compute_pain_trend(values)  -> str
    compute_sleep_trend(values) -> str
    compute_energy_trend(values) -> str
"""

from __future__ import annotations

from typing import List

# ── Constants ─────────────────────────────────────────────────────────────────

TREND_DELTA_THRESHOLD = 0.4
"""Minimum absolute delta between half-means to classify as improving/worsening."""

MIN_DAYS_FOR_TREND = 4
"""Minimum number of values required to compute a reliable split-half trend."""


# ── Core function ─────────────────────────────────────────────────────────────

def compute_trend(values: List[float], higher_is_better: bool = False) -> str:
    """
    Classify a time-ordered list of numeric values as a trend direction.

    Uses split-half mean comparison: compares the mean of the second half
    of the series against the mean of the first half.

    Args:
        values:           Time-ordered numeric values (oldest first).
        higher_is_better: If True, an increasing second half is 'improving'
                          (e.g. sleep hours, capacity score).
                          If False (default), a decreasing second half is
                          'improving' (e.g. pain score).

    Returns:
        "improving"        — trend moving in the desired direction
        "worsening"        — trend moving in the undesired direction
        "stable"           — delta below TREND_DELTA_THRESHOLD
        "insufficient_data" — fewer than MIN_DAYS_FOR_TREND values
    """
    if len(values) < MIN_DAYS_FOR_TREND:
        return "insufficient_data"

    mid = len(values) // 2
    first_half_mean = sum(values[:mid]) / mid
    second_half_mean = sum(values[mid:]) / (len(values) - mid)
    delta = second_half_mean - first_half_mean

    if abs(delta) < TREND_DELTA_THRESHOLD:
        return "stable"

    if higher_is_better:
        return "improving" if delta > 0 else "worsening"
    else:
        return "improving" if delta < 0 else "worsening"


# ── Domain-specific helpers ───────────────────────────────────────────────────

def compute_pain_trend(values: List[float]) -> str:
    """Pain trend — lower scores are better."""
    return compute_trend(values, higher_is_better=False)


def compute_sleep_trend(values: List[float]) -> str:
    """Sleep trend — higher hours are better."""
    return compute_trend(values, higher_is_better=True)


def compute_capacity_trend(values: List[float]) -> str:
    """Capacity score trend — higher scores are better."""
    return compute_trend(values, higher_is_better=True)


def compute_energy_trend(values: List[float]) -> str:
    """
    Energy trend from ordinal encoded values (Low=1, Moderate=2, High=3).
    Higher is better.
    """
    return compute_trend(values, higher_is_better=True)


# ── Ordinal encoder for categorical fields ────────────────────────────────────

def encode_energy(value: str) -> float:
    """Map energy string to ordinal float for trend computation."""
    return {"low": 1.0, "moderate": 2.0, "high": 3.0}.get(value.lower(), 2.0)


def encode_mood(value: str) -> float:
    """Map mood string to ordinal float for trend computation."""
    return {"low": 1.0, "stable": 2.0, "positive": 3.0}.get(value.lower(), 2.0)


# ── Day-of-week pattern analysis ──────────────────────────────────────────────

_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MIN_SAMPLES_PER_DAY = 2


def day_of_week_pattern(
    dated_values: List[tuple],  # List of (date_iso: str, value: float)
    higher_is_better: bool = True,
    min_samples: int = MIN_SAMPLES_PER_DAY,
) -> dict:
    """
    Compute per-weekday averages and identify the best/worst day.

    Args:
        dated_values:      List of (date_iso, numeric_value) pairs, oldest first.
        higher_is_better:  Direction for 'best' classification.
        min_samples:       Minimum entries per day to report a day's average.

    Returns dict with:
        pattern:            {weekday_int: {'day': 'Mon', 'avg': float, 'n': int}}
        best_day:           'Mon' or None
        worst_day:          'Mon' or None
        finding:            Human-readable string or None
        status:             'ok' or 'insufficient_data'
    """
    from datetime import date as _date
    from collections import defaultdict

    buckets: dict = defaultdict(list)
    for date_iso, value in dated_values:
        try:
            d = _date.fromisoformat(str(date_iso))
            buckets[d.weekday()].append(float(value))
        except (ValueError, TypeError):
            continue

    pattern = {}
    for weekday, vals in sorted(buckets.items()):
        if len(vals) >= min_samples:
            pattern[weekday] = {
                "day": _DAY_NAMES[weekday],
                "avg": round(sum(vals) / len(vals), 2),
                "n": len(vals),
            }

    if len(pattern) < 3:
        return {"pattern": pattern, "best_day": None, "worst_day": None,
                "finding": None, "status": "insufficient_data"}

    avgs = {wd: info["avg"] for wd, info in pattern.items()}
    best_wd  = max(avgs, key=lambda wd: avgs[wd]) if higher_is_better else min(avgs, key=lambda wd: avgs[wd])
    worst_wd = min(avgs, key=lambda wd: avgs[wd]) if higher_is_better else max(avgs, key=lambda wd: avgs[wd])

    best_day  = pattern[best_wd]["day"]
    worst_day = pattern[worst_wd]["day"]
    delta     = abs(pattern[best_wd]["avg"] - pattern[worst_wd]["avg"])

    finding = None
    if delta >= 0.5:
        finding = (
            f"Day-of-week pattern detected: best={best_day} (avg {pattern[best_wd]['avg']}), "
            f"worst={worst_day} (avg {pattern[worst_wd]['avg']})."
        )

    return {
        "pattern": pattern,
        "best_day": best_day,
        "worst_day": worst_day,
        "finding": finding,
        "status": "ok",
    }
