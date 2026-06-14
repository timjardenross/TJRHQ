"""Health Check — /health-check Slack command.

Opens a guided modal for the Captain's daily health check-in.
On submission, writes one summary-level row to health_daily_logs (Supabase).

Privacy boundary (enforced here and in the DB schema):
  - NO diagnosis, medication names/doses, clinical notes, imaging, blood
    pressure, heart rate, or document content may reach Supabase.
  - Only the fields listed in ALLOWED_FIELDS may be sent.

Public API:
    MODAL_CALLBACK_ID          str
    build_health_check_modal() -> dict
    parse_modal_values(values) -> dict
    calculate_daily_status(payload) -> str   ("GREEN" | "AMBER" | "RED")
    handle_health_check_submit(values, user_id, client, respond) -> None
"""

from __future__ import annotations

import logging
import os
import sys
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

# Allow import from core/health/supabase_client when running from slack-bot/
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.health.supabase_client import supabase_upsert as _shared_upsert

log = logging.getLogger(__name__)

MODAL_CALLBACK_ID = "health_check_modal"

# ── Privacy boundary ──────────────────────────────────────────────────────────
# Exact set of columns that may be written to health_daily_logs.
# Any field not in this list is silently dropped before the DB call.
ALLOWED_FIELDS = frozenset({
    "log_date", "pain_score", "pain_location", "energy", "mood",
    "sleep_hours", "sleep_quality", "cpap_used", "cpap_hours",
    "movement_notes", "notes", "workload_constraint", "work_location",
    "sitting_tolerance_minutes", "source",
})

# ── Status calculation ────────────────────────────────────────────────────────

def calculate_daily_status(payload: dict) -> str:
    """Return 'GREEN', 'AMBER', or 'RED' based on summary health indicators.

    Scoring:
      pain ≥ 7          → +2 pts
      pain 4–6          → +1 pt
      energy = low      → +1 pt
      mood = low        → +1 pt
      sleep = poor      → +1 pt

    GREEN = 0 pts, AMBER = 1 pt, RED ≥ 2 pts
    """
    score = 0

    pain = payload.get("pain_score")
    if pain is not None:
        if pain >= 7:
            score += 2
        elif pain >= 4:
            score += 1

    if payload.get("energy") == "low":
        score += 1

    if payload.get("mood") == "low":
        score += 1

    if payload.get("sleep_quality") == "poor":
        score += 1

    if score == 0:
        return "GREEN"
    if score == 1:
        return "AMBER"
    return "RED"


# ── Modal definition ──────────────────────────────────────────────────────────

def build_health_check_modal() -> dict:
    """Return the Slack Block Kit view payload for the health check modal."""
    return {
        "type": "modal",
        "callback_id": MODAL_CALLBACK_ID,
        "title": {"type": "plain_text", "text": "Daily Health Check-in"},
        "submit": {"type": "plain_text", "text": "Log Check-in"},
        "close":  {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            # ── Pain ────────────────────────────────────────────────────────
            {
                "type": "section",
                "block_id": "pain_section",
                "text": {"type": "mrkdwn", "text": "*Pain*"},
            },
            {
                "type": "input",
                "block_id": "pain_score_block",
                "label": {"type": "plain_text", "text": "Pain score (0 = none, 10 = severe)"},
                "element": {
                    "type": "static_select",
                    "action_id": "pain_score",
                    "placeholder": {"type": "plain_text", "text": "Select…"},
                    "options": [
                        {"text": {"type": "plain_text", "text": str(i)}, "value": str(i)}
                        for i in range(11)
                    ],
                },
            },
            {
                "type": "input",
                "block_id": "pain_location_block",
                "label": {"type": "plain_text", "text": "Pain location"},
                "optional": True,
                "element": {
                    "type": "static_select",
                    "action_id": "pain_location",
                    "placeholder": {"type": "plain_text", "text": "Select…"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "None"},          "value": "none"},
                        {"text": {"type": "plain_text", "text": "Lower back"},    "value": "lower back"},
                        {"text": {"type": "plain_text", "text": "Upper back"},    "value": "upper back"},
                        {"text": {"type": "plain_text", "text": "Legs"},          "value": "legs"},
                        {"text": {"type": "plain_text", "text": "Neck"},          "value": "neck"},
                        {"text": {"type": "plain_text", "text": "Head"},          "value": "head"},
                        {"text": {"type": "plain_text", "text": "Multiple"},      "value": "multiple"},
                        {"text": {"type": "plain_text", "text": "Other"},         "value": "other"},
                    ],
                },
            },
            # ── Energy & mood ────────────────────────────────────────────────
            {
                "type": "section",
                "block_id": "energy_section",
                "text": {"type": "mrkdwn", "text": "*Energy & Mood*"},
            },
            {
                "type": "input",
                "block_id": "energy_block",
                "label": {"type": "plain_text", "text": "Energy level"},
                "element": {
                    "type": "static_select",
                    "action_id": "energy",
                    "placeholder": {"type": "plain_text", "text": "Select…"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "Low"},      "value": "low"},
                        {"text": {"type": "plain_text", "text": "Moderate"}, "value": "moderate"},
                        {"text": {"type": "plain_text", "text": "High"},     "value": "high"},
                    ],
                },
            },
            {
                "type": "input",
                "block_id": "mood_block",
                "label": {"type": "plain_text", "text": "Mood"},
                "element": {
                    "type": "static_select",
                    "action_id": "mood",
                    "placeholder": {"type": "plain_text", "text": "Select…"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "Low"},      "value": "low"},
                        {"text": {"type": "plain_text", "text": "Stable"},   "value": "stable"},
                        {"text": {"type": "plain_text", "text": "Positive"}, "value": "positive"},
                    ],
                },
            },
            # ── Sleep ────────────────────────────────────────────────────────
            {
                "type": "section",
                "block_id": "sleep_section",
                "text": {"type": "mrkdwn", "text": "*Sleep*"},
            },
            {
                "type": "input",
                "block_id": "sleep_hours_block",
                "label": {"type": "plain_text", "text": "Sleep hours"},
                "element": {
                    "type": "static_select",
                    "action_id": "sleep_hours",
                    "placeholder": {"type": "plain_text", "text": "Select…"},
                    "options": [
                        {"text": {"type": "plain_text", "text": f"{h}h"}, "value": str(h)}
                        for h in [3, 4, 5, 6, 7, 8, 9, 10]
                    ] + [
                        {"text": {"type": "plain_text", "text": "3h or less"}, "value": "2.5"},
                        {"text": {"type": "plain_text", "text": "10h+"},        "value": "10.5"},
                    ],
                },
            },
            {
                "type": "input",
                "block_id": "sleep_quality_block",
                "label": {"type": "plain_text", "text": "Sleep quality"},
                "element": {
                    "type": "static_select",
                    "action_id": "sleep_quality",
                    "placeholder": {"type": "plain_text", "text": "Select…"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "Poor"}, "value": "poor"},
                        {"text": {"type": "plain_text", "text": "Fair"}, "value": "fair"},
                        {"text": {"type": "plain_text", "text": "Good"}, "value": "good"},
                    ],
                },
            },
            {
                "type": "input",
                "block_id": "cpap_hours_block",
                "label": {"type": "plain_text", "text": "CPAP hours (0 if not used)"},
                "element": {
                    "type": "static_select",
                    "action_id": "cpap_hours",
                    "placeholder": {"type": "plain_text", "text": "Select…"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "0 (not used)"}, "value": "0"},
                    ] + [
                        {"text": {"type": "plain_text", "text": f"{h}h"}, "value": str(h)}
                        for h in [1, 2, 3, 4, 5, 6, 7, 8]
                    ],
                },
            },
            # ── Movement & work ──────────────────────────────────────────────
            {
                "type": "section",
                "block_id": "movement_section",
                "text": {"type": "mrkdwn", "text": "*Movement & Work*"},
            },
            {
                "type": "input",
                "block_id": "movement_block",
                "label": {"type": "plain_text", "text": "Movement today"},
                "element": {
                    "type": "static_select",
                    "action_id": "movement",
                    "placeholder": {"type": "plain_text", "text": "Select…"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "None"},     "value": "none"},
                        {"text": {"type": "plain_text", "text": "Light"},    "value": "light"},
                        {"text": {"type": "plain_text", "text": "Moderate"}, "value": "moderate"},
                    ],
                },
            },
            {
                "type": "input",
                "block_id": "work_location_block",
                "label": {"type": "plain_text", "text": "Work location"},
                "element": {
                    "type": "static_select",
                    "action_id": "work_location",
                    "placeholder": {"type": "plain_text", "text": "Select…"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "Home"},   "value": "home"},
                        {"text": {"type": "plain_text", "text": "Office"}, "value": "office"},
                        {"text": {"type": "plain_text", "text": "Travel"}, "value": "travel"},
                        {"text": {"type": "plain_text", "text": "Other"},  "value": "other"},
                    ],
                },
            },
            {
                "type": "input",
                "block_id": "sitting_tolerance_block",
                "label": {"type": "plain_text", "text": "Sitting tolerance (minutes)"},
                "element": {
                    "type": "static_select",
                    "action_id": "sitting_tolerance_minutes",
                    "placeholder": {"type": "plain_text", "text": "Select…"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "< 15 min"},  "value": "10"},
                        {"text": {"type": "plain_text", "text": "15 min"},    "value": "15"},
                        {"text": {"type": "plain_text", "text": "30 min"},    "value": "30"},
                        {"text": {"type": "plain_text", "text": "45 min"},    "value": "45"},
                        {"text": {"type": "plain_text", "text": "60 min"},    "value": "60"},
                        {"text": {"type": "plain_text", "text": "90 min"},    "value": "90"},
                        {"text": {"type": "plain_text", "text": "120+ min"},  "value": "120"},
                    ],
                },
            },
            # ── Notes ────────────────────────────────────────────────────────
            {
                "type": "input",
                "block_id": "notes_block",
                "label": {"type": "plain_text", "text": "Notes (optional, max 1000 chars)"},
                "optional": True,
                "element": {
                    "type": "plain_text_input",
                    "action_id": "notes",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "How are you feeling today? Any changes or context for planning?",
                    },
                    "max_length": 1000,
                },
            },
        ],
    }


# ── Modal value parser ────────────────────────────────────────────────────────

def parse_modal_values(values: dict) -> dict:
    """Extract submitted modal values into a flat dict ready for DB insert.

    Privacy rule: any key not in ALLOWED_FIELDS is silently discarded here.
    """
    def _select(block: str, action: str):
        try:
            return values[block][action]["selected_option"]["value"]
        except (KeyError, TypeError):
            return None

    def _text(block: str, action: str):
        try:
            return values[block][action]["value"]
        except (KeyError, TypeError):
            return None

    movement_val = _select("movement_block", "movement")

    raw = {
        "log_date":                 date.today().isoformat(),
        "pain_score":               _safe_int(_select("pain_score_block", "pain_score")),
        "pain_location":            _select("pain_location_block", "pain_location"),
        "energy":                   _select("energy_block", "energy"),
        "mood":                     _select("mood_block", "mood"),
        "sleep_hours":              _safe_float(_select("sleep_hours_block", "sleep_hours")),
        "sleep_quality":            _select("sleep_quality_block", "sleep_quality"),
        "cpap_hours":               _safe_float(_select("cpap_hours_block", "cpap_hours")),
        "cpap_used":                _safe_float(_select("cpap_hours_block", "cpap_hours") or "0") > 0,
        "movement_notes":           movement_val,
        "work_location":            _select("work_location_block", "work_location"),
        "sitting_tolerance_minutes": _safe_int(_select("sitting_tolerance_block", "sitting_tolerance_minutes")),
        "notes":                    _text("notes_block", "notes"),
        "source":                   "slack",
    }

    # Strip None values and enforce privacy boundary
    return {k: v for k, v in raw.items() if v is not None and k in ALLOWED_FIELDS}


def _safe_int(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _safe_float(val) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


# ── Supabase upsert ───────────────────────────────────────────────────────────

def _supabase_upsert_health_log(payload: dict) -> dict:
    """Upsert to health_daily_logs via shared Supabase client (WP-3)."""
    return _shared_upsert("health_daily_logs", payload, on_conflict="log_date")


# ── Confirmation message builder ──────────────────────────────────────────────

def _build_confirmation_message(payload: dict, status: str, saved_row: dict) -> list:
    """Build Slack Block Kit blocks for the post-submission confirmation DM."""
    status_emoji = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴"}.get(status, "⚪")
    log_date = payload.get("log_date", date.today().isoformat())
    pain = payload.get("pain_score", "—")
    energy = (payload.get("energy") or "—").capitalize()
    mood = (payload.get("mood") or "—").capitalize()
    sleep = payload.get("sleep_hours", "—")
    sleep_q = (payload.get("sleep_quality") or "—").capitalize()
    movement = (payload.get("movement_notes") or "—").capitalize()
    work_loc = (payload.get("work_location") or "—").capitalize()
    sitting = payload.get("sitting_tolerance_minutes", "—")
    cpap = payload.get("cpap_hours", 0)
    notes = payload.get("notes", "")

    summary_lines = [
        f"*Pain:* {pain}/10",
        f"*Energy:* {energy}   *Mood:* {mood}",
        f"*Sleep:* {sleep}h ({sleep_q})   *CPAP:* {cpap}h",
        f"*Movement:* {movement}   *Work:* {work_loc}",
        f"*Sitting tolerance:* {sitting} min",
    ]

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{status_emoji} Health Check-in Logged — {log_date}",
            },
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(summary_lines)},
        },
    ]

    if notes:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Notes:* {notes[:300]}"},
        })

    status_labels = {
        "GREEN": "All good — no constraints flagged.",
        "AMBER": "One indicator warrants attention. Pace where needed.",
        "RED":   "Multiple indicators flagged. Consider reduced workload today.",
    }
    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": f"Daily status: *{status}* — {status_labels.get(status, '')}"},
        ],
    })

    return blocks


# ── Main submit handler ───────────────────────────────────────────────────────

def handle_health_check_submit(
    values: dict,
    user_id: str,
    client: Any,
    *,
    respond=None,
) -> None:
    """Process modal submission: validate → upsert → send confirmation.

    Called from the app.view(MODAL_CALLBACK_ID) handler in app.py.
    Always sends feedback to the user; never raises.
    """
    try:
        payload = parse_modal_values(values)
        log.info("[health-check] Parsed payload fields: %s", list(payload.keys()))

        status = calculate_daily_status(payload)
        log.info("[health-check] Daily status: %s for user=%s", status, user_id)

        # Include calculated status as workload_constraint hint
        if "workload_constraint" not in payload:
            payload["workload_constraint"] = (
                "reduced"  if status == "RED"   else
                "normal"   if status == "GREEN" else
                "modified"  # AMBER → modified (preserves three-tier signal, WP-5)
            )

        saved_row = _supabase_upsert_health_log(payload)
        log.info("[health-check] Upserted row id=%s", saved_row.get("id"))

        blocks = _build_confirmation_message(payload, status, saved_row)

        client.chat_postMessage(
            channel=user_id,
            text=f"Health check-in logged — {status}",
            blocks=blocks,
        )

    except RuntimeError as exc:
        log.error("[health-check] Supabase write failed: %s", exc)
        _send_error_dm(client, user_id, str(exc))

    except TimeoutError as exc:
        log.error("[health-check] Supabase timeout: %s", exc)
        _send_error_dm(client, user_id, "Database write timed out — please try again in a moment.")

    except Exception as exc:
        log.error("[health-check] Unexpected error: %s — %s", type(exc).__name__, exc)
        _send_error_dm(client, user_id, f"{type(exc).__name__}: {exc}")


def _send_error_dm(client: Any, user_id: str, reason: str) -> None:
    """Send a visible failure message to the user as a DM."""
    try:
        client.chat_postMessage(
            channel=user_id,
            text="⚠️ Health check-in could not be saved.",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            "⚠️ *Health check-in could not be saved.*\n\n"
                            f"Reason: `{reason[:300]}`\n\n"
                            "Your data was not stored. Please try again or "
                            "contact the ship's engineer."
                        ),
                    },
                }
            ],
        )
    except Exception as dm_exc:
        log.error("[health-check] Could not send error DM: %s", dm_exc)
