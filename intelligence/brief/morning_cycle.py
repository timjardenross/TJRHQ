"""
Morning collection cycle readiness (Briefs canonical uplift, Sections 4-6).

Ties daily brief generation to the ACTUAL completion of the 06:00
`daily_source_collection` job (intelligence/scheduler.py::_daily_collection_job)
via the heartbeat it already records for domain_key='intelligence_collection'
(migration 0071 domain_heartbeats) — rather than firing the brief on a blind
clock offset. This reuses an existing primitive; it does not introduce a new
orchestration mechanism, queue, or table.

Bounded degraded-cutoff policy: one missing/failed collection heartbeat must
never block the brief indefinitely. If today's collection heartbeat hasn't
landed by a configurable hard cutoff (default derived from
OR_INTEL_SCHEDULE_CRON's configured time, historically 06:30 AEST), brief
generation proceeds anyway and the brief records that its coverage is
degraded — see BriefGenerator, which asks this module for the current
status when it runs, and intelligence/scheduler.py, which polls this module
to decide WHEN to run.

Never raises and never blocks — a Supabase outage here must degrade the
brief (or the polling job simply retries later, up to its own cutoff), not
crash the caller.
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from intelligence.config import SCHEDULE_TZ

log = logging.getLogger(__name__)

COLLECTION_DOMAIN_KEY = "intelligence_collection"


def _parse_cutoff() -> tuple[int, int]:
    """Cutoff hour/minute derived from OR_INTEL_SCHEDULE_CRON (default
    "30 6 * * *" -> 06:30). Overridable directly via OR_INTEL_MORNING_CUTOFF
    ("HH:MM") without touching the cron string."""
    override = os.getenv("OR_INTEL_MORNING_CUTOFF", "").strip()
    if override:
        try:
            h, m = override.split(":")
            return int(h), int(m)
        except (ValueError, TypeError):
            log.warning("Invalid OR_INTEL_MORNING_CUTOFF=%r — falling back to SCHEDULE_CRON", override)

    try:
        from intelligence.config import SCHEDULE_CRON
        parts = SCHEDULE_CRON.split()
        return int(parts[1]), int(parts[0])
    except Exception:
        return 6, 30


MORNING_CUTOFF_HOUR, MORNING_CUTOFF_MINUTE = _parse_cutoff()

# The scheduler poll only needs to be "live" for a window around the
# expected collection + cutoff time — outside it there is nothing to check.
# Generous on both sides so a delayed collection run or a clock-skewed
# deploy still gets picked up.
_WINDOW_START_HOUR = 5
_WINDOW_END_HOUR = 9


def _resolve_tz():
    try:
        import pytz
        return pytz.timezone(SCHEDULE_TZ)
    except Exception:
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(SCHEDULE_TZ)
        except Exception:
            log.warning("Could not resolve timezone %s for morning_cycle — using host local time", SCHEDULE_TZ)
            return None


def local_now() -> datetime:
    tz = _resolve_tz()
    return datetime.now(tz) if tz is not None else datetime.now()


def cycle_id_for(moment: Optional[datetime] = None) -> str:
    """The AEST/local calendar date this morning's collection cycle belongs
    to, as 'YYYY-MM-DD'. Used as intelligence_briefs.morning_cycle_id."""
    moment = moment or local_now()
    return moment.date().isoformat()


def in_morning_window(moment: Optional[datetime] = None) -> bool:
    """Cheap upfront check so a poll job can no-op most of the day without
    making a network call."""
    moment = moment or local_now()
    return _WINDOW_START_HOUR <= moment.hour <= _WINDOW_END_HOUR


@dataclass
class MorningCycleStatus:
    cycle_id: str
    collection_status: str            # "ok" | "failed" | "unknown" | "pending"
    collection_checked_at: Optional[str]
    ready: bool                       # safe to generate now (heartbeat landed, or cutoff reached)
    cutoff_reached: bool
    degraded: bool                    # generating without full confirmation of a clean collection run
    reason: Optional[str]

    def to_dict(self) -> dict:
        return {
            "morning_cycle_id": self.cycle_id,
            "collection_status": self.collection_status,
            "collection_checked_at": self.collection_checked_at,
            "cutoff_reached": self.cutoff_reached,
            "degraded": self.degraded,
            "reason": self.reason,
        }


def get_status(moment: Optional[datetime] = None) -> MorningCycleStatus:
    moment = moment or local_now()
    cycle_id = cycle_id_for(moment)
    cutoff = moment.replace(hour=MORNING_CUTOFF_HOUR, minute=MORNING_CUTOFF_MINUTE, second=0, microsecond=0)
    cutoff_reached = moment >= cutoff
    day_start = moment.replace(hour=0, minute=0, second=0, microsecond=0)

    try:
        from core.platform.heartbeat import supabase_get
        path = (
            f"domain_heartbeats?domain_key=eq.{COLLECTION_DOMAIN_KEY}"
            f"&checked_at=gte.{urllib.parse.quote(day_start.isoformat())}"
            f"&order=checked_at.desc&limit=1"
        )
        rows = supabase_get(path)
    except Exception as exc:
        if cutoff_reached:
            return MorningCycleStatus(
                cycle_id=cycle_id, collection_status="unknown", collection_checked_at=None,
                ready=True, cutoff_reached=True, degraded=True,
                reason=f"Could not verify morning collection status ({exc}); proceeding at the bounded cutoff.",
            )
        return MorningCycleStatus(
            cycle_id=cycle_id, collection_status="pending", collection_checked_at=None,
            ready=False, cutoff_reached=False, degraded=False,
            reason=f"Collection status temporarily unavailable ({exc}); will retry before cutoff.",
        )

    if rows:
        row = rows[0]
        status = row.get("status", "unknown")
        return MorningCycleStatus(
            cycle_id=cycle_id, collection_status=status, collection_checked_at=row.get("checked_at"),
            ready=True, cutoff_reached=cutoff_reached, degraded=(status != "ok"),
            reason=None if status == "ok" else f"Morning collection heartbeat reported status '{status}'.",
        )

    if cutoff_reached:
        return MorningCycleStatus(
            cycle_id=cycle_id, collection_status="pending", collection_checked_at=None,
            ready=True, cutoff_reached=True, degraded=True,
            reason="Morning collection had not reported completion by the bounded cutoff; proceeding degraded.",
        )

    return MorningCycleStatus(
        cycle_id=cycle_id, collection_status="pending", collection_checked_at=None,
        ready=False, cutoff_reached=False, degraded=False, reason=None,
    )
