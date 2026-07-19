"""
Sleep Lag Intelligence — WP3
Mission: M-20260613-INTELLIGENCE-MATURITY-PHASE2

Analyses sleep-to-next-day performance relationships:
- Sleep duration vs next-day energy
- Sleep quality vs next-day energy
- CPAP usage vs next-day energy
- Sleep duration vs readiness score

Designed to integrate with weekly_synthesis.py and produce standalone output.

Public API:
    compute_sleep_lag_analysis(entries) -> dict
    compute_sleep_lag_from_supabase(days) -> dict
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))

try:
    from supabase_client import supabase_get, is_configured
    _SUPABASE_OK = True
except ImportError:
    _SUPABASE_OK = False


# ---------------------------------------------------------------------------
# Encoders
# ---------------------------------------------------------------------------

_ENERGY_NUM = {"low": 1, "moderate": 2, "high": 3}
_QUALITY_NUM = {"poor": 1, "fair": 2, "good": 3, "excellent": 4}


def _enc_energy(v: Any) -> int | None:
    if v is None:
        return None
    return _ENERGY_NUM.get(str(v).lower().strip())


def _enc_quality(v: Any) -> int | None:
    if v is None:
        return None
    return _QUALITY_NUM.get(str(v).lower().strip())


def _sleep_hours(e: dict) -> float | None:
    v = e.get("sleep_hours")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _cpap_used(e: dict) -> bool | None:
    raw = e.get("cpap_status") or e.get("cpap_used")
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    return str(raw).lower().strip() in ("yes", "true", "1")


# ---------------------------------------------------------------------------
# Pearson r
# ---------------------------------------------------------------------------

def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx  = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy  = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return round(num / (dx * dy), 3)


def _interp(r: float | None) -> str:
    if r is None:
        return "insufficient_data"
    a = abs(r)
    d = "positive" if r > 0 else "negative"
    if a >= 0.7:
        return f"strong_{d}"
    if a >= 0.4:
        return f"moderate_{d}"
    if a >= 0.2:
        return f"weak_{d}"
    return "negligible"


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def compute_sleep_lag_analysis(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute sleep lag analysis from a list of health log entries.

    Entries should be sorted by log_date ascending.
    Each entry: {log_date, sleep_hours, sleep_quality, cpap_status, energy, ...}

    Returns structured dict with correlation results and findings.
    """
    sorted_entries = sorted(entries, key=lambda e: str(e.get("log_date", "")))
    n = len(sorted_entries)

    if n < 3:
        return {
            "status": "insufficient_data",
            "n_entries": n,
            "note": "Minimum 3 consecutive days required for lag analysis.",
            "correlations": {},
            "findings": [],
        }

    # Build lag-1 pairs: tonight's sleep → tomorrow's energy
    lag_pairs: list[dict[str, Any]] = []
    for i in range(n - 1):
        curr = sorted_entries[i]
        nxt  = sorted_entries[i + 1]

        # Only count if dates are consecutive
        try:
            d_curr = date.fromisoformat(str(curr["log_date"])[:10])
            d_next = date.fromisoformat(str(nxt["log_date"])[:10])
            if (d_next - d_curr).days != 1:
                continue
        except (KeyError, ValueError):
            continue

        lag_pairs.append({
            "date_night":    str(curr["log_date"])[:10],
            "date_next":     str(nxt["log_date"])[:10],
            "sleep_hours":   _sleep_hours(curr),
            "sleep_quality": _enc_quality(curr.get("sleep_quality")),
            "cpap_used":     _cpap_used(curr),
            "next_energy":   _enc_energy(nxt.get("energy")),
            "next_energy_raw": nxt.get("energy"),
        })

    valid_pairs = [p for p in lag_pairs if p["next_energy"] is not None]
    n_pairs = len(valid_pairs)

    if n_pairs < 3:
        return {
            "status": "insufficient_consecutive_pairs",
            "n_entries": n,
            "n_lag_pairs": n_pairs,
            "note": "Insufficient consecutive-day pairs with both sleep and next-day energy data.",
            "correlations": {},
            "findings": [],
        }

    # ── Sleep duration vs next-day energy ───────────────────────────────────
    sleep_dur_pairs = [(p["sleep_hours"], p["next_energy"])
                       for p in valid_pairs if p["sleep_hours"] is not None]
    xs_dur  = [x for x, _ in sleep_dur_pairs]
    ys_dur  = [y for _, y in sleep_dur_pairs]
    r_dur   = _pearson(xs_dur, ys_dur)

    # Threshold analysis: ≥7h vs <6h sleep
    high_sleep  = [p["next_energy"] for p in valid_pairs
                   if p["sleep_hours"] is not None and p["sleep_hours"] >= 7]
    low_sleep   = [p["next_energy"] for p in valid_pairs
                   if p["sleep_hours"] is not None and p["sleep_hours"] < 6]
    high_sleep_energy = round(mean(high_sleep), 2) if high_sleep else None
    low_sleep_energy  = round(mean(low_sleep), 2)  if low_sleep  else None

    # ── Sleep quality vs next-day energy ────────────────────────────────────
    qual_pairs = [(p["sleep_quality"], p["next_energy"])
                  for p in valid_pairs if p["sleep_quality"] is not None]
    xs_qual = [x for x, _ in qual_pairs]
    ys_qual = [y for _, y in qual_pairs]
    r_qual  = _pearson(xs_qual, ys_qual)

    # ── CPAP vs next-day energy ─────────────────────────────────────────────
    cpap_groups: dict[bool, list[int]] = {True: [], False: []}
    for p in valid_pairs:
        if p["cpap_used"] is not None:
            cpap_groups[p["cpap_used"]].append(p["next_energy"])

    cpap_with    = round(mean(cpap_groups[True]),  2) if cpap_groups[True]  else None
    cpap_without = round(mean(cpap_groups[False]), 2) if cpap_groups[False] else None

    # ── Sleep duration thresholds ────────────────────────────────────────────
    sleep_buckets: dict[str, list[int]] = defaultdict(list)
    for p in valid_pairs:
        h = p["sleep_hours"]
        e = p["next_energy"]
        if h is None or e is None:
            continue
        if h >= 8:
            sleep_buckets["8h+"].append(e)
        elif h >= 7:
            sleep_buckets["7-8h"].append(e)
        elif h >= 6:
            sleep_buckets["6-7h"].append(e)
        else:
            sleep_buckets["<6h"].append(e)

    sleep_threshold_table = {
        bucket: {
            "n": len(vals),
            "avg_next_energy": round(mean(vals), 2),
            "modal_energy": _modal_energy(vals),
        }
        for bucket, vals in sleep_threshold_table_items(sleep_buckets)
    }

    # ── Optimal sleep threshold ─────────────────────────────────────────────
    optimal_threshold = _find_optimal_sleep_threshold(sleep_threshold_table)

    # ── Findings ─────────────────────────────────────────────────────────────
    findings = _build_findings(
        r_dur, r_qual, n_pairs,
        high_sleep_energy, low_sleep_energy,
        cpap_with, cpap_without,
        optimal_threshold,
        len(cpap_groups[True]), len(cpap_groups[False]),
    )

    return {
        "status": "ok",
        "n_entries": n,
        "n_lag_pairs": n_pairs,
        "correlations": {
            "sleep_duration_vs_next_day_energy": {
                "r": r_dur,
                "interpretation": _interp(r_dur),
                "n": len(xs_dur),
                "avg_energy_high_sleep_7plus": high_sleep_energy,
                "avg_energy_low_sleep_sub6": low_sleep_energy,
            },
            "sleep_quality_vs_next_day_energy": {
                "r": r_qual,
                "interpretation": _interp(r_qual),
                "n": len(xs_qual),
            },
            "cpap_vs_next_day_energy": {
                "avg_energy_with_cpap":    cpap_with,
                "avg_energy_without_cpap": cpap_without,
                "n_with_cpap":    len(cpap_groups[True]),
                "n_without_cpap": len(cpap_groups[False]),
                "interpretation": _cpap_interp(cpap_with, cpap_without),
            },
        },
        "sleep_threshold_table": sleep_threshold_table,
        "optimal_sleep_threshold": optimal_threshold,
        "findings": findings,
    }


def sleep_threshold_table_items(
    buckets: dict[str, list[int]]
) -> list[tuple[str, list[int]]]:
    order = ["<6h", "6-7h", "7-8h", "8h+"]
    return [(k, buckets[k]) for k in order if k in buckets]


def _modal_energy(vals: list[int]) -> str:
    if not vals:
        return "unknown"
    rev = {1: "Low", 2: "Moderate", 3: "High"}
    return rev.get(Counter(vals).most_common(1)[0][0], "unknown")


def _cpap_interp(with_val: float | None, without_val: float | None) -> str:
    if with_val is None or without_val is None:
        return "insufficient_data"
    diff = with_val - without_val
    if diff >= 0.3:
        return "strong_positive"
    if diff >= 0.1:
        return "positive"
    if diff <= -0.1:
        return "negative"
    return "neutral"


def _find_optimal_sleep_threshold(table: dict[str, dict]) -> str | None:
    best_bucket, best_energy = None, -1.0
    for bucket, stats in table.items():
        avg = stats.get("avg_next_energy", 0) or 0
        n   = stats.get("n", 0) or 0
        if n >= 2 and avg > best_energy:
            best_energy = avg
            best_bucket = bucket
    return best_bucket


def _build_findings(
    r_dur: float | None,
    r_qual: float | None,
    n_pairs: int,
    high_sleep_e: float | None,
    low_sleep_e: float | None,
    cpap_with: float | None,
    cpap_without: float | None,
    optimal: str | None,
    n_cpap_with: int,
    n_cpap_without: int,
) -> list[str]:
    findings = []
    _rev = {1: "Low", 2: "Moderate", 3: "High"}

    if r_dur is not None:
        findings.append(
            f"SLEEP DURATION→ENERGY: r={r_dur} ({_interp(r_dur)}, n={n_pairs}) — "
            + (f"Sleep ≥7h → avg energy {high_sleep_e:.2f}/3 vs <6h → {low_sleep_e:.2f}/3"
               if high_sleep_e and low_sleep_e else "limited threshold data")
        )

    if r_qual is not None:
        findings.append(f"SLEEP QUALITY→ENERGY: r={r_qual} ({_interp(r_qual)})")

    if cpap_with is not None and cpap_without is not None:
        diff = round(cpap_with - cpap_without, 2)
        sign = "+" if diff >= 0 else ""
        findings.append(
            f"CPAP→NEXT-DAY ENERGY: CPAP nights avg {cpap_with:.2f} vs non-CPAP {cpap_without:.2f} "
            f"({sign}{diff} delta, n={n_cpap_with} vs {n_cpap_without})"
        )

    if optimal:
        findings.append(f"OPTIMAL SLEEP WINDOW: {optimal} associated with highest next-day energy")

    if n_pairs < 14:
        findings.append(f"NOTE: {n_pairs} lag pairs. Reliability improves with ≥14 consecutive days.")

    return findings


# ---------------------------------------------------------------------------
# Supabase convenience wrapper
# ---------------------------------------------------------------------------

def compute_sleep_lag_from_supabase(days: int = 60) -> dict[str, Any]:
    """Fetch health entries from Supabase and run sleep lag analysis."""
    if not _SUPABASE_OK or not is_configured():
        return {
            "status": "supabase_unavailable",
            "correlations": {},
            "findings": ["Supabase not configured — cannot fetch health entries."],
        }
    since = (date.today() - timedelta(days=days)).isoformat()
    try:
        entries = supabase_get(
            f"captains_log_entries?log_date=gte.{since}&order=log_date.asc&limit={days}"
        )
    except Exception as exc:
        return {
            "status": "fetch_error",
            "error": str(exc),
            "correlations": {},
            "findings": [],
        }
    return compute_sleep_lag_analysis(entries)
