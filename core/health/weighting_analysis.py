"""
Weighting Analysis — WP4

Analyses which input variables most strongly correlate with the Captain's
self-rated capacity to produce evidence-based weighting recommendations.

Rules:
  - No automatic weight changes — recommendations only
  - Requires MIN_ANALYSIS_DAYS paired entries for any output
  - Correlation is simple mean-difference: how well does each variable
    predict the captain's rating vs the current model's assumption

Entry points:
  run_analysis(days=45) → WeightingAnalysis dict
"""

from __future__ import annotations

import json
import sys
import argparse
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))

from supabase_client import supabase_get, is_configured
from capacity_score import WEIGHTS, CAPACITY_THRESHOLDS

MIN_ANALYSIS_DAYS = 14


# ---------------------------------------------------------------------------
# Variable extractors — each returns a float signal and a label
# ---------------------------------------------------------------------------

def _pain_signal(e: Dict) -> Optional[float]:
    v = e.get("pain_score")
    return float(v) / 10.0 if v is not None else None  # 0–1, higher = worse


def _sleep_signal(e: Dict) -> Optional[float]:
    h = e.get("sleep_hours")
    if h is None:
        return None
    # Invert so higher = worse (matches pain direction)
    if float(h) < 5:   return 1.0
    if float(h) < 6:   return 0.6
    return 0.0


def _energy_signal(e: Dict) -> Optional[float]:
    v = (e.get("energy") or "").strip().lower()
    return {"low": 1.0, "moderate": 0.4, "high": 0.0}.get(v)


def _mood_signal(e: Dict) -> Optional[float]:
    v = (e.get("mood") or "").strip().lower()
    return {"low": 1.0, "stable": 0.4, "positive": 0.0}.get(v)


def _capacity_signal(e: Dict) -> Optional[float]:
    v = (e.get("physical_capacity") or "").strip().lower()
    return {"worse": 1.0, "same": 0.5, "better": 0.0}.get(v)


def _sleep_quality_signal(e: Dict) -> Optional[float]:
    v = (e.get("sleep_quality") or "").strip().lower()
    return {"poor": 1.0, "fair": 0.5, "good": 0.0}.get(v)


_EXTRACTORS = {
    "pain_score":        (_pain_signal,    WEIGHTS["pain_max_deduction"]),
    "sleep_hours":       (_sleep_signal,   WEIGHTS["sleep_lt_5h"]),
    "energy":            (_energy_signal,  WEIGHTS["energy_low"]),
    "mood":              (_mood_signal,    WEIGHTS["mood_low"]),
    "physical_capacity": (_capacity_signal, abs(WEIGHTS["capacity_worse"])),
    "sleep_quality":     (_sleep_quality_signal, WEIGHTS["sleep_lt_5h"]),
}


# ---------------------------------------------------------------------------
# Rating → numeric
# ---------------------------------------------------------------------------

_RATING_NUM = {"Green": 0, "Amber": 1, "Red": 2}


def _captain_num(e: Dict) -> Optional[int]:
    r = e.get("captain_capacity_rating")
    return _RATING_NUM.get(r)


# ---------------------------------------------------------------------------
# Correlation helper
# ---------------------------------------------------------------------------

def _pearson_simple(xs: List[float], ys: List[float]) -> Optional[float]:
    """Simple Pearson r — positive means variable predicts severity."""
    n = len(xs)
    if n < 4:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = (sum((x - mx) ** 2 for x in xs)) ** 0.5
    dy = (sum((y - my) ** 2 for y in ys)) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return round(num / (dx * dy), 3)


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def run_analysis(days: int = 45) -> Dict[str, Any]:
    if not is_configured():
        return {"error": "Supabase not configured", "success": False}

    since = (date.today() - timedelta(days=days - 1)).isoformat()
    entries = supabase_get(
        f"captains_log_entries?log_date=gte.{since}&order=log_date.asc&limit={days}"
    )

    paired = [e for e in entries if e.get("captain_capacity_rating")]
    if len(paired) < MIN_ANALYSIS_DAYS:
        return {
            "success": True,
            "status": "insufficient_data",
            "message": f"Need {MIN_ANALYSIS_DAYS} rated entries; have {len(paired)}",
            "days_analysed": days,
            "paired_entries": len(paired),
            "recommendations": [],
        }

    captain_nums = [_captain_num(e) for e in paired]
    valid_captain = [v for v in captain_nums if v is not None]

    correlations: Dict[str, Optional[float]] = {}
    for var, (extractor, current_weight) in _EXTRACTORS.items():
        xs = []
        ys = []
        for e, cn in zip(paired, captain_nums):
            sig = extractor(e)
            if sig is not None and cn is not None:
                xs.append(sig)
                ys.append(float(cn))
        correlations[var] = _pearson_simple(xs, ys)

    # Rank by absolute correlation strength
    ranked = sorted(
        [(v, r) for v, r in correlations.items() if r is not None],
        key=lambda x: abs(x[1]),
        reverse=True,
    )

    recommendations = _generate_recommendations(ranked, len(paired))

    return {
        "success": True,
        "status": "complete",
        "days_analysed": days,
        "paired_entries": len(paired),
        "variable_correlations": {v: r for v, r in correlations.items()},
        "ranked_by_predictive_strength": [
            {"variable": v, "correlation": r, "strength": _strength_label(r)}
            for v, r in ranked
        ],
        "current_weights": dict(WEIGHTS),
        "recommendations": recommendations,
    }


def _strength_label(r: Optional[float]) -> str:
    if r is None:
        return "insufficient_data"
    a = abs(r)
    if a >= 0.6:   return "strong"
    if a >= 0.35:  return "moderate"
    if a >= 0.15:  return "weak"
    return "negligible"


def _generate_recommendations(
    ranked: List[Tuple[str, float]],
    n_paired: int,
) -> List[Dict[str, Any]]:
    """
    Compare observed correlations against current weight allocations.
    Produce plain-English recommendations — no automatic changes.
    """
    # Total current weight budget for the main variables
    total_budget = sum([
        WEIGHTS["pain_max_deduction"],
        WEIGHTS["energy_low"],
        WEIGHTS["sleep_lt_5h"],
        WEIGHTS["mood_low"],
        abs(WEIGHTS["capacity_worse"]),
    ])

    # Map variable names to current weights
    current = {
        "pain_score":        WEIGHTS["pain_max_deduction"],
        "energy":            WEIGHTS["energy_low"],
        "sleep_hours":       WEIGHTS["sleep_lt_5h"],
        "mood":              WEIGHTS["mood_low"],
        "physical_capacity": abs(WEIGHTS["capacity_worse"]),
        "sleep_quality":     WEIGHTS["sleep_lt_5h"],  # proxy — same tier
    }

    recs = []
    for var, corr in ranked[:4]:  # top 4 predictors
        a = abs(corr)
        cw = current.get(var, 0)

        # Suggest a weight proportional to the observed correlation strength
        proposed = round(total_budget * a / max(sum(abs(c) for _, c in ranked if c is not None), 1), 1)
        proposed = min(proposed, 40)  # cap any single variable at 40

        if abs(proposed - cw) < 3:
            continue  # not worth flagging

        direction = "increase" if proposed > cw else "decrease"
        reason = (
            f"{var.replace('_', ' ').title()} shows {_strength_label(corr)} correlation "
            f"(r={corr:.2f}) with Captain self-ratings over the last {n_paired} entries. "
            f"Current weight ({cw}%) may {('under' if direction == 'increase' else 'over')}state its influence."
        )

        recs.append({
            "variable": var,
            "current_weight": cw,
            "recommended_weight": proposed,
            "direction": direction,
            "correlation": corr,
            "strength": _strength_label(corr),
            "reason": reason,
            "note": "Recommendation only — no automatic changes permitted. XO approval required.",
        })

    return recs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run weighting analysis")
    parser.add_argument("--days", type=int, default=45)
    args = parser.parse_args()
    print(json.dumps(run_analysis(days=args.days), indent=2, default=str))
