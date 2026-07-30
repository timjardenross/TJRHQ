"""
Captain Readiness Score — M-20260614 WP7 + M-20260613-INTELLIGENCE-MATURITY-PHASE2 WP8

Combines health capacity with operational load to produce a single
0–100 readiness score indicating how well-positioned the Captain is
for effective work today.

Formula (fully documented, no black-box):

  readiness = health_component (60%) + ops_component (40%)

  health_component (0–60 pts):
    Derived from capacity_score (0–100) scaled to 0–60.
    Enhanced signals (WP8):
      - Pain spike penalty:      -8 pts if pain_score >= 8
      - Sleep deprivation:       -8 pts if sleep_hours < 5
      - CPAP compliance bonus:   +4 pts if cpap_used and cpap_hours >= 5
      - Low mood penalty:        -4 pts if mood == 'Low'

  ops_component (0–40 pts):
    Starts at 40, deductions applied:
      - Each blocked P0 mission:   -10 pts (max -20)
      - Each blocked P1 mission:   -5  pts (max -10)
      - Pending escalations:       -5  per critical (max -10)
      - Total active missions > 8: -5  pts (overload signal)
      - Upcoming deadlines (WP8):  -3  pts per P0/P1 due within 3 days (max -6)

Score is clamped 0–100.
Status thresholds mirror capacity_score:
  Green  >= 75
  Amber  50–74
  Red    < 50

All contributors are returned for full auditability.
No data is written. Score is advisory only.

Public API:
    compute_readiness_score(capacity_score, missions, escalations,
                            health_entry, cpap_hours) -> ReadinessResult
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

READINESS_THRESHOLDS = {
    "Green": 75,
    "Amber": 50,
    # below 50: Red
}

HEALTH_WEIGHT     = 0.60   # 60 pts max
OPS_BASE          = 40     # starts at 40, deductions applied

BLOCKED_P0_COST   = 10     # per P0 blocked mission
BLOCKED_P0_MAX    = 20
BLOCKED_P1_COST   = 5      # per P1 blocked mission
BLOCKED_P1_MAX    = 10
ESCALATION_COST   = 5      # per critical escalation
ESCALATION_MAX    = 10
OVERLOAD_COST     = 5      # when active mission count > OVERLOAD_THRESHOLD
OVERLOAD_THRESHOLD = 8

# WP8 — Enhanced health signal costs
PAIN_SPIKE_THRESHOLD  = 8      # pain_score >= 8 triggers penalty
PAIN_SPIKE_PENALTY    = 8
SLEEP_DEPRIVATION_HRS = 5.0    # sleep_hours < 5 triggers penalty
SLEEP_DEPRIVATION_PENALTY = 8
CPAP_BONUS            = 4      # cpap_used + cpap_hours >= 5
CPAP_BONUS_MIN_HOURS  = 5.0
LOW_MOOD_PENALTY      = 4
DEADLINE_PRESSURE_COST = 3     # per P0/P1 due within 3 days
DEADLINE_PRESSURE_MAX  = 6
DEADLINE_NEAR_DAYS     = 3


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class ReadinessResult:
    score: int                        # 0–100
    status: str                       # "Green" | "Amber" | "Red" | "Unknown"
    health_component: int             # pts contributed by health (0–60)
    ops_component: int                # pts contributed by ops (0–40)
    contributors: list[str]           # plain-language explanations
    recommended_focus: list[str]      # top 3 suggested focus areas
    capacity_status: str              # underlying health status
    methodology: str = field(default=(
        "readiness = health_component (60%) + ops_component (40%); "
        "health scaled from capacity_score; ops starts at 40 with deductions "
        "for blocked P0/P1 missions, critical escalations, mission overload"
    ))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_readiness_score(
    capacity_score: Optional[int],
    capacity_status: str,
    missions: list[dict[str, Any]],
    escalations: list[dict[str, Any]] | None = None,
    health_entry: dict[str, Any] | None = None,
    cpap_hours: Optional[float] = None,
) -> ReadinessResult:
    """
    Compute Captain Readiness Score.

    Args:
        capacity_score:  0–100 from capacity_score.compute_capacity_score(), or None
        capacity_status: "Green" | "Amber" | "Red" | "Unknown"
        missions:        list of mission dicts from mission registry
        escalations:     list of escalation dicts from Number One (optional)
        health_entry:    today's health log dict for enhanced signals (WP8, optional)
        cpap_hours:      CPAP hours used last night for compliance bonus (WP8, optional)

    Returns:
        ReadinessResult with score, status, contributors, and recommended focus
    """
    contributors: list[str] = []
    escalations = escalations or []
    he = health_entry or {}

    # ── Health component ────────────────────────────────────────────────────
    if capacity_score is None:
        health_pts = 30  # neutral assumption when no data
        contributors.append("Health data unavailable — neutral assumption applied (30/60 pts)")
    else:
        health_pts = round(capacity_score * HEALTH_WEIGHT)
        deduction = 60 - health_pts
        if deduction == 0:
            contributors.append(f"Health at full capacity — {health_pts}/60 pts")
        elif deduction <= 10:
            contributors.append(f"Health slightly reduced — {health_pts}/60 pts (capacity score {capacity_score})")
        elif deduction <= 25:
            contributors.append(f"Health moderately reduced — {health_pts}/60 pts (capacity score {capacity_score})")
        else:
            contributors.append(f"Health significantly reduced — {health_pts}/60 pts (capacity score {capacity_score})")

    # ── WP8: Enhanced health signals ────────────────────────────────────────
    # Applied as direct adjustments to health_pts (clamped to 0–60 after)
    try:
        pain = float(he.get("pain_score") or 0)
        if pain >= PAIN_SPIKE_THRESHOLD:
            health_pts -= PAIN_SPIKE_PENALTY
            contributors.append(
                f"Acute pain spike (pain={pain:.0f}≥{PAIN_SPIKE_THRESHOLD}) — -{PAIN_SPIKE_PENALTY} pts"
            )
    except (TypeError, ValueError):
        pass

    try:
        slp = float(he.get("sleep_hours") or 0)
        if 0 < slp < SLEEP_DEPRIVATION_HRS:
            health_pts -= SLEEP_DEPRIVATION_PENALTY
            contributors.append(
                f"Sleep deprivation ({slp:.1f}h < {SLEEP_DEPRIVATION_HRS}h minimum) — -{SLEEP_DEPRIVATION_PENALTY} pts"
            )
    except (TypeError, ValueError):
        pass

    cpap_raw = he.get("cpap_status") or he.get("cpap_used")
    cpap_flag = False
    if cpap_raw is not None:
        if isinstance(cpap_raw, bool):
            cpap_flag = cpap_raw
        else:
            cpap_flag = str(cpap_raw).lower().strip() in ("yes", "true", "1")
    try:
        _cpap_h = float(cpap_hours or he.get("cpap_hours") or 0)
        if cpap_flag and _cpap_h >= CPAP_BONUS_MIN_HOURS:
            health_pts += CPAP_BONUS
            contributors.append(f"CPAP compliance ({_cpap_h:.1f}h) — +{CPAP_BONUS} pts")
    except (TypeError, ValueError):
        pass

    mood_raw = str(he.get("mood") or "").lower().strip()
    if mood_raw == "low":
        health_pts -= LOW_MOOD_PENALTY
        contributors.append(f"Low mood today — -{LOW_MOOD_PENALTY} pts")

    health_pts = max(0, min(60, health_pts))

    # ── Ops component ───────────────────────────────────────────────────────
    ops_pts = OPS_BASE
    ops_deductions: list[str] = []

    blocked_p0 = [m for m in missions if
                  _get_priority(m) == "P0" and _is_blocked(m)]
    blocked_p1 = [m for m in missions if
                  _get_priority(m) == "P1" and _is_blocked(m)]
    critical_escalations = [e for e in escalations if
                             e.get("level", "").lower() == "critical"]
    active_count = len([m for m in missions if not _is_terminal(m)])

    if blocked_p0:
        cost = min(len(blocked_p0) * BLOCKED_P0_COST, BLOCKED_P0_MAX)
        ops_pts -= cost
        ids = ", ".join(m.get("mission_id", "?") for m in blocked_p0[:3])
        ops_deductions.append(f"{len(blocked_p0)} P0 mission(s) blocked ({ids}) — -{cost} pts")

    if blocked_p1:
        cost = min(len(blocked_p1) * BLOCKED_P1_COST, BLOCKED_P1_MAX)
        ops_pts -= cost
        ops_deductions.append(f"{len(blocked_p1)} P1 mission(s) blocked — -{cost} pts")

    if critical_escalations:
        cost = min(len(critical_escalations) * ESCALATION_COST, ESCALATION_MAX)
        ops_pts -= cost
        ops_deductions.append(f"{len(critical_escalations)} critical escalation(s) — -{cost} pts")

    if active_count > OVERLOAD_THRESHOLD:
        ops_pts -= OVERLOAD_COST
        ops_deductions.append(f"Mission overload ({active_count} active missions) — -{OVERLOAD_COST} pts")

    # WP8: Deadline pressure
    try:
        from zoneinfo import ZoneInfo as _ZI
        from datetime import datetime as _dt
        today_str = _dt.now(_ZI("Australia/Brisbane")).date().isoformat()
    except Exception:
        from datetime import date as _date
        today_str = _date.today().isoformat()
    near_deadline = [
        m for m in missions
        if _get_priority(m) in ("P0", "P1")
        and not _is_terminal(m)
        and _days_until_due(m, today_str) is not None
        and 0 <= _days_until_due(m, today_str) <= DEADLINE_NEAR_DAYS
    ]
    if near_deadline:
        cost = min(len(near_deadline) * DEADLINE_PRESSURE_COST, DEADLINE_PRESSURE_MAX)
        ops_pts -= cost
        ids = ", ".join(m.get("mission_id", m.get("id", "?")) for m in near_deadline[:2])
        ops_deductions.append(
            f"{len(near_deadline)} mission(s) due within {DEADLINE_NEAR_DAYS} days ({ids}) — -{cost} pts"
        )

    ops_pts = max(0, ops_pts)

    if ops_deductions:
        contributors.extend(ops_deductions)
    else:
        contributors.append(f"Operational load clear — {ops_pts}/40 pts")

    # ── Total score ─────────────────────────────────────────────────────────
    raw_score = health_pts + ops_pts
    score = max(0, min(100, raw_score))

    if score >= READINESS_THRESHOLDS["Green"]:
        status = "Green"
    elif score >= READINESS_THRESHOLDS["Amber"]:
        status = "Amber"
    else:
        status = "Red"

    # ── Recommended focus ───────────────────────────────────────────────────
    recommended_focus = _build_recommended_focus(
        capacity_status, blocked_p0, blocked_p1, active_count, missions
    )

    return ReadinessResult(
        score=score,
        status=status,
        health_component=health_pts,
        ops_component=ops_pts,
        contributors=contributors,
        recommended_focus=recommended_focus,
        capacity_status=capacity_status,
    )


# ---------------------------------------------------------------------------
# Recommended focus builder
# ---------------------------------------------------------------------------

def _build_recommended_focus(
    capacity_status: str,
    blocked_p0: list[dict],
    blocked_p1: list[dict],
    active_count: int,
    missions: list[dict],
) -> list[str]:
    focus = []

    if capacity_status == "Red":
        focus.append("Prioritise rest and recovery — operate in minimal-load mode today")
        if blocked_p0:
            focus.append(f"Critical: unblock {blocked_p0[0].get('title', blocked_p0[0].get('mission_id', 'P0 mission'))}")
        else:
            focus.append("P0 missions only — defer all non-critical work")
        return focus[:3]

    if blocked_p0:
        focus.append(f"Unblock P0: {blocked_p0[0].get('title', blocked_p0[0].get('mission_id', ''))}")

    # Surface top non-blocked P0 or P1 missions
    top = [m for m in missions if
           _get_priority(m) in ("P0", "P1") and not _is_blocked(m) and not _is_terminal(m)]
    for m in top[:2]:
        title = m.get("title", m.get("mission_id", ""))
        priority = _get_priority(m)
        focus.append(f"{priority}: {title}")

    if capacity_status == "Amber" and not focus:
        focus.append("Reduced capacity day — focus on communication and planning over deep work")

    if not focus:
        focus.append("No P0/P1 missions active — review mission backlog for next priority")

    return focus[:3]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TERMINAL = {"Closed", "Archived", "COMPLETED", "DEFERRED", "CANCELLED"}
_BLOCKED  = {"Blocked", "BLOCKED", "BLOCKED_OPS"}


def _get_priority(m: dict) -> str:
    return str(m.get("priority", "P3")).upper()


def _is_blocked(m: dict) -> bool:
    return str(m.get("status", "")).strip() in _BLOCKED


def _is_terminal(m: dict) -> bool:
    return str(m.get("status", "")).strip() in _TERMINAL


def _days_until_due(m: dict, today_str: str) -> Optional[int]:
    due = m.get("due_date") or m.get("deadline")
    if not due:
        return None
    try:
        from datetime import date as _d
        return (_d.fromisoformat(str(due)[:10]) - _d.fromisoformat(today_str)).days
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Formatting helper (used by scheduler and Slack delivery)
# ---------------------------------------------------------------------------

_STATUS_EMOJI = {"Green": ":large_green_circle:", "Amber": ":large_yellow_circle:", "Red": ":red_circle:", "Unknown": ":white_circle:"}


def format_readiness_for_slack(result: ReadinessResult) -> str:
    """Format a ReadinessResult as a Slack message block."""
    emoji = _STATUS_EMOJI.get(result.status, ":white_circle:")
    lines = [
        f"{emoji} *Captain Readiness: {result.score}/100 ({result.status})*",
        f"  Health: {result.health_component}/60 pts  |  Operations: {result.ops_component}/40 pts",
        "",
    ]
    lines.append("*Contributors:*")
    for c in result.contributors:
        lines.append(f"  • {c}")
    lines.append("")
    if result.recommended_focus:
        lines.append("*Recommended Focus:*")
        for f in result.recommended_focus:
            lines.append(f"  • {f}")
    return "\n".join(lines)
