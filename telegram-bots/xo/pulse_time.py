"""
Shared recovery-pulse time bucketing — USS-TJR Human Systems.

Extracted from app.py's private `_current_pulse_type()` (EOS Phase 2
Priority 3) so voice_capture.py's automatic recovery-pulse promotion can
reuse the exact same morning/midday/evening cadence the real Telegram
button flow already uses, rather than a second, drifting copy of the
same split. One source of truth for "what pulse slot is this moment" -
app.py imports from here now instead of defining it locally.

Captain directive 2026-08-10: reduced from 4 pulses/day to 3. The
`end_of_day` bucket (16-20h) was dropped and folded into `midday`
(12-20h) rather than dropping morning or evening, for three independent
reasons:
  1. Domain reasoning: morning (start-of-day baseline) and evening
     (end-of-day reflection) are the two anchor checkpoints in
     established EMA/self-report practice - see the Part B proposal for
     sources. midday and end_of_day were always the most conceptually
     redundant pair (both mid/late-workday "how's capacity holding"
     checks), so one of that pair is the correct one to fold away.
  2. Live usage data (recovery_pulses, 2026-08-10 query): all-time pulse
     counts were morning=25, midday=17, end_of_day=14, evening=10.
     end_of_day was the second-least-used bucket, confirming it (not
     midday) is the redundant one to drop.
  3. Prior design intent already agreed: platform-runtime/recovery_scheduler.py
     (D-055, retired) fires Slack dispatch at exactly 3 windows -
     07:00, 12:30, 20:00 - with no separate end_of_day window, i.e. this
     3-way split was already the implicit target elsewhere in the
     codebase before Telegram's 4-way flow was reconciled to it.

recovery_pulses.pulse_type keeps 'end_of_day' as a legal DB value (other
surfaces - the LCARS Portal Medical Bay pulse page and the retired Slack
/recovery-pulse modal - still reference it and were out of this change's
authorized scope) but this canonical bucketing function, which the live
Telegram flow and voice-capture promotion both use, will never produce it
again.

Pure function, no I/O, no Supabase dependency - safe for either module to
import without risking a circular import (app.py already imports
voice_capture.py at call time; voice_capture.py must never import app.py).
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Australia/Brisbane")


def pulse_type_for_hour(hour: int) -> str:
    """Three-way split (Captain directive 2026-08-10, see module docstring):
    morning 5-12h, midday 12-20h (absorbs the retired end_of_day 16-20h
    slot), evening 20-5h."""
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 20:
        return "midday"
    return "evening"


def current_pulse_type() -> str:
    """Convenience wrapper matching app.py's original `_current_pulse_type()`
    signature - "now", in the same fixed Brisbane timezone every recovery
    pulse in this codebase is already logged against."""
    return pulse_type_for_hour(datetime.now(TZ).hour)
