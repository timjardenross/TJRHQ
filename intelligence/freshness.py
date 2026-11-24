"""One definition of "fresh" for the incident delivery path (alert tiers, alert dispatcher, morning brief).

Before this module the tier rules (12 h), the dispatcher (6 h) and the V1 brief (24 h "recent") each carried their own number, so the
brief could print "ACTIVE ALERT-LEVEL (live ...)" for an incident the dispatcher would never alert. Everything now reads these values.

  ALERT_FRESH_HOURS   a factual report this recent (with a verified publication time) is needed for an interrupt. Override with
                      INCIDENT_ALERT_FRESH_HOURS (read at call time, as the dispatcher always did).
  BRIEF_FRESH_HOURS   the morning brief's "recent" window: what counts as current for a scheduled brief item.
  LIVE_BRIEF_HOURS    an incident still ongoing / partially restored stays a current brief item this long after its newest factual
                      report. Anything else older than BRIEF_FRESH_HOURS is context, never a current incident.

Pure and flag-free.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

ALERT_FRESH_HOURS = 6.0
ALERT_FRESH_ENV = "INCIDENT_ALERT_FRESH_HOURS"
BRIEF_FRESH_HOURS = 24
LIVE_BRIEF_HOURS = 72


def alert_window() -> timedelta:
    try:
        return timedelta(hours=float(os.getenv(ALERT_FRESH_ENV, "") or ALERT_FRESH_HOURS))
    except ValueError:
        return timedelta(hours=ALERT_FRESH_HOURS)


def brief_window() -> timedelta:
    return timedelta(hours=BRIEF_FRESH_HOURS)


def live_window() -> timedelta:
    return timedelta(hours=LIVE_BRIEF_HOURS)


def within(published: datetime | None, now: datetime | None, window: timedelta) -> bool:
    """True when ``published`` lies in [now - window, now]. No publication time is never fresh; no ``now`` means 'not asked'."""
    if published is None:
        return False
    if now is None:
        return True
    return timedelta(0) <= now - published <= window


def alert_fresh(published: datetime | None, now: datetime | None) -> bool:
    return within(published, now, alert_window())


def brief_fresh(published: datetime | None, now: datetime | None) -> bool:
    return within(published, now, brief_window())
