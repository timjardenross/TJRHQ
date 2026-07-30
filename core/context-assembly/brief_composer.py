"""
Brief Composer — WP4

Composes CaptainBriefContext and CaptainOperatingPictureContext from
assembled context parts.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "core" / "context-assembly"))

from models import (
    CaptainBriefContext,
    CaptainOperatingPictureContext,
    HealthContextPackage,
    Recommendation,
    BlockerContextPackage,
    DecisionContextPackage,
    SystemHealthSummary,
    KeyDate,
    COPPriorityItem,
    OperationalStatus,
    BlockersSummary,
)


def compose_captain_brief(
    health: Optional[HealthContextPackage],
    top_priorities: List[Recommendation],
    blockers: List[BlockerContextPackage],
    decisions_awaiting_input: List[DecisionContextPackage],
    active_mission_count: int = 0,
    alert_count: int = 0,
    key_dates: Optional[List[KeyDate]] = None,
    number_one_summary: Optional[str] = None,
    source: str = "fresh",
) -> CaptainBriefContext:
    """
    Assemble the Captain's Daily Brief from its component parts.
    All inputs are optional — missing data produces safe defaults.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    blocked_count = len(blockers)
    has_critical = any(b.escalation_level == "critical" for b in blockers)
    has_high = any(b.escalation_level == "high" for b in blockers)
    cap_status = health.capacity_status if health else None

    if has_critical or alert_count > 0:
        sys_status = "red"
    elif has_high or cap_status == "Red":
        sys_status = "yellow"
    else:
        sys_status = "green"

    system_health = SystemHealthSummary(
        status=sys_status,
        alert_count=alert_count,
        active_mission_count=active_mission_count,
        blocked_mission_count=blocked_count,
    )

    return CaptainBriefContext(
        assembled_at=datetime.utcnow().isoformat() + "Z",
        date=today,
        source=source,
        health=health,
        top_priorities=top_priorities[:3],
        blockers=blockers,
        decisions_awaiting_input=decisions_awaiting_input,
        system_health=system_health,
        key_dates_this_week=key_dates or [],
        number_one_summary=number_one_summary,
    )


def compose_operating_picture(brief: CaptainBriefContext) -> CaptainOperatingPictureContext:
    """
    Distil the Captain's Brief into the 5-minute Operating Picture.
    This is the home-screen view — minimal, scannable.
    """
    # Health snapshot — includes capacity model status and calibration context
    health_snapshot = {}
    if brief.health and brief.health.data_quality != "missing":
        hs = brief.health.status_summary
        tt = brief.health.trend_summary

        # Pull latest calibration summary (best-effort; non-blocking)
        cal_accuracy = None
        cal_status = None
        captain_rating = None
        governance_flag = False
        try:
            import sys
            from pathlib import Path
            _h_root = Path(__file__).resolve().parents[2]
            sys.path.insert(0, str(_h_root / "core" / "health"))
            from calibration_engine import get_calibration_summary, get_calibration_status
            cal_summary = get_calibration_summary()
            if cal_summary:
                cal_accuracy = cal_summary.get("agreement_rate")
                cal_status = get_calibration_status(cal_summary)
                governance_flag = bool(cal_summary.get("weighting_review_flag"))
        except Exception:
            pass

        health_snapshot = {
            "pain_level": hs.pain_level,
            "energy": hs.energy,
            "trend": tt.overall_direction,
            "capacity_score": brief.health.capacity_score,
            "capacity_status": brief.health.capacity_status,
            "captain_self_rating": captain_rating,
            "model_accuracy_pct": cal_accuracy,
            "calibration_status": cal_status,
            "weighting_review_flag": governance_flag,
            "recovery_focus": (brief.health.recovery_priorities[0]
                               if brief.health.recovery_priorities else None),
        }

    # Top 3 priorities as COP items
    cop_priorities = [
        COPPriorityItem(
            rank=r.priority_rank,
            mission_id=r.mission_id,
            title=r.title,
            status="active",
            next_action=r.next_action,
            due_date=r.due_date,
            blocker_count=len(r.blockers),
        )
        for r in brief.top_priorities[:3]
    ]

    # Operational status
    sh = brief.system_health
    services_status = "all_green" if sh.status == "green" else (
        "critical" if sh.status == "red" else "warnings"
    )
    op_status = OperationalStatus(
        overall=sh.status,
        alert_count=sh.alert_count,
        active_missions=sh.active_mission_count,
        services_status=services_status,
    )

    # Blockers summary
    blockers_summary = BlockersSummary(
        count=len(brief.blockers),
        top_blocker=(brief.blockers[0].mission_title if brief.blockers else None),
    )

    # Quick actions — capacity-aware
    cap_status = brief.health.capacity_status if brief.health else None
    quick_actions = [
        {"label": "View Mission Details", "action": "open_missions"},
        {"label": "Open Slack", "action": "open_slack"},
        {"label": "Review Health", "action": "open_health"},
        {"label": "Weekly Review", "action": "open_weekly_review"},
        {"label": "Request XO Brief", "action": "request_xo_brief"},
    ]
    if cap_status == "Red":
        quick_actions.insert(0, {
            "label": "Capacity Red — Defer Non-Essential",
            "action": "review_capacity",
            "urgent": True,
        })
    if health_snapshot.get("weighting_review_flag"):
        quick_actions.insert(0, {
            "label": "Health Model Review Required — Notify XO",
            "action": "xo_model_review",
            "urgent": True,
        })

    return CaptainOperatingPictureContext(
        assembled_at=brief.assembled_at,
        source=brief.source,
        health_snapshot=health_snapshot,
        top_3_priorities=cop_priorities,
        operational_status=op_status,
        blockers_summary=blockers_summary,
        number_one_says=brief.number_one_summary,
        quick_actions=quick_actions,
    )
