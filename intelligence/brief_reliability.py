"""Morning-brief reliability helpers: misfire grace, missed-brief deadman, gap-aware lookback.

Background: no captains_daily_briefs row existed for 9-12 Sep 2026 (and 11 mornings were missed in 4 episodes since 15 Aug) while
collection ran on. The legacy morning brief only reads the last 24h, so a missed brief meant material events were never briefed.

Pure logic only (callers inject ``sb_request``/``notify``/clock) so it is testable offline. Nothing here runs unless the scheduler
or captains_brief calls it, and with no gap every function returns the pre-existing behaviour (24h lookback, no extra text).
"""
from __future__ import annotations

import logging
import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

# -- (1) Misfire grace ---------------------------------------------------------
# APScheduler's default misfire_grace_time is 1 second: a cron job whose run is even slightly late (executor busy, process stalled)
# is silently dropped. NOTE the scheduler uses the default in-memory jobstore, so a restart across the fire time is NOT recovered by
# grace (next fire is recomputed from "now", i.e. tomorrow); that case is covered by the deadman + gap-aware lookback below.
MORNING_GRACE_SECONDS = 3 * 3600   # a brief at <=10:00 is still useful; auto-deploy (every 5 min) can stall/restart around 07:00
WEEKLY_GRACE_SECONDS = 3 * 3600
MIDDAY_GRACE_SECONDS = 3600        # conditional update: stale after ~1h
EOD_GRACE_SECONDS = 3600
DEADMAN_GRACE_SECONDS = 3 * 3600
BRIEF_JOB_KWARGS = {"coalesce": True, "max_instances": 1}


def job_kwargs(grace_seconds: int) -> dict:
    return {**BRIEF_JOB_KWARGS, "misfire_grace_time": grace_seconds}


# -- (4) Gap-aware lookback ----------------------------------------------------
BASE_LOOKBACK_HOURS = 24
MAX_LOOKBACK_HOURS = 72
_NORMAL_CYCLE_SLACK_HOURS = 30   # last brief <=30h old is a normal daily cycle (DST, late send): keep exactly 24h


@dataclass(frozen=True)
class GapInfo:
    lookback_hours: int = BASE_LOOKBACK_HOURS
    last_generated_at: datetime | None = None
    last_brief_date: str | None = None
    gap_hours: float = 0.0
    capped: bool = False

    @property
    def missed(self) -> bool:
        return self.lookback_hours > BASE_LOOKBACK_HOURS


NO_GAP = GapInfo()


def _parse_ts(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def compute_gap(last_generated_at: datetime | None, now: datetime, last_brief_date: str | None = None) -> GapInfo:
    """Lookback from the last successful brief's generation time (+2h margin), capped at 72h; exactly 24h when the cycle was normal."""
    if last_generated_at is None:
        return NO_GAP
    gap_h = (now - last_generated_at).total_seconds() / 3600
    if gap_h <= _NORMAL_CYCLE_SLACK_HOURS:
        return GapInfo(BASE_LOOKBACK_HOURS, last_generated_at, last_brief_date, round(gap_h, 1))
    wanted = math.ceil(gap_h) + 2
    return GapInfo(min(MAX_LOOKBACK_HOURS, wanted), last_generated_at, last_brief_date, round(gap_h, 1), wanted > MAX_LOOKBACK_HOURS)


def get_gap(sb_request: Callable[[str, str], list], today_iso: str, now: datetime | None = None) -> GapInfo:
    """Look up the latest morning brief from a PREVIOUS brief_date. Never raises; any failure means NO_GAP (today's behaviour)."""
    now = now or datetime.now(timezone.utc)
    try:
        rows = sb_request("captains_daily_briefs",
                          f"brief_type=eq.morning&brief_date=lt.{today_iso}&order=generated_at.desc&limit=1&select=generated_at,brief_date")
        if not rows:
            return NO_GAP
        return compute_gap(_parse_ts(rows[0].get("generated_at")), now, rows[0].get("brief_date"))
    except Exception as exc:  # noqa: BLE001 - recovery aid must never block the brief; fall back to the unchanged 24h window
        log.warning("[brief-gap] could not determine previous brief: %s", exc)
        return NO_GAP


def coverage_note(gap: GapInfo, collection_caveat: str | None = None) -> list[str]:
    """Plain-text (pre-escape) coverage limitation lines; [] when nothing is degraded (keeps the default brief byte-identical)."""
    lines: list[str] = []
    if gap.missed:
        since = gap.last_brief_date or "the last brief"
        cap = f" (capped at {MAX_LOOKBACK_HOURS}h; older material may be missing)" if gap.capped else ""
        lines.append(f"⚠️ COVERAGE LIMITED: no morning brief was generated since {since} (about {gap.gap_hours:.0f}h ago). "
                     f"Signals below look back {gap.lookback_hours}h to cover the gap{cap}.")
    if collection_caveat:
        lines.append(f"⚠️ COVERAGE LIMITED: {collection_caveat}.")
    return lines


# -- (2) Missed-brief deadman --------------------------------------------------
_alerted: set[tuple[str, str]] = set()   # (brief_type, brief_date) already alerted by this process: no double fire


def _skip_dates() -> set[str]:
    """Deliberate no-brief days: BRIEF_DEADMAN_SKIP_DATES='2026-12-25,2026-12-26'."""
    return {d.strip() for d in os.environ.get("BRIEF_DEADMAN_SKIP_DATES", "").split(",") if d.strip()}


def check_missed_brief(sb_request: Callable[[str, str], list], notify: Callable[[str], bool], today_iso: str,
                       brief_type: str = "morning", alerted: set | None = None) -> str:
    """After the expected generation time: alert once if no captains_daily_briefs row of ``brief_type`` exists for ``today_iso``.

    Returns 'ok' | 'alerted' | 'already_alerted' | 'skipped' | 'unverified'. A query failure is 'unverified' (never alerts on a guess)."""
    alerted = _alerted if alerted is None else alerted
    key = (brief_type, today_iso)
    if today_iso in _skip_dates():
        return "skipped"
    if key in alerted:
        return "already_alerted"
    try:
        rows = sb_request("captains_daily_briefs", f"brief_type=eq.{brief_type}&brief_date=eq.{today_iso}&limit=1&select=brief_date")
    except Exception as exc:  # noqa: BLE001 - cannot verify; do not raise a false alarm, log for the journal
        log.warning("[brief-deadman] could not verify %s brief for %s: %s", brief_type, today_iso, exc)
        return "unverified"
    if rows:
        return "ok"
    alerted.add(key)
    delivered = notify(f"🚨 MISSED BRIEF: no {brief_type} brief exists for {today_iso}. Collection may still be running; the next brief "
                       f"will extend its lookback to cover the gap (up to {MAX_LOOKBACK_HOURS}h). Check intelligence-scheduler.")
    if not delivered:
        alerted.discard(key)   # alert itself failed: allow a retry rather than silence
        return "unverified"
    return "alerted"


def brief_date_aest(now: datetime | None = None) -> str:
    """Same fixed UTC+10 date that captains_brief._persist_brief stamps on brief_date."""
    now = now or datetime.now(timezone.utc)
    return now.astimezone(timezone(timedelta(hours=10))).date().isoformat()
