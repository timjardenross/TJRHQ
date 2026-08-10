"""D-056 — /mood-chart command handler.

Simple daily mood tracking (1-10 scale) at key times of day with optional
contextual notes about sleep, pain, anxiety, substance use, etc.
Writes to the mood_chart table in Supabase (UNIQUE on log_date + time_of_day → upsert).

Similar pattern to recovery_pulse but with simplified (mood score only) flow
plus contextual annotation support.

Public API:
    MODAL_CALLBACK_ID              — view callback_id for app.py registration
    build_mood_chart_modal()       -> dict
    handle_mood_chart_submit(values, user_id, client)
    send_mood_summary(user_id, client)  — standalone Slack DM
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from lib.tz import today_brisbane_iso


def _make_supabase():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        return CommanderSupabaseClient()
    except Exception as exc:
        log.warning("[mood-chart] Supabase client unavailable: %s", exc)
        return None


# ── Constants ─────────────────────────────────────────────────────────────────

MODAL_CALLBACK_ID = "mood_chart_modal"

_TIME_OF_DAY_META = {
    "morning":   {"label": "Morning Mood",    "emoji": ":sunrise:", "purpose": "Start of day assessment"},
    "afternoon": {"label": "Afternoon Mood",  "emoji": ":sun_with_face:", "purpose": "Midday check-in"},
    "evening":   {"label": "Evening Mood",    "emoji": ":night_with_stars:", "purpose": "End of day reflection"},
}


def _suggested_time_of_day() -> str:
    """Suggest a time of day based on current hour."""
    try:
        local_hour = datetime.now().hour
    except Exception:
        local_hour = datetime.now(tz=timezone.utc).hour
    if local_hour < 14:
        return "morning"
    if local_hour < 18:
        return "afternoon"
    return "evening"


# ── Modal builder ─────────────────────────────────────────────────────────────

def build_mood_chart_modal(time_of_day: str | None = None) -> dict:
    """Return Block Kit view dict for the mood chart modal."""
    today = today_brisbane_iso()
    suggested = time_of_day or _suggested_time_of_day()
    meta = _TIME_OF_DAY_META[suggested]

    time_options = [
        {
            "text": {"type": "plain_text", "text": f"{m['emoji']} {m['label']}"},
            "value": tod,
        }
        for tod, m in _TIME_OF_DAY_META.items()
    ]

    mood_options = [
        {
            "text": {"type": "plain_text", "text": str(i)},
            "value": str(i),
        }
        for i in range(1, 11)
    ]

    blocks: list[dict] = [
        # Context
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{today}* — Mood Chart\n"
                    "Rate your mood from 1 (worst) to 10 (best) at different times of day.\n"
                    "Add context about sleep, pain, anxiety, substance use, or anything else that matters."
                ),
            },
        },
        {"type": "divider"},

        # Time of day selector
        {
            "type": "input",
            "block_id": "time_of_day",
            "label": {"type": "plain_text", "text": "Time of day"},
            "hint": {
                "type": "plain_text",
                "text": f"Suggested for now: {meta['label']} — {meta['purpose']}",
            },
            "element": {
                "type": "static_select",
                "action_id": "value",
                "initial_option": {
                    "text": {"type": "plain_text", "text": f"{meta['emoji']} {meta['label']}"},
                    "value": suggested,
                },
                "options": time_options,
            },
        },

        # Mood score (1-10)
        {
            "type": "input",
            "block_id": "mood_score",
            "label": {"type": "plain_text", "text": "Mood score (1 = worst · 10 = best)"},
            "element": {
                "type": "static_select",
                "action_id": "value",
                "placeholder": {"type": "plain_text", "text": "Select…"},
                "options": mood_options,
            },
            "optional": False,
        },

        # Sleep
        {
            "type": "input",
            "block_id": "sleep_hours",
            "label": {"type": "plain_text", "text": "Sleep last night (hours)"},
            "element": {
                "type": "plain_text_input",
                "action_id": "value",
                "placeholder": {"type": "plain_text", "text": "e.g., 7.5"},
            },
            "optional": True,
        },

        # Sleep quality
        {
            "type": "input",
            "block_id": "sleep_quality",
            "label": {"type": "plain_text", "text": "Sleep quality"},
            "element": {
                "type": "static_select",
                "action_id": "value",
                "placeholder": {"type": "plain_text", "text": "Select…"},
                "options": [
                    {"text": {"type": "plain_text", "text": "Poor"},      "value": "poor"},
                    {"text": {"type": "plain_text", "text": "Fair"},      "value": "fair"},
                    {"text": {"type": "plain_text", "text": "Good"},      "value": "good"},
                    {"text": {"type": "plain_text", "text": "Excellent"}, "value": "excellent"},
                ],
            },
            "optional": True,
        },

        # Pain level
        {
            "type": "input",
            "block_id": "pain_level",
            "label": {"type": "plain_text", "text": "Pain level (0 = none · 10 = severe)"},
            "element": {
                "type": "plain_text_input",
                "action_id": "value",
                "placeholder": {"type": "plain_text", "text": "0–10"},
            },
            "optional": True,
        },

        # Anxiety level
        {
            "type": "input",
            "block_id": "anxiety_level",
            "label": {"type": "plain_text", "text": "Anxiety level (0 = calm · 10 = severe)"},
            "element": {
                "type": "plain_text_input",
                "action_id": "value",
                "placeholder": {"type": "plain_text", "text": "0–10"},
            },
            "optional": True,
        },

        # Stress level
        {
            "type": "input",
            "block_id": "stress_level",
            "label": {"type": "plain_text", "text": "Stress level (0 = relaxed · 10 = maximum)"},
            "element": {
                "type": "plain_text_input",
                "action_id": "value",
                "placeholder": {"type": "plain_text", "text": "0–10"},
            },
            "optional": True,
        },

        # Alcohol use
        {
            "type": "input",
            "block_id": "alcohol_use",
            "label": {"type": "plain_text", "text": "Alcohol use"},
            "element": {
                "type": "static_select",
                "action_id": "value",
                "placeholder": {"type": "plain_text", "text": "Select…"},
                "options": [
                    {"text": {"type": "plain_text", "text": "None"},     "value": "false"},
                    {"text": {"type": "plain_text", "text": "Consumed"}, "value": "true"},
                ],
            },
            "optional": True,
        },

        # Substance use
        {
            "type": "input",
            "block_id": "substance_use",
            "label": {"type": "plain_text", "text": "Other substance use"},
            "element": {
                "type": "static_select",
                "action_id": "value",
                "placeholder": {"type": "plain_text", "text": "Select…"},
                "options": [
                    {"text": {"type": "plain_text", "text": "None"},     "value": "false"},
                    {"text": {"type": "plain_text", "text": "Consumed"}, "value": "true"},
                ],
            },
            "optional": True,
        },

        # Notes
        {
            "type": "input",
            "block_id": "notes",
            "label": {"type": "plain_text", "text": "Notes (optional)"},
            "element": {
                "type": "plain_text_input",
                "action_id": "value",
                "multiline": True,
                "placeholder": {
                    "type": "plain_text",
                    "text": "Anything relevant to your mood or context.",
                },
            },
            "optional": True,
        },
    ]

    return {
        "type": "modal",
        "callback_id": MODAL_CALLBACK_ID,
        "title": {"type": "plain_text", "text": "Mood Chart"},
        "submit": {"type": "plain_text", "text": "Log Mood"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": blocks,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract(values: dict, block_id: str) -> str | None:
    block = values.get(block_id, {})
    for action in block.values():
        v = action.get("selected_option") or action.get("value")
        if isinstance(v, dict):
            return v.get("value")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _int(val: str | None) -> int | None:
    try:
        return int(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _float(val: str | None) -> float | None:
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _bool(val: str | None) -> bool | None:
    if val is None:
        return None
    if val.lower() in ("true", "1", "yes"):
        return True
    if val.lower() in ("false", "0", "no"):
        return False
    return None


# ── Submission handler ────────────────────────────────────────────────────────

def handle_mood_chart_submit(values: dict, user_id: str, client: Any) -> None:
    """Write mood chart entry to Supabase and DM confirmation to user."""
    today = today_brisbane_iso()

    time_of_day = _extract(values, "time_of_day") or _suggested_time_of_day()
    mood_score = _int(_extract(values, "mood_score"))
    sleep_hours = _float(_extract(values, "sleep_hours"))
    sleep_quality = _extract(values, "sleep_quality")
    pain_level = _int(_extract(values, "pain_level"))
    anxiety_level = _int(_extract(values, "anxiety_level"))
    stress_level = _int(_extract(values, "stress_level"))
    alcohol_use = _bool(_extract(values, "alcohol_use"))
    substance_use = _bool(_extract(values, "substance_use"))
    notes = _extract(values, "notes")

    if mood_score is None:
        try:
            client.chat_postMessage(
                channel=user_id,
                text=":warning: Mood score is required. Please log your mood again."
            )
        except Exception:
            pass
        log.error("[mood-chart] Missing mood_score")
        return

    payload: dict = {
        "log_date": today,
        "time_of_day": time_of_day,
        "mood_score": mood_score,
        "source": "slack",
    }
    if sleep_hours is not None:     payload["sleep_hours"] = sleep_hours
    if sleep_quality:               payload["sleep_quality"] = sleep_quality
    if pain_level is not None:      payload["pain_level"] = pain_level
    if anxiety_level is not None:   payload["anxiety_level"] = anxiety_level
    if stress_level is not None:    payload["stress_level"] = stress_level
    if alcohol_use is not None:     payload["alcohol_use"] = alcohol_use
    if substance_use is not None:   payload["substance_use"] = substance_use
    if notes:                       payload["notes"] = notes

    db = _make_supabase()
    saved = False
    if db and db.is_enabled():
        try:
            db.raw_client.table("mood_chart").upsert(
                payload, on_conflict="log_date,time_of_day"
            ).execute()
            saved = True
            log.info("[mood-chart] Upserted %s mood for %s (score=%d)", time_of_day, today, mood_score)
        except Exception as exc:
            log.error("[mood-chart] Supabase upsert failed: %s", exc)
    else:
        log.warning("[mood-chart] Supabase unavailable — mood not persisted")

    meta = _TIME_OF_DAY_META.get(time_of_day, _TIME_OF_DAY_META["morning"])
    status_icon = ":white_check_mark:" if saved else ":warning:"
    status_line = f"{status_icon} {meta['label']} logged." if saved else f"{status_icon} Received but could not save to database."

    mood_emoji = _mood_emoji(mood_score)
    lines = [status_line, "", f"*{today} — {meta['label']}*", ""]
    lines.append(f"• *Mood:* {mood_emoji} {mood_score}/10")
    if sleep_hours is not None:
        lines.append(f"• *Sleep:* {sleep_hours}h")
    if sleep_quality:
        lines.append(f"• *Sleep quality:* {sleep_quality.capitalize()}")
    if pain_level is not None:
        lines.append(f"• *Pain:* {pain_level}/10")
    if anxiety_level is not None:
        lines.append(f"• *Anxiety:* {anxiety_level}/10")
    if stress_level is not None:
        lines.append(f"• *Stress:* {stress_level}/10")
    if alcohol_use:
        lines.append("• *Alcohol use:* Yes")
    if substance_use:
        lines.append("• *Substance use:* Yes")
    if notes:
        lines.append(f"\n_Notes:_ {notes}")

    # Append mood summary if data is available
    try:
        summary_text = _get_mood_summary(db, today)
        if summary_text:
            lines += ["", summary_text]
    except Exception:
        pass

    try:
        client.chat_postMessage(channel=user_id, text="\n".join(lines))
    except Exception as exc:
        log.error("[mood-chart] DM failed: %s", exc)


def _mood_emoji(score: int) -> str:
    """Return emoji representation of mood score."""
    if score <= 2:
        return ":frowning_face:"
    if score <= 4:
        return ":disappointed_face:"
    if score <= 6:
        return ":neutral_face:"
    if score <= 8:
        return ":smiley:"
    return ":grinning_face:"


def _get_mood_summary(db: Any, today: str) -> str | None:
    """Fetch today's mood summary for the DM footer."""
    if not db or not db.is_enabled():
        return None
    try:
        result = db.raw_client.table("mood_chart_today").select(
            "entries_today,avg_mood_score,low_mood_score,high_mood_score,morning_score,afternoon_score,evening_score"
        ).execute()
        if result.data:
            row = result.data[0]
            entries = row.get("entries_today", 0)
            avg = row.get("avg_mood_score", 0)
            low = row.get("low_mood_score", 0)
            high = row.get("high_mood_score", 0)
            morning = row.get("morning_score")
            afternoon = row.get("afternoon_score")
            evening = row.get("evening_score")

            scores_line = "Scores: "
            if morning:
                scores_line += f"Morning {morning} "
            if afternoon:
                scores_line += f"· Afternoon {afternoon} "
            if evening:
                scores_line += f"· Evening {evening}"
            scores_line = scores_line.rstrip()

            return f"*Today's mood:* {_mood_emoji(int(avg))} avg={avg}/10 · range {low}–{high}\n{scores_line}"
    except Exception as exc:
        log.debug("[mood-chart] summary fetch failed: %s", exc)
    return None


# ── Standalone mood summary DM ───────────────────────────────────────────────

def send_mood_summary(user_id: str, client: Any) -> None:
    """DM today's mood summary snapshot. Called by a mood-status command."""
    db = _make_supabase()
    today = today_brisbane_iso()
    summary_text = _get_mood_summary(db, today) or "No mood entries logged today."
    try:
        client.chat_postMessage(
            channel=user_id,
            text=f"*Mood Summary — {today}*\n\n{summary_text}\n\nLog your mood: `/mood-chart`",
        )
    except Exception as exc:
        log.error("[mood-chart] send_mood_summary DM failed: %s", exc)
