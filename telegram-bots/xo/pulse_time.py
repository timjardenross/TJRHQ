"""
Shared recovery-pulse time bucketing — USS-TJR Human Systems.

Extracted from app.py's private `_current_pulse_type()` (EOS Phase 2
Priority 3) so voice_capture.py's automatic recovery-pulse promotion can
reuse the exact same morning/midday/end_of_day/evening cadence the real
Telegram button flow already uses, rather than a second, drifting copy of
the same four-way split. One source of truth for "what pulse slot is this
moment" - app.py imports from here now instead of defining it locally.

Pure function, no I/O, no Supabase dependency - safe for either module to
import without risking a circular import (app.py already imports
voice_capture.py at call time; voice_capture.py must never import app.py).
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Australia/Brisbane")


def pulse_type_for_hour(hour: int) -> str:
    """Same four-way split app.py's Telegram button flow has always used
    (recovery_pulses migration 0020: morning/midday/end_of_day/evening)."""
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 16:
        return "midday"
    if 16 <= hour < 20:
        return "end_of_day"
    return "evening"


def current_pulse_type() -> str:
    """Convenience wrapper matching app.py's original `_current_pulse_type()`
    signature - "now", in the same fixed Brisbane timezone every recovery
    pulse in this codebase is already logged against."""
    return pulse_type_for_hour(datetime.now(TZ).hour)
