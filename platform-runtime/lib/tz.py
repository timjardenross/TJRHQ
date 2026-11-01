"""Timezone utilities — the platform's local time is Australia/Melbourne (DST-aware).

Changed from Brisbane (fixed UTC+10, no DST) on the owner's direction. "Today" and
wall-clock reminder times follow Melbourne, including daylight saving.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

log = logging.getLogger(__name__)

try:
    from zoneinfo import ZoneInfo
    _LOCAL = ZoneInfo("Australia/Melbourne")
except Exception as exc:  # noqa: BLE001 - best-effort tzdata fallback, fixed UTC+10 offset used
    # Only if tzdata/zoneinfo is unavailable. Approximation: ignores daylight saving.
    log.warning("[tz] ZoneInfo unavailable, falling back to fixed UTC+10 (no DST): %s", exc)
    from datetime import timedelta, timezone
    _LOCAL = timezone(timedelta(hours=10))  # type: ignore[assignment]


def now_local() -> datetime:
    return datetime.now(_LOCAL)


def today_local() -> date:
    return now_local().date()


def today_local_iso() -> str:
    return today_local().isoformat()
