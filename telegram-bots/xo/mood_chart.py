"""XO Bot mood_chart — Telegram inline mood logging (1-10 scale)

Tap-based flow: mood score → sleep (optional) → sleep quality (optional) →
optional contextual fields. Each entry is independent; tapping the same
slot again updates that time-of-day's mood (upsert on log_date + time_of_day).

Similar pattern to inline pulse flow but simpler (single score vs. multi-dimensional
telemetry) and with optional contextual annotations (sleep, pain, anxiety, etc.).
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("Australia/Brisbane")
log = logging.getLogger(__name__)

# ── Time of day labels and selection ──────────────────────────────────────────

_TOD_LABELS = {
    "morning":   "🌅 Morning Mood",
    "afternoon": "🌤 Afternoon Mood",
    "evening":   "🌃 Evening Mood",
}

_MOOD_EMOJI = {
    1:  "😭",  # 1 = worst
    2:  "😞",
    3:  "😕",
    4:  "😐",
    5:  "🙂",
    6:  "😊",
    7:  "😄",
    8:  "😃",
    9:  "😍",
    10: "🤩",  # 10 = best
}


def _current_time_of_day() -> str:
    """Suggest a time of day based on current hour."""
    try:
        local_hour = datetime.now(_TZ).hour
    except Exception:
        local_hour = datetime.now().hour
    if local_hour < 14:
        return "morning"
    if local_hour < 18:
        return "afternoon"
    return "evening"


# ── Inline keyboard builders ──────────────────────────────────────────────────
# Callback data format: mc|tod=<time_of_day>|ms=<mood_score>|sh=<sleep_hours>|sq=<sleep_quality>

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def kb_time_of_day() -> InlineKeyboardMarkup:
    """Step 1: Select time of day."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🌅 Morning",   callback_data="mc|tod=morning"),
        InlineKeyboardButton("🌤 Afternoon", callback_data="mc|tod=afternoon"),
        InlineKeyboardButton("🌃 Evening",   callback_data="mc|tod=evening"),
    ]])


def kb_mood_score(tod: str) -> InlineKeyboardMarkup:
    """Step 2: Select mood score (1-10)."""
    # Present as 3 rows: 1-3, 4-6, 7-9, 10
    rows = [
        [
            InlineKeyboardButton(f"{_MOOD_EMOJI.get(i, '?')} {i}", callback_data=f"mc|tod={tod}|ms={i}")
            for i in range(1, 4)
        ],
        [
            InlineKeyboardButton(f"{_MOOD_EMOJI.get(i, '?')} {i}", callback_data=f"mc|tod={tod}|ms={i}")
            for i in range(4, 7)
        ],
        [
            InlineKeyboardButton(f"{_MOOD_EMOJI.get(i, '?')} {i}", callback_data=f"mc|tod={tod}|ms={i}")
            for i in range(7, 10)
        ],
        [InlineKeyboardButton(f"{_MOOD_EMOJI.get(10, '?')} 10", callback_data=f"mc|tod={tod}|ms=10")],
    ]
    return InlineKeyboardMarkup(rows)


def kb_confirm_or_add_context(tod: str, ms: int) -> InlineKeyboardMarkup:
    """Step 3: Confirm and save, or add optional context."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Save", callback_data=f"mc|tod={tod}|ms={ms}|done=1"),
        InlineKeyboardButton("➕ Add context", callback_data=f"mc|tod={tod}|ms={ms}|context=1"),
    ]])


# ── Parsing helpers ──────────────────────────────────────────────────────────

def parse_cb(data: str) -> dict:
    """Parse mood chart callback data."""
    result = {}
    for part in data.split("|")[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            result[k] = v
    return result


# ── Write to database ────────────────────────────────────────────────────────

async def write_mood_entry(
    db,
    time_of_day: str,
    mood_score: int,
    sleep_hours: float | None = None,
    sleep_quality: str | None = None,
    pain_level: int | None = None,
    anxiety_level: int | None = None,
    stress_level: int | None = None,
    alcohol_use: bool | None = None,
    substance_use: bool | None = None,
    notes: str | None = None,
) -> tuple[bool, str | None]:
    """Write mood chart entry. Returns (saved, error_msg)."""
    if not db:
        return False, "Supabase unavailable (check SUPABASE_KEY)"

    try:
        payload = {
            "log_date": datetime.now(_TZ).date().isoformat(),
            "time_of_day": time_of_day,
            "mood_score": mood_score,
            "source": "telegram",
        }
        if sleep_hours is not None:
            payload["sleep_hours"] = sleep_hours
        if sleep_quality:
            payload["sleep_quality"] = sleep_quality
        if pain_level is not None:
            payload["pain_level"] = pain_level
        if anxiety_level is not None:
            payload["anxiety_level"] = anxiety_level
        if stress_level is not None:
            payload["stress_level"] = stress_level
        if alcohol_use is not None:
            payload["alcohol_use"] = alcohol_use
        if substance_use is not None:
            payload["substance_use"] = substance_use
        if notes:
            payload["notes"] = notes

        res = db.table("mood_chart").upsert(
            payload,
            on_conflict="log_date,time_of_day",
        ).execute()

        log.info("Mood entry written: tod=%s mood=%d sleep=%s", time_of_day, mood_score, sleep_hours)

        # Record heartbeat
        try:
            from core.platform.heartbeat import record_heartbeat
            record_heartbeat("mood_chart", status="ok", detail=f"tod={time_of_day} mood={mood_score} source=telegram")
        except Exception:
            pass

        return True, None

    except Exception as exc:
        error_msg = str(exc)
        log.error("mood entry upsert failed: %s | tod=%s mood=%d", exc, time_of_day, mood_score)
        return False, error_msg


# ── Formatting helpers ───────────────────────────────────────────────────────

def format_mood_entry(tod: str, score: int, sleep_hours: float | None = None,
                      sleep_quality: str | None = None) -> str:
    """Format a mood entry for display."""
    tod_label = _TOD_LABELS.get(tod, tod)
    mood_emoji = _MOOD_EMOJI.get(score, "?")
    lines = [f"{mood_emoji} {tod_label}: {score}/10"]
    if sleep_hours is not None:
        lines.append(f"  • Sleep: {sleep_hours}h")
    if sleep_quality:
        lines.append(f"  • Quality: {sleep_quality.capitalize()}")
    return "\n".join(lines)
