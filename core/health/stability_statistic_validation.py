"""Stream 0 — critical-slowing-down statistic validation (USS-TJR-MSN-0388).

READ-ONLY analysis. This module creates no table, writes nothing, and is not
imported by any live code path. It exists to answer one question before any
of Mission 0388's later streams wire a new statistic into
core/health/burnout_trajectory.py:

    Does rolling lag-1 autocorrelation / rolling variance ("critical slowing
    down", van de Leemput & Wichers, PNAS 2014; replicated Smit et al.
    2024/25) produce a legible, non-noisy early-warning signal at the
    Captain's ACTUAL capacity_checkins cadence?

The method those papers use is ESM (experience sampling): 3-10 prompts per
day for months, i.e. several hundred to several thousand observations, with
rolling windows of 100+ points. This script measures what we actually have
and reports the gap in concrete numbers rather than asserting a verdict.

Run:
    python3 -m core.health.stability_statistic_validation
"""

from __future__ import annotations

import itertools
import random
import statistics
import sys
from datetime import date, datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.health.supabase_client import supabase_get

# Ordinal encodings. capacity_state is the primary series (it is the field
# burnout_trajectory.py already buckets on, so validating CSD on anything
# else would validate a statistic we could not then use).
CAPACITY_ORDINAL = {"green": 0, "orange": 1, "red": 2}

# Rolling-window sizes to test. The CSD literature's own windows are 100+;
# these are the largest windows that leave any estimates at all on a series
# of the Captain's length, which is itself part of the finding.
TEST_WINDOWS = (7, 10, 14)

# An AR(1) estimate is only meaningful if its sampling error is small
# relative to the drift the method is supposed to detect. The PNAS/Smit
# papers report pre-transition AR(1) rises on the order of 0.10-0.25, so an
# estimate whose own standard error exceeds this is not decision-grade.
MEANINGFUL_AR1_SHIFT = 0.15


def fetch_series() -> list[dict]:
    """Every capacity_checkins row carrying a capacity_state, chronological."""
    rows = supabase_get(
        "capacity_checkins"
        "?select=captured_at,log_date,checkin_type,capacity_state,executive_function"
        "&order=captured_at.asc&limit=5000"
    )
    return [r for r in rows if r.get("capacity_state") in CAPACITY_ORDINAL]


def lag1_autocorr(values: list[float]) -> float | None:
    """Lag-1 autocorrelation. None when undefined (n<3 or zero variance).

    Zero variance is not a degenerate edge case here — a run of identical
    capacity_state readings is common and genuinely carries no
    autocorrelation information, so it must return None rather than 0.0 or
    1.0, either of which would be read downstream as a real measurement.
    """
    n = len(values)
    if n < 3:
        return None
    mean = sum(values) / n
    denom = sum((v - mean) ** 2 for v in values)
    if denom == 0:
        return None
    numer = sum((values[i] - mean) * (values[i + 1] - mean) for i in range(n - 1))
    return numer / denom


def rolling(values: list[float], window: int, fn) -> list[float | None]:
    """fn applied to each trailing window; None where the window is short."""
    return [
        (fn(values[i - window + 1 : i + 1]) if i >= window - 1 else None)
        for i in range(len(values))
    ]


def _variance(vals: list[float]) -> float | None:
    return statistics.pvariance(vals) if len(vals) >= 2 else None


def cadence_report(rows: list[dict]) -> dict:
    days = sorted({r["log_date"] for r in rows})
    d0, d1 = date.fromisoformat(days[0]), date.fromisoformat(days[-1])
    span = (d1 - d0).days + 1
    gaps = [
        (date.fromisoformat(b) - date.fromisoformat(a)).days
        for a, b in itertools.pairwise(days)
    ]
    last = datetime.fromisoformat(rows[-1]["captured_at"]).date()
    return {
        "n_readings": len(rows),
        "n_days": len(days),
        "calendar_span_days": span,
        "day_coverage": len(days) / span,
        "readings_per_day": len(rows) / span,
        "max_gap_days": max(gaps) if gaps else 0,
        "first_day": days[0],
        "last_day": days[-1],
        "staleness_days": (datetime.now(timezone.utc).date() - last).days,
    }


def permutation_null(values: list[float], window: int, trials: int = 2000) -> dict:
    """How much rolling-AR(1) swing does PURE NOISE produce on this series?

    Shuffling destroys all temporal structure, so any rolling-AR(1) range
    still seen under shuffling is noise by construction. If the real
    series' range is inside that null distribution, the observed "signal"
    is not distinguishable from chance at this length.
    """
    rng = random.Random(20260914)
    ranges = []
    for _ in range(trials):
        shuffled = values[:]
        rng.shuffle(shuffled)
        est = [v for v in rolling(shuffled, window, lag1_autocorr) if v is not None]
        if len(est) >= 2:
            ranges.append(max(est) - min(est))
    ranges.sort()
    if not ranges:
        return {}
    return {
        "trials": len(ranges),
        "median_range": statistics.median(ranges),
        "p95_range": ranges[int(0.95 * (len(ranges) - 1))],
    }


def analyse() -> dict:
    rows = fetch_series()
    if not rows:
        raise RuntimeError("No capacity_checkins rows with a capacity_state.")

    cadence = cadence_report(rows)
    series = [float(CAPACITY_ORDINAL[r["capacity_state"]]) for r in rows]

    windows: dict[int, dict] = {}
    for w in TEST_WINDOWS:
        ar1 = [v for v in rolling(series, w, lag1_autocorr) if v is not None]
        var = [v for v in rolling(series, w, _variance) if v is not None]
        # Approximate SE of an AR(1) estimate from n observations.
        se = 1.0 / (w ** 0.5)
        windows[w] = {
            "n_estimates": len(ar1),
            "ar1_min": min(ar1) if ar1 else None,
            "ar1_max": max(ar1) if ar1 else None,
            "ar1_range": (max(ar1) - min(ar1)) if len(ar1) >= 2 else None,
            "ar1_mean": statistics.fmean(ar1) if ar1 else None,
            "ar1_sd": statistics.pstdev(ar1) if len(ar1) >= 2 else None,
            "approx_se_per_estimate": se,
            "se_exceeds_meaningful_shift": se > MEANINGFUL_AR1_SHIFT,
            "var_range": (max(var) - min(var)) if len(var) >= 2 else None,
            "null": permutation_null(series, w),
        }
    return {"cadence": cadence, "series_length": len(series), "windows": windows}


def _fmt(v, nd=3):
    return "n/a" if v is None else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))


def main() -> int:
    res = analyse()
    c = res["cadence"]
    print("=" * 72)
    print("USS-TJR-MSN-0388 STREAM 0 — critical-slowing-down feasibility")
    print("=" * 72)
    print("\n-- Actual check-in cadence --")
    print(f"  capacity readings           : {c['n_readings']}")
    print(f"  distinct days               : {c['n_days']}")
    print(f"  calendar span               : {c['calendar_span_days']} days "
          f"({c['first_day']} -> {c['last_day']})")
    print(f"  day coverage                : {c['day_coverage']:.1%}")
    print(f"  readings per calendar day   : {c['readings_per_day']:.2f}")
    print(f"  largest gap between days    : {c['max_gap_days']} days")
    print(f"  staleness (days since last) : {c['staleness_days']}")

    print("\n-- Rolling AR(1) / variance on capacity_state ordinal series --")
    for w, d in res["windows"].items():
        print(f"\n  window = {w} readings")
        print(f"    usable estimates          : {d['n_estimates']}")
        print(f"    AR(1) mean / sd           : {_fmt(d['ar1_mean'])} / {_fmt(d['ar1_sd'])}")
        print(f"    AR(1) min..max (range)    : {_fmt(d['ar1_min'])} .. {_fmt(d['ar1_max'])} "
              f"({_fmt(d['ar1_range'])})")
        print(f"    approx SE per estimate    : {_fmt(d['approx_se_per_estimate'])} "
              f"(meaningful shift is ~{MEANINGFUL_AR1_SHIFT})")
        print(f"    SE swamps real effect?    : {d['se_exceeds_meaningful_shift']}")
        print(f"    rolling variance range    : {_fmt(d['var_range'])}")
        n = d["null"]
        if n:
            print(f"    SHUFFLED-null AR(1) range : median {_fmt(n['median_range'])}, "
                  f"p95 {_fmt(n['p95_range'])} over {n['trials']} shuffles")
            obs = d["ar1_range"]
            if obs is not None:
                verdict = ("INSIDE the noise band — not distinguishable from chance"
                           if obs <= n["p95_range"] else
                           "exceeds the p95 noise band")
                print(f"    observed vs null          : {verdict}")
    print("\n" + "=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
