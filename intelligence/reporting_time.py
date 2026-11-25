"""Melbourne reporting-date helpers (pure functions, no I/O).

A reporting date is the calendar date in Australia/Melbourne of an instant. Timestamps stay in UTC everywhere they are stored;
only the *attribution* (which day / ISO week a product or brief belongs to) is Melbourne. Naive datetimes are rejected so a
caller can never silently attribute a local-time value to the wrong day.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

MELBOURNE = ZoneInfo("Australia/Melbourne")


def _aware(ts: datetime) -> datetime:
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError("timezone-aware datetime required")
    return ts


def reporting_date(ts: datetime) -> date:
    """Melbourne calendar date of a tz-aware instant."""
    return _aware(ts).astimezone(MELBOURNE).date()


def iso_week_key(d: date) -> str:
    """ISO week of a date, e.g. 2026-W48."""
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


def to_melbourne(ts: datetime) -> datetime:
    return _aware(ts).astimezone(MELBOURNE)


def age_hours(as_of: datetime, now: datetime) -> float:
    """Elapsed hours between two tz-aware instants (never negative)."""
    return max(0.0, (_aware(now) - _aware(as_of)).total_seconds() / 3600.0)


def format_as_of(ts: datetime) -> str:
    """'25 Nov 06:22 AEDT' style label in Melbourne time (zone abbreviation shows daylight saving)."""
    m = to_melbourne(ts)
    return f"{m.day} {m.strftime('%b %H:%M')} {m.tzname()}"


def melbourne_period(now: datetime, days: int) -> tuple[datetime, datetime]:
    """(period_start, period_end) as Melbourne-zone datetimes for the same instants.

    Same instants as the UTC pair, so every comparison and duration is unchanged; only `.strftime('%Y-%m-%d')` (how the
    brief row stores the period) now yields the Melbourne date.
    """
    # Subtract in absolute time (UTC) and convert: zoneinfo arithmetic on local values is wall-clock and would shift by an
    # hour across a daylight-saving change.
    start = _aware(now) - timedelta(days=days)
    return to_melbourne(start), to_melbourne(now)


FLAG = "INTEL_PRODUCTS_APPEND_V1"   # one WP1 flag, default OFF, read at call time


def flag_enabled() -> bool:
    return os.environ.get(FLAG, "0").strip().lower() in ("1", "true", "yes", "on")


def period_datetime(ts: datetime) -> datetime:
    """The value stored as a brief's period_start / period_end: the same instant in Melbourne time when the flag is on
    (so strftime('%Y-%m-%d') is the Melbourne date), unchanged otherwise."""
    return to_melbourne(ts) if flag_enabled() else ts
