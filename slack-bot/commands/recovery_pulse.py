"""D-055 — /recovery-pulse command handler.

Opens a Block Kit modal for logging one of the four daily recovery pulses
(morning · midday · end_of_day · evening). Writes to the recovery_pulses
table in Supabase (UNIQUE on log_date + pulse_type → upsert).

Public API:
    MODAL_CALLBACK_ID              — view callback_id for app.py registration
    build_recovery_pulse_modal()   -> dict
    handle_recovery_pulse_submit(values, user_id, client)
    send_confidence_summary(user_id, client)  — standalone Slack DM
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))


def _make_supabase():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        return CommanderSupabaseClient()
    except Exception as exc:
        log.warning("[recovery-pulse] Supabase client unavailable: %s", exc)
        return None


# ── Constants ─────────────────────────────────────────────────────────────────

MODAL_CALLBACK_ID = "recovery_pulse_modal"

_PULSE_META = {
    "morning":    {"label": "Morning Readiness",  "purpose": "Mission planning · Daily posture determination",  "emoji": ":sunrise:"},
    "midday":     {"label": "Midday Status",       "purpose": "Course correction · Workload protection",         "emoji": ":sun_with_face:"},
    "end_of_day": {"label": "End of Workday",      "purpose": "Transition to recovery mode",                     "emoji": ":sunset:"},
    "evening":    {"label": "Evening Recovery",    "purpose": "Recovery completion loop",                        "emoji": ":night_with_stars:"},
}


def _suggested_pulse_type() -> str:
    hour = datetime.now(tz=timezone.utc).hour
    # Rough AU AEST offset (UTC+10/11) — hour is UTC so adjust
    # Use local time from the server if available, fallback to UTC heuristic
    try:
        local_hour = datetime.now().hour
    except Exception:
        local_hour = hour
    if local_hour < 11:
        return "morning"
    if local_hour < 14:
        return "midday"
    if local_hour < 18:
        return "end_of_day"
    return "evening"


# ── Modal builder ─────────────────────────────────────────────────────────────

def build_recovery_pulse_modal(pulse_type: str | None = None) -> dict:
    """Return Block Kit view dict for the recovery pulse modal."""
    today = date.today().isoformat()
    suggested = pulse_type or _suggested_pulse_type()
    meta = _PULSE_META[suggested]

    pulse_options = [
        {
            "text": {"type": "plain_text", "text": f"{m['emoji']} {m['label']}"},
            "value": pt,
        }
        for pt, m in _PULSE_META.items()
    ]

    blocks: list[dict] = [
        # Context
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{today}* — Recovery Pulse\n"
                    "Four pulses per day build a complete picture of recovery state.\n"
                    "Missed pulses reduce _readiness confidence_ — not recovery itself."
                ),
            },
        },
        {"type": "divider"},

        # Pulse type selector
        {
            "type": "input",
            "block_id": "pulse_type",
            "label": {"type": "plain_text", "text": "Pulse type"},
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
                "options": pulse_options,
            },
        },

        # Energy
        {
            "type": "input",
            "block_id": "energy",
            "label": {"type": "plain_text", "text": "Energy level"},
            "element": {
                "type": "static_select",
                "action_id": "value",
                "placeholder": {"type": "plain_text", "text": "Select…"},
                "options": [
                    {"text": {"type": "plain_text", "text": "Low"},      "value": "low"},
                    {"text": {"type": "plain_text", "text": "Moderate"}, "value": "moderate"},
                    {"text": {"type": "plain_text", "text": "High"},     "value": "high"},
                ],
            },
            "optional": True,
        },

        # Mood
        {
            "type": "input",
            "block_id": "mood",
            "label": {"type": "plain_text", "text": "Mood / nervous system"},
            "element": {
                "type": "static_select",
                "action_id": "value",
                "placeholder": {"type": "plain_text", "text": "Select…"},
                "options": [
                    {"text": {"type": "plain_text", "text": "Low"},      "value": "low"},
                    {"text": {"type": "plain_text", "text": "Stable"},   "value": "stable"},
                    {"text": {"type": "plain_text", "text": "Positive"}, "value": "positive"},
                ],
            },
            "optional": True,
        },

        # Stress
        {
            "type": "input",
            "block_id": "stress",
            "label": {"type": "plain_text", "text": "Stress / recovery debt"},
            "element": {
                "type": "static_select",
                "action_id": "value",
                "placeholder": {"type": "plain_text", "text": "Select…"},
                "options": [
                    {"text": {"type": "plain_text", "text": "Low"},      "value": "low"},
                    {"text": {"type": "plain_text", "text": "Moderate"}, "value": "moderate"},
                    {"text": {"type": "plain_text", "text": "High"},     "value": "high"},
                ],
            },
            "optional": True,
        },

        # Readiness
        {
            "type": "input",
            "block_id": "readiness",
            "label": {"type": "plain_text", "text": "Readiness / remaining capacity"},
            "element": {
                "type": "static_select",
                "action_id": "value",
                "placeholder": {"type": "plain_text", "text": "Select…"},
                "options": [
                    {"text": {"type": "plain_text", "text": "Low"},      "value": "low"},
                    {"text": {"type": "plain_text", "text": "Moderate"}, "value": "moderate"},
                    {"text": {"type": "plain_text", "text": "High"},     "value": "high"},
                ],
            },
            "optional": True,
        },

        # Body signals
        {
            "type": "input",
            "block_id": "pain_score",
            "label": {"type": "plain_text", "text": "Body signals (0 = none · 10 = severe)"},
            "hint": {
                "type": "plain_text",
                "text": "Context only — not a recovery metric.",
            },
            "element": {
                "type": "plain_text_input",
                "action_id": "value",
                "placeholder": {"type": "plain_text", "text": "0–10"},
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
                    "text": "Anything the Recovery Officer should know.",
                },
            },
            "optional": True,
        },
    ]

    return {
        "type": "modal",
        "callback_id": MODAL_CALLBACK_ID,
        "title": {"type": "plain_text", "text": "Recovery Pulse"},
        "submit": {"type": "plain_text", "text": "Log Pulse"},
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


def _float(val: str | None) -> float | None:
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


# ── Submission handler ────────────────────────────────────────────────────────

def handle_recovery_pulse_submit(values: dict, user_id: str, client: Any) -> None:
    """Write pulse to recovery_pulses and DM confirmation to user."""
    today = date.today().isoformat()

    pulse_type = _extract(values, "pulse_type") or _suggested_pulse_type()
    energy     = _extract(values, "energy")
    mood       = _extract(values, "mood")
    stress     = _extract(values, "stress")
    readiness  = _extract(values, "readiness")
    pain_score = _float(_extract(values, "pain_score"))
    notes      = _extract(values, "notes")

    payload: dict = {
        "log_date":   today,
        "pulse_type": pulse_type,
        "source":     "slack",
    }
    if energy:                    payload["energy"]          = energy
    if mood:                      payload["nervous_system"]  = mood
    if stress:                    payload["body_signals"]    = stress
    if readiness:                 payload["readiness"]       = readiness
    if pain_score is not None:    payload["pain_score"] = pain_score
    if notes:                     payload["notes"]      = notes

    db = _make_supabase()
    saved = False
    if db and db.is_enabled():
        try:
            db.raw_client.table("recovery_pulses").upsert(
                payload, on_conflict="log_date,pulse_type"
            ).execute()
            saved = True
            log.info("[recovery-pulse] Upserted %s pulse for %s", pulse_type, today)
        except Exception as exc:
            log.error("[recovery-pulse] Supabase upsert failed: %s", exc)
    else:
        log.warning("[recovery-pulse] Supabase unavailable — pulse not persisted")

    meta = _PULSE_META.get(pulse_type, _PULSE_META["morning"])
    status_icon = ":white_check_mark:" if saved else ":warning:"
    status_line = f"{status_icon} {meta['label']} logged." if saved else f"{status_icon} Received but could not save to database."

    lines = [status_line, "", f"*{today} — {meta['label']}*", ""]
    if energy:     lines.append(f"• *Energy:* {energy.capitalize()}")
    if mood:       lines.append(f"• *Mood:* {mood.capitalize()}")
    if stress:     lines.append(f"• *Stress:* {stress.capitalize()}")
    if readiness:  lines.append(f"• *Readiness:* {readiness.capitalize()}")
    if pain_score is not None:
        lines.append(f"• *Body signals:* {pain_score}/10")
    lines += ["", "_Missed pulses are information, not failure._"]

    # Append confidence summary if data is available
    try:
        confidence_text = _get_confidence_line(db, today)
        if confidence_text:
            lines += ["", confidence_text]
    except Exception:
        pass

    try:
        client.chat_postMessage(channel=user_id, text="\n".join(lines))
    except Exception as exc:
        log.error("[recovery-pulse] DM failed: %s", exc)


def _get_confidence_line(db: Any, today: str) -> str | None:
    """Fetch today's confidence summary for the DM footer."""
    if not db or not db.is_enabled():
        return None
    try:
        result = db.raw_client.table("recovery_confidence_today").select(
            "recovery_confidence,pulses_completed,pulses_missing,confidence_label"
        ).execute()
        if result.data:
            row = result.data[0]
            pct = row.get("recovery_confidence", 0)
            done = row.get("pulses_completed", 0)
            missing = row.get("pulses_missing", 4)
            bar_filled = int(pct / 10)
            bar = "█" * bar_filled + "░" * (10 - bar_filled)
            return f"*Recovery confidence today:* `{bar}` {pct}%  ({done}/4 pulses · {missing} remaining)"
    except Exception as exc:
        log.debug("[recovery-pulse] confidence fetch failed: %s", exc)
    return None


# ── Standalone confidence DM ──────────────────────────────────────────────────

def send_confidence_summary(user_id: str, client: Any) -> None:
    """DM today's recovery confidence snapshot. Called by /recovery-status."""
    db = _make_supabase()
    today = date.today().isoformat()
    confidence_text = _get_confidence_line(db, today) or "No recovery pulse data logged today."
    try:
        client.chat_postMessage(
            channel=user_id,
            text=f"*Recovery Confidence — {today}*\n\n{confidence_text}\n\nLog a pulse: `/recovery-pulse`",
        )
    except Exception as exc:
        log.error("[recovery-pulse] send_confidence_summary DM failed: %s", exc)
