"""
Mission Risk Scoring Engine — WP3

Replaces rule-based mission prioritisation with a continuous 0–100 risk score.
Higher score = higher operational risk = higher priority for Captain attention.

Score components (capped at 100):
  Status component (max 40):
    BLOCKED / BLOCKED_OPS          = 40
    Awaiting XO Approval           = 28
    Awaiting Number One Review     = 18
    IN_PROGRESS / Active > 14d     =  8
    Other active                   =  0

  Age component (max 30):
    ≥ 21 days                      = 30
    ≥ 14 days                      = 22
    ≥  7 days                      = 14
    ≥  3 days                      =  8
    < 3 days                       =  0

  Priority component (max 20):
    Critical / P0                  = 20
    High / P1                      = 12
    Normal / P2                    =  4
    Low / P3+                      =  0

  Governance component (max 10):
    Missing lesson learned         =  5
    Missing validation evidence    =  5

Risk bands:
  0–25   Low
  26–50  Moderate
  51–75  High
  76–100 Critical
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Status scores
# ---------------------------------------------------------------------------

_STATUS_SCORES: dict[str, int] = {
    "blocked":                    40,
    "blocked_ops":                40,
    "blocked_by":                 40,
    "awaiting xo approval":       28,
    "awaiting number one review": 18,
}

_ACTIVE_STATUSES = {
    "active", "in_progress", "in progress", "open", "analysis",
    "design", "validation in progress",
}

# ---------------------------------------------------------------------------
# Priority scores
# ---------------------------------------------------------------------------

_PRIORITY_SCORES: dict[str, int] = {
    "critical": 20,
    "p0":       20,
    "high":     12,
    "p1":       12,
    "normal":   4,
    "medium":   4,
    "p2":       4,
    "low":      0,
    "p3":       0,
}

# ---------------------------------------------------------------------------
# Risk bands
# ---------------------------------------------------------------------------

_BANDS = [
    (76, "Critical"),
    (51, "High"),
    (26, "Moderate"),
    (0,  "Low"),
]

_BAND_EMOJI = {
    "Critical": ":sos:",
    "High":     ":rotating_light:",
    "Moderate": ":warning:",
    "Low":      ":white_check_mark:",
}


def _band(score: int) -> str:
    for threshold, label in _BANDS:
        if score >= threshold:
            return label
    return "Low"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def calculate_mission_risk_score(mission: dict) -> dict:
    """
    Compute a risk score for a single mission.

    Args:
        mission: dict with keys:
            id, title, status, priority (optional), timestamp (optional),
            description (optional)

    Returns:
        {
            mission_id:   str
            score:        int  (0–100)
            band:         str  (Low / Moderate / High / Critical)
            components:   {status, age, priority, governance}
            reasons:      list[str]
            band_emoji:   str
        }
    """
    mission_id = mission.get("id", "")
    status_raw = mission.get("status", "")
    status     = status_raw.lower().strip()
    priority   = (mission.get("priority") or "").lower().strip()

    reasons: list[str] = []

    # --- Status component ---
    status_score = _STATUS_SCORES.get(status, 0)
    if status_score:
        reasons.append(f"Status: {status_raw}")
    elif status in _ACTIVE_STATUSES:
        status_score = 0  # age component will penalise long-running active missions

    # --- Age component ---
    open_date = _parse_open_date(mission_id, mission.get("timestamp", ""))
    age_days  = (date.today() - open_date).days if open_date else None

    age_score = 0
    if age_days is not None:
        if age_days >= 21:
            age_score = 30
            reasons.append(f"Open {age_days} days (severely overdue)")
        elif age_days >= 14:
            age_score = 22
            reasons.append(f"Open {age_days} days (overdue)")
        elif age_days >= 7:
            age_score = 14
            reasons.append(f"Open {age_days} days")
        elif age_days >= 3:
            age_score = 8
            reasons.append(f"Open {age_days} days (early escalation)")

    # --- Priority component ---
    priority_score = _PRIORITY_SCORES.get(priority, 0)

    # --- Governance component ---
    gov_score = 0
    try:
        from captain_notifications import check_lesson_captured
        if status in ("completed", "closed") and not check_lesson_captured(mission_id):
            gov_score += 5
            reasons.append("Missing lesson learned")
    except Exception:
        pass

    if _missing_validation(mission_id):
        gov_score += 5
        reasons.append("Missing validation evidence")

    # --- Total (capped at 100) ---
    raw = status_score + age_score + priority_score + gov_score
    score = min(100, raw)
    band  = _band(score)

    return {
        "mission_id": mission_id,
        "title":      mission.get("description") or mission.get("title", ""),
        "status":     status_raw,
        "score":      score,
        "band":       band,
        "band_emoji": _BAND_EMOJI.get(band, ":grey_question:"),
        "components": {
            "status":     status_score,
            "age":        age_score,
            "priority":   priority_score,
            "governance": gov_score,
        },
        "reasons": reasons,
    }


def _parse_open_date(mission_id: str, timestamp: str) -> Optional[date]:
    """Extract open date from mission ID or timestamp fallback."""
    parts = mission_id.split("-")
    for p in parts:
        if len(p) == 8 and p.isdigit():
            try:
                return datetime.strptime(p, "%Y%m%d").date()
            except ValueError:
                continue
    if timestamp:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(timestamp[:16], fmt).date()
            except ValueError:
                continue
    return None


def _missing_validation(mission_id: str) -> bool:
    """Heuristically check whether validation evidence is absent for this mission."""
    try:
        active_dir = _REPO_ROOT / "Missions" / "Active"
        if not active_dir.exists():
            return False
        for f in active_dir.iterdir():
            if mission_id in f.name:
                text = f.read_text()
                indicators = ["validation", "validated", "acceptance criteria", "test passed"]
                if not any(ind in text.lower() for ind in indicators):
                    return True
                return False
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Top-N risk missions
# ---------------------------------------------------------------------------

def get_top_risk_missions(limit: int = 10) -> list[dict]:
    """
    Score all active missions from the mission index and return the top-N by risk.

    Returns list of scored mission dicts, sorted by score descending.
    Excludes COMPLETED / CLOSED missions.
    """
    try:
        from captain_notifications import _read_mission_index
        missions = _read_mission_index()
    except Exception as exc:
        log.warning("[risk] Failed to read mission index: %s", exc)
        return []

    exclude = {"completed", "closed", "cancelled", "complete", "assessment complete",
               "design complete", "deployed"}
    active = [m for m in missions if m.get("status", "").lower() not in exclude]

    scored = [calculate_mission_risk_score(m) for m in active]
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:limit]


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_risk_report(scored: list[dict], title: str = "Mission Risk Report") -> str:
    """Format top-N risk missions as a Slack message."""
    if not scored:
        return ":white_check_mark: *No active missions at elevated risk.*"

    lines = [f":chart_with_upwards_trend: *{title}*"]
    for i, r in enumerate(scored, 1):
        emoji   = r["band_emoji"]
        reasons = " · ".join(r["reasons"]) if r["reasons"] else "No specific risk factors"
        lines.append(
            f"  {i}. {emoji} *{r['mission_id']}* — Risk: {r['score']} ({r['band']})\n"
            f"     _{r['title'][:60]}_\n"
            f"     Factors: {reasons}"
        )
    return "\n".join(lines)


def format_risk_brief_block(limit: int = 3) -> str:
    """
    Return a compact risk block for the morning brief.
    Only emitted if any mission scores ≥ 51 (High or Critical).
    """
    try:
        top = get_top_risk_missions(limit=10)
        high_risk = [r for r in top if r["score"] >= 51]
        if not high_risk:
            return ""

        lines = [f":rotating_light: *Top {min(limit, len(high_risk))} High-Risk Missions:*"]
        for r in high_risk[:limit]:
            emoji = r["band_emoji"]
            lines.append(f"  • {emoji} *{r['mission_id']}* — {r['score']}/100 ({r['band']}) — {r['reasons'][0] if r['reasons'] else ''}")
        return "\n".join(lines)
    except Exception as exc:
        log.debug("[risk] Brief block failed: %s", exc)
        return ""
