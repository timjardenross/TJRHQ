"""
Captain Capacity Model — WP3

Computes a 0–100 operational capacity score from a captains_log_entries row.

Formula is centralised here. Change the weights in WEIGHTS to recalibrate.
The formula deliberately avoids storing the score in captains_log_entries so
that recalibration does not require a data migration.

Usage:
    from core.health.capacity_score import compute_capacity_score, CAPACITY_THRESHOLDS

    score, status = compute_capacity_score(entry)
    # score: int 0–100
    # status: "Green" | "Amber" | "Red"
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Configurable weights — adjust here to recalibrate without schema changes
# ---------------------------------------------------------------------------

WEIGHTS = {
    # Pain deduction: full pain_score 10 → 35 pts deducted
    "pain_max_deduction": 35,

    # Energy deductions
    "energy_low": 20,
    "energy_moderate": 8,
    "energy_high": 0,

    # Sleep deductions
    "sleep_lt_5h": 15,
    "sleep_lt_6h": 8,
    "sleep_gte_6h": 0,

    # Sleep quality deductions (WP-5)
    "sleep_quality_poor": 5,
    "sleep_quality_fair": 2,
    "sleep_quality_good": 0,
    "sleep_quality_excellent": 0,

    # Mood deductions
    "mood_low": 10,
    "mood_stable": 4,
    "mood_positive": 0,

    # Physical capacity modifier
    "capacity_worse": -10,
    "capacity_same": 0,
    "capacity_better": 5,
}

CAPACITY_THRESHOLDS = {
    "Green": 80,   # 80–100: full capacity
    "Amber": 55,   # 55–79: reduced capacity
    # below 55: Red — significantly constrained
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_capacity_score(entry: Dict[str, Any]) -> Tuple[Optional[int], str]:
    """
    Compute capacity score and status from a captains_log_entries row.

    Returns (score, status) where:
      score  — int 0–100, or None if no usable data
      status — "Green" | "Amber" | "Red" | "Unknown"

    Fields consumed (all optional):
      pain_score        : int 0–10
      energy            : "Low" | "Moderate" | "High"
      sleep_hours       : float
      sleep_quality     : "Poor" | "Fair" | "Good"  (also accepts lowercase)
      mood              : "Low" | "Stable" | "Positive"
      physical_capacity : "Better" | "Same" | "Worse"
    """
    if not entry:
        return None, "Unknown"

    usable_fields = [
        entry.get("pain_score"),
        entry.get("energy"),
        entry.get("sleep_hours"),
        entry.get("sleep_quality"),
        entry.get("mood"),
        entry.get("physical_capacity"),
    ]
    if all(v is None for v in usable_fields):
        return None, "Unknown"

    score = 100

    # Pain deduction
    pain = entry.get("pain_score")
    if pain is not None:
        try:
            score -= round((float(pain) / 10.0) * WEIGHTS["pain_max_deduction"])
        except (TypeError, ValueError):
            pass

    # Energy deduction
    energy = (entry.get("energy") or "").strip()
    score -= WEIGHTS.get(f"energy_{energy.lower()}", 0)

    # Sleep deduction
    sleep_h = entry.get("sleep_hours")
    if sleep_h is not None:
        try:
            h = float(sleep_h)
            if h < 5:
                score -= WEIGHTS["sleep_lt_5h"]
            elif h < 6:
                score -= WEIGHTS["sleep_lt_6h"]
        except (TypeError, ValueError):
            pass

    # Sleep quality deduction (WP-5)
    sleep_q = (entry.get("sleep_quality") or "").strip().lower()
    score -= WEIGHTS.get(f"sleep_quality_{sleep_q}", 0)

    # Mood deduction
    mood = (entry.get("mood") or "").strip()
    score -= WEIGHTS.get(f"mood_{mood.lower()}", 0)

    # Physical capacity modifier
    cap = (entry.get("physical_capacity") or "").strip().lower()
    score += WEIGHTS.get(f"capacity_{cap}", 0)

    # Clamp
    score = max(0, min(100, score))

    # Status
    if score >= CAPACITY_THRESHOLDS["Green"]:
        status = "Green"
    elif score >= CAPACITY_THRESHOLDS["Amber"]:
        status = "Amber"
    else:
        status = "Red"

    return score, status


def capacity_zone_from_checkin(row: Optional[Dict[str, Any]]) -> Tuple[Optional[int], str]:
    """
    Capacity Gate adapter (D-055) — MY CAPACITY TODAY replaced Recovery
    Pulse/captains_log_entries as the Captain's day-to-day capacity input
    2026-08-21. This maps a `capacity_checkins` row's `capacity_state`
    (green/orange/red — the Captain's own report) directly onto the Gate's
    existing Green/Amber/Red vocabulary, which is the same trichotomy
    already, just spelled differently.

    Unlike compute_capacity_score(), there's no weighted formula here — the
    new model doesn't compute a proxy score from component signals, the
    Captain's own capacity_state IS the signal. The nominal score
    (green=90, orange=60, red=25) exists only so callers written against
    compute_capacity_score()'s (score, status) contract keep working
    unchanged — nothing should treat this score as more precise than the
    3-way zone it's derived from.

    Args:
        row: the most recent capacity_checkins row for the day in question
             (checkin_type='capacity'), or None/{} if no check-in yet.

    Returns:
        (score, status) — same shape as compute_capacity_score(), so this
        is a drop-in replacement at every call site.
    """
    if not row or not row.get("capacity_state"):
        return None, "Unknown"

    zone_score = {"green": 90, "orange": 60, "red": 25}
    zone_status = {"green": "Green", "orange": "Amber", "red": "Red"}

    state = row["capacity_state"]
    return zone_score.get(state), zone_status.get(state, "Unknown")


def capacity_status_only(score: Optional[int]) -> str:
    """Derive status string from a pre-computed score."""
    if score is None:
        return "Unknown"
    if score >= CAPACITY_THRESHOLDS["Green"]:
        return "Green"
    if score >= CAPACITY_THRESHOLDS["Amber"]:
        return "Amber"
    return "Red"


def describe_weights() -> Dict[str, Any]:
    """Return the current weight configuration for documentation/API output."""
    return {
        "weights": WEIGHTS,
        "thresholds": CAPACITY_THRESHOLDS,
        "formula": (
            "score = 100 "
            "- (pain_score/10 × pain_max_deduction) "
            "- energy_deduction "
            "- sleep_hours_deduction "
            "- sleep_quality_deduction "
            "- mood_deduction "
            "+ physical_capacity_modifier, "
            "clamped 0–100"
        ),
    }
