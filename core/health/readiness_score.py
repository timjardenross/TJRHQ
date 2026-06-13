"""
Captain Readiness Score — M-20260614 WP7

Combines health capacity with operational load to produce a single
0–100 readiness score indicating how well-positioned the Captain is
for effective work today.

Formula (fully documented, no black-box):

  readiness = health_component (60%) + ops_component (40%)

  health_component (0–60 pts):
    Derived from capacity_score (0–100) scaled to 0–60.

  ops_component (0–40 pts):
    Starts at 40, deductions applied:
      - Each blocked P0 mission:   -10 pts (max -20)
      - Each blocked P1 mission:   -5  pts (max -10)
      - Pending escalations:       -5  per critical (max -10)
      - Total active missions > 8: -5  pts (overload signal)

Score is clamped 0–100.
Status thresholds mirror capacity_score:
  Green  >= 75
  Amber  50–74
  Red    < 50

All contributors are returned for full auditability.
No data is written. Score is advisory only.

Public API:
    compute_readiness_score(capacity_score, missions, escalations) -> ReadinessResult
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
) -> ReadinessResult:
    """
    Compute Captain Readiness Score.

    Args:
        capacity_score:  0–100 from capacity_score.compute_capacity_score(), or None
        capacity_status: "Green" | "Amber" | "Red" | "Unknown"
        missions:        list of mission dicts from mission registry
        escalations:     list of escalation dicts from Number One (optional)

    Returns:
        ReadinessResult with score, status, contributors, and recommended focus
    """
    contributors: list[str] = []
    escalations = escalations or []

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
