"""Timezone utilities — always use Brisbane (Australia/Brisbane = UTC+10, no DST)."""
from __future__ import annotations

import logging
from datetime import date, datetime

log = logging.getLogger(__name__)

try:
    from zoneinfo import ZoneInfo
    _BRISBANE = ZoneInfo("Australia/Brisbane")
except Exception as exc:  # noqa: BLE001 - best-effort tzdata fallback, fixed UTC+10 offset used
    log.debug("[tz] ZoneInfo unavailable, falling back to fixed UTC+10: %s", exc)
    from datetime import timedelta, timezone
    _BRISBANE = timezone(timedelta(hours=10))  # type: ignore[assignment]


def now_brisbane() -> datetime:
    return datetime.now(_BRISBANE)


def today_brisbane() -> date:
    return now_brisbane().date()


def today_brisbane_iso() -> str:
    return today_brisbane().isoformat()
