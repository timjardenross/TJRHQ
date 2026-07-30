"""Timezone utilities — always use Brisbane (Australia/Brisbane = UTC+10, no DST)."""
from __future__ import annotations
from datetime import date, datetime

try:
    from zoneinfo import ZoneInfo
    _BRISBANE = ZoneInfo("Australia/Brisbane")
except Exception:
    from datetime import timezone, timedelta
    _BRISBANE = timezone(timedelta(hours=10))  # type: ignore[assignment]


def now_brisbane() -> datetime:
    return datetime.now(_BRISBANE)


def today_brisbane() -> date:
    return now_brisbane().date()


def today_brisbane_iso() -> str:
    return today_brisbane().isoformat()
