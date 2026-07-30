"""Officer Scheduling Framework (EXEC-010A WP2).

Defines recurring autonomous officer activities. Reuses APScheduler where
available; degrades to a lightweight due-date check if scheduler unavailable.

No new database tables. Schedule state stored in decisions table:
  owner = `officer_schedule:{officer}:{activity_id}`
  rationale = `LAST_RUN: {iso} | NEXT_DUE: {iso} | COUNT: {n}`

Public API:
    ScheduleFrequency
    OfficerSchedule
    ScheduledActivity
    get_due_activities(ctx)             -> list[ScheduledActivity]
    record_activity_run(activity_id)    -> None
    OFFICER_SCHEDULES
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ── Enums ─────────────────────────────────────────────────────────────────────

class ScheduleFrequency(str, Enum):
    DAILY      = "daily"
    WEEKLY     = "weekly"
    MONTHLY    = "monthly"
    ON_TRIGGER = "on_trigger"   # fires only when a trigger fires, not on schedule


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class OfficerSchedule:
    activity_id: str
    officer: str
    activity: str
    frequency: ScheduleFrequency
    action_type: str
    description: str

    @property
    def interval_days(self) -> int:
        return {"daily": 1, "weekly": 7, "monthly": 30}.get(self.frequency.value, 0)


@dataclass
class ScheduledActivity:
    schedule: OfficerSchedule
    is_due: bool
    last_run: datetime | None = None
    next_due: datetime | None = None
    run_count: int = 0


# ── Schedule catalogue ────────────────────────────────────────────────────────

OFFICER_SCHEDULES: list[OfficerSchedule] = [

    # Medical Officer — Human Systems
    OfficerSchedule(
        activity_id="med_daily_capacity_review",
        officer="medical",
        activity="Daily capacity governance review",
        frequency=ScheduleFrequency.DAILY,
        action_type="review",
        description="Review capacity score and gate actions; flag anomalies",
    ),
    OfficerSchedule(
        activity_id="med_weekly_health_trend",
        officer="medical",
        activity="Weekly health trend analysis",
        frequency=ScheduleFrequency.WEEKLY,
        action_type="investigation",
        description="Analyse 7-day capacity patterns for structural health signals",
    ),

    # Research Officer
    OfficerSchedule(
        activity_id="research_daily_scan",
        officer="research",
        activity="Daily intelligence scan",
        frequency=ScheduleFrequency.DAILY,
        action_type="investigation",
        description="Scan ORI, investigations, and cross-domain signals for research priorities",
    ),
    OfficerSchedule(
        activity_id="research_weekly_synthesis",
        officer="research",
        activity="Weekly research synthesis",
        frequency=ScheduleFrequency.WEEKLY,
        action_type="improvement",
        description="Synthesise high-confidence findings into strategic intelligence brief",
    ),

    # Knowledge Officer
    OfficerSchedule(
        activity_id="knowledge_daily_capture",
        officer="knowledge",
        activity="Daily knowledge capture sweep",
        frequency=ScheduleFrequency.DAILY,
        action_type="improvement",
        description="Capture lesson candidates and advance knowledge lifecycle records",
    ),
    OfficerSchedule(
        activity_id="knowledge_weekly_quality",
        officer="knowledge",
        activity="Weekly knowledge quality review",
        frequency=ScheduleFrequency.WEEKLY,
        action_type="review",
        description="Assess knowledge quality metrics and identify decay patterns",
    ),
    OfficerSchedule(
        activity_id="knowledge_monthly_cross_domain",
        officer="knowledge",
        activity="Monthly cross-domain knowledge integration",
        frequency=ScheduleFrequency.MONTHLY,
        action_type="improvement",
        description="Integrate cross-domain patterns into organisational knowledge base",
    ),

    # Chief Engineer
    OfficerSchedule(
        activity_id="eng_daily_delivery_scan",
        officer="engineering",
        activity="Daily delivery status scan",
        frequency=ScheduleFrequency.DAILY,
        action_type="review",
        description="Monitor engineering mission status, blockers, and velocity signals",
    ),
    OfficerSchedule(
        activity_id="eng_weekly_debt_review",
        officer="engineering",
        activity="Weekly technical debt review",
        frequency=ScheduleFrequency.WEEKLY,
        action_type="technical_debt_review",
        description="Review critical and increasing tech debt items; update remediation status",
    ),
    OfficerSchedule(
        activity_id="eng_monthly_capability_assessment",
        officer="engineering",
        activity="Monthly capability maturity assessment",
        frequency=ScheduleFrequency.MONTHLY,
        action_type="capability_improvement",
        description="Assess capability maturity progression and flag deterioration",
    ),

    # Operations Officer (Number One)
    OfficerSchedule(
        activity_id="n1_daily_mission_sweep",
        officer="number_one",
        activity="Daily mission coordination sweep",
        frequency=ScheduleFrequency.DAILY,
        action_type="review",
        description="Review mission assignments, blockers, and escalation queue",
    ),
    OfficerSchedule(
        activity_id="n1_weekly_program_health",
        officer="number_one",
        activity="Weekly program health review",
        frequency=ScheduleFrequency.WEEKLY,
        action_type="review",
        description="Assess delivery forecast, resource conflicts, and program interventions",
    ),

    # QA Validation Officer
    OfficerSchedule(
        activity_id="qa_daily_decision_gate",
        officer="qa",
        activity="Daily decision package quality gate",
        frequency=ScheduleFrequency.DAILY,
        action_type="review",
        description="Validate decision packages before XO review; flag quality issues",
    ),
    OfficerSchedule(
        activity_id="qa_weekly_benefit_integrity",
        officer="qa",
        activity="Weekly benefit tracking integrity check",
        frequency=ScheduleFrequency.WEEKLY,
        action_type="review",
        description="Verify benefit lifecycle records are current and accurately reflect reality",
    ),

    # XO
    OfficerSchedule(
        activity_id="xo_daily_synthesis",
        officer="xo",
        activity="Daily officer output synthesis",
        frequency=ScheduleFrequency.DAILY,
        action_type="review",
        description="Synthesise all officer outputs into consolidated XO brief for Captain",
    ),
    OfficerSchedule(
        activity_id="xo_weekly_investment_review",
        officer="xo",
        activity="Weekly investment governance review",
        frequency=ScheduleFrequency.WEEKLY,
        action_type="review",
        description="Review investment portfolio, business cases, and benefit assurance status",
    ),
]

_SCHEDULE_INDEX: dict[str, OfficerSchedule] = {s.activity_id: s for s in OFFICER_SCHEDULES}
_SCHEDULE_OWNER_PREFIX = "officer_schedule:"


# ── Schedule state retrieval ──────────────────────────────────────────────────

def _get_schedule_state(activity_id: str) -> tuple[datetime | None, int]:
    """Return (last_run, run_count) from decisions table. Returns (None, 0) on miss."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return None, 0

        owner = f"{_SCHEDULE_OWNER_PREFIX}{activity_id}"
        res = c.raw_client.table("decisions").select("rationale").eq("owner", owner).limit(1).execute()
        rows = list(res.data or [])
        if not rows:
            return None, 0

        rationale = rows[0].get("rationale", "")
        last_run: datetime | None = None
        run_count = 0
        for part in rationale.split("|"):
            part = part.strip()
            if part.startswith("LAST_RUN:"):
                try:
                    last_run = datetime.fromisoformat(part.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif part.startswith("COUNT:"):
                try:
                    run_count = int(part.split(":", 1)[1].strip())
                except ValueError:
                    pass
        return last_run, run_count
    except Exception as exc:
        log.debug("[officer_schedules] State retrieval failed for %s: %s", activity_id, exc)
        return None, 0


def _is_due(schedule: OfficerSchedule, last_run: datetime | None) -> bool:
    """Return True if the activity is due to run based on its frequency."""
    if schedule.frequency == ScheduleFrequency.ON_TRIGGER:
        return False
    if last_run is None:
        return True
    interval = timedelta(days=schedule.interval_days)
    return (datetime.utcnow() - last_run) >= interval


# ── Public API ────────────────────────────────────────────────────────────────

def get_due_activities(ctx: Any = None) -> list[ScheduledActivity]:
    """Return all officer scheduled activities that are currently due."""
    due: list[ScheduledActivity] = []
    for schedule in OFFICER_SCHEDULES:
        if schedule.frequency == ScheduleFrequency.ON_TRIGGER:
            continue
        try:
            last_run, run_count = _get_schedule_state(schedule.activity_id)
            next_due = (
                (last_run + timedelta(days=schedule.interval_days)) if last_run else datetime.utcnow()
            )
            is_due = _is_due(schedule, last_run)
            due.append(ScheduledActivity(
                schedule=schedule,
                is_due=is_due,
                last_run=last_run,
                next_due=next_due,
                run_count=run_count,
            ))
        except Exception as exc:
            log.debug("[officer_schedules] Due check failed for %s: %s", schedule.activity_id, exc)
    return [a for a in due if a.is_due]


def record_activity_run(activity_id: str) -> None:
    """Record that a scheduled activity ran. Updates or creates the state record."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return

        schedule = _SCHEDULE_INDEX.get(activity_id)
        if not schedule:
            return

        last_run, run_count = _get_schedule_state(activity_id)
        now = datetime.utcnow()
        next_due = now + timedelta(days=schedule.interval_days)
        new_count = run_count + 1

        owner = f"{_SCHEDULE_OWNER_PREFIX}{activity_id}"
        rationale = f"LAST_RUN: {now.isoformat()} | NEXT_DUE: {next_due.isoformat()} | COUNT: {new_count}"
        statement = f"[OFFICER SCHEDULE] {activity_id}: {schedule.activity}"

        existing = c.raw_client.table("decisions").select("id").eq("owner", owner).limit(1).execute()
        if list(existing.data or []):
            c.raw_client.table("decisions").update({
                "rationale": rationale,
                "statement": statement,
                "updated_at": now.isoformat(),
            }).eq("owner", owner).execute()
        else:
            c.raw_client.table("decisions").insert({
                "owner": owner,
                "statement": statement,
                "rationale": rationale,
                "decision_type": "officer_schedule",
                "status": "active",
            }).execute()

        log.info("[officer_schedules] Recorded run: %s (count=%d)", activity_id, new_count)
    except Exception as exc:
        log.debug("[officer_schedules] Record run failed for %s: %s", activity_id, exc)


__all__ = [
    "ScheduleFrequency",
    "OfficerSchedule",
    "ScheduledActivity",
    "OFFICER_SCHEDULES",
    "get_due_activities",
    "record_activity_run",
]
