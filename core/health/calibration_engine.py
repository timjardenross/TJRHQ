"""
Calibration Engine — WP2

Compares system Capacity Score/Status against Captain self-ratings
to measure model accuracy over time.

Entry points:
  run_calibration(days=30)  → CalibrationResult dict, persists to Supabase
  get_calibration_summary() → latest CalibrationResult from Supabase
"""

from __future__ import annotations

import json
import sys
import argparse
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))

from supabase_client import supabase_get, supabase_upsert, is_configured
from capacity_score import compute_capacity_score


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_DAYS_FOR_CONFIDENCE = 7   # need at least 7 paired days for any confidence
MID_DAYS_FOR_CONFIDENCE = 14  # 14+ days → medium confidence
HIGH_DAYS_FOR_CONFIDENCE = 21  # 21+ days → high confidence
GOVERNANCE_TRIGGER_DAYS = 14   # WP6: consecutive low-agreement days before advisory


def _mismatch_type(system_status: str, captain_rating: str) -> Optional[str]:
    """
    Classify the mismatch direction.
    false_green: system says Green, captain says Amber or Red
    false_amber: system says Amber, captain says Red (understated severity)
    false_red:   system says Red,   captain says Green or Amber (overstated)
    Returns None if they agree.
    """
    if system_status == captain_rating:
        return None
    if system_status == "Green" and captain_rating in ("Amber", "Red"):
        return "false_green"
    if system_status == "Amber" and captain_rating == "Red":
        return "false_amber"
    if system_status == "Red" and captain_rating in ("Green", "Amber"):
        return "false_red"
    # Amber→Green: system over-flagged, still a false_red conceptually
    if system_status == "Amber" and captain_rating == "Green":
        return "false_red"
    return "mismatch"


def _calibration_confidence(n: int) -> str:
    if n < MIN_DAYS_FOR_CONFIDENCE:
        return "insufficient"
    if n < MID_DAYS_FOR_CONFIDENCE:
        return "low"
    if n < HIGH_DAYS_FOR_CONFIDENCE:
        return "medium"
    return "high"


# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------

def _compute_rolling_pct(rows: List[Dict], end_idx: int, window: int) -> Optional[float]:
    """Agreement % for the `window` days ending at end_idx (inclusive)."""
    start = max(0, end_idx - window + 1)
    window_rows = rows[start:end_idx + 1]
    paired = [r for r in window_rows if r.get("agreement") is not None]
    if not paired:
        return None
    agreed = sum(1 for r in paired if r["agreement"])
    return round(agreed / len(paired) * 100, 2)


def run_calibration(days: int = 30) -> Dict[str, Any]:
    """
    Read `days` of Captain's Log entries, compute calibration metrics,
    persist daily rows to capacity_calibration, and upsert a summary row.

    Returns the CalibrationResult dict.
    """
    if not is_configured():
        return {"error": "Supabase not configured", "success": False}

    since = (date.today() - timedelta(days=days - 1)).isoformat()
    entries = supabase_get(
        f"captains_log_entries?log_date=gte.{since}&order=log_date.asc&limit={days}"
    )

    # Only rows that have both system inputs AND a captain rating are useful
    paired_rows: List[Dict] = []
    for e in entries:
        cap_rating = e.get("captain_capacity_rating")
        if not cap_rating:
            continue  # not yet rated — skip

        score, status = compute_capacity_score(e)
        if status in ("Unknown", None):
            continue  # not enough system data

        agree = (status == cap_rating)
        mtype = _mismatch_type(status, cap_rating)

        paired_rows.append({
            "log_date": e["log_date"],
            "capacity_score": score,
            "capacity_status": status,
            "captain_rating": cap_rating,
            "agreement": agree,
            "mismatch_type": mtype,
        })

    # Enrich with rolling windows and persist each daily row
    for idx, row in enumerate(paired_rows):
        row["weekly_agreement_pct"] = _compute_rolling_pct(paired_rows, idx, 7)
        row["rolling_30d_pct"] = _compute_rolling_pct(paired_rows, idx, 30)
        try:
            supabase_upsert("capacity_calibration", row, "log_date")
        except Exception:
            pass  # best-effort; don't abort the whole run

    # Build summary
    n = len(paired_rows)
    agreed_count = sum(1 for r in paired_rows if r["agreement"])
    false_green = sum(1 for r in paired_rows if r["mismatch_type"] == "false_green")
    false_amber = sum(1 for r in paired_rows if r["mismatch_type"] == "false_amber")
    false_red   = sum(1 for r in paired_rows if r["mismatch_type"] == "false_red")

    agreement_rate = round(agreed_count / n * 100, 2) if n > 0 else None
    confidence = _calibration_confidence(n)

    # WP6: count consecutive days where rolling_30d_pct < 70
    consecutive_low = _count_consecutive_low(paired_rows)
    weighting_review_flag = consecutive_low >= GOVERNANCE_TRIGGER_DAYS

    summary: Dict[str, Any] = {
        "summary_date": date.today().isoformat(),
        "window_days": days,
        "total_days_compared": n,
        "agreement_count": agreed_count,
        "agreement_rate": agreement_rate,
        "false_green_count": false_green,
        "false_amber_count": false_amber,
        "false_red_count": false_red,
        "calibration_confidence": confidence,
        "consecutive_low_days": consecutive_low,
        "weighting_review_flag": weighting_review_flag,
    }

    try:
        supabase_upsert("capacity_calibration_summary", summary, "summary_date")
    except Exception:
        pass

    summary["success"] = True
    summary["rows_processed"] = len(entries)
    summary["rows_paired"] = n
    return summary


def _count_consecutive_low(rows: List[Dict]) -> int:
    """Count consecutive days (from today backward) with rolling_30d_pct < 70."""
    count = 0
    for row in reversed(rows):
        pct = row.get("rolling_30d_pct")
        if pct is not None and pct < 70:
            count += 1
        else:
            break
    return count


# ---------------------------------------------------------------------------
# Read latest summary from Supabase
# ---------------------------------------------------------------------------

def get_calibration_summary() -> Optional[Dict[str, Any]]:
    """Return the most recent calibration summary row, or None."""
    if not is_configured():
        return None
    try:
        rows = supabase_get("capacity_calibration_summary?order=summary_date.desc&limit=1")
        return rows[0] if rows else None
    except Exception:
        return None


def get_calibration_status(summary: Optional[Dict]) -> str:
    """
    Return Green/Amber/Red calibration status for dashboard display.
      Green:  agreement_rate >= 85
      Amber:  agreement_rate 70–84
      Red:    agreement_rate < 70
    """
    if not summary or summary.get("agreement_rate") is None:
        return "Unknown"
    rate = float(summary["agreement_rate"])
    if rate >= 85:
        return "Green"
    if rate >= 70:
        return "Amber"
    return "Red"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run capacity calibration")
    parser.add_argument("--days", type=int, default=30, help="Window in days (default 30)")
    args = parser.parse_args()

    result = run_calibration(days=args.days)
    print(json.dumps(result, indent=2, default=str))
