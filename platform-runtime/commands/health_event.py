"""ROS-001 v1.1 — /health-event command handler.

Captures a significant health timeline event via a Block Kit modal and
writes to health_events in Supabase.

Public API:
    EVENT_MODAL_CALLBACK_ID      — view callback_id registered in app.py
    build_health_event_modal() -> dict
    handle_health_event_submit(values, user_id, client)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

# ── Supabase client ───────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from lib.tz import today_brisbane_iso


def _make_supabase():
    try:
        from tools.supabase.client import CommanderSupabaseClient
        return CommanderSupabaseClient()
    except Exception as exc:
        log.warning("[health-event] Supabase client unavailable: %s", exc)
        return None


# ── Modal ─────────────────────────────────────────────────────────────────────

EVENT_MODAL_CALLBACK_ID = "health_event_modal"

_EVENT_TYPES = [
    ("Appointment", "appointment"),
    ("Procedure", "procedure"),
    ("Surgery", "surgery"),
    ("Imaging ordered", "imaging_ordered"),
    ("Medication change", "medication_change"),
    ("Symptom onset", "symptom_onset"),
    ("Symptom change", "symptom_change"),
    ("Recovery milestone", "recovery_milestone"),
    ("Referral", "referral"),
    ("Pharmacy", "pharmacy"),
    ("Other", "other"),
]


def build_health_event_modal() -> dict:
    """Return the Block Kit view dict for the health event modal."""
    today = today_brisbane_iso()
    return {
        "type": "modal",
        "callback_id": EVENT_MODAL_CALLBACK_ID,
        "title": {"type": "plain_text", "text": "Log Health Event"},
        "submit": {"type": "plain_text", "text": "Log Event"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [

            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "Log a significant health event to the recovery timeline.\n"
                        "_No clinical documents are uploaded — this is a pointer only._"
                    ),
                },
            },
            {"type": "divider"},

            # ── Event date ────────────────────────────────────────────────────
            {
                "type": "input",
                "block_id": "event_date",
                "label": {"type": "plain_text", "text": "Event date"},
                "element": {
                    "type": "datepicker",
                    "action_id": "value",
                    "initial_date": today,
                    "placeholder": {"type": "plain_text", "text": "Select date"},
                },
            },

            # ── Event type ────────────────────────────────────────────────────
            {
                "type": "input",
                "block_id": "event_type",
                "label": {"type": "plain_text", "text": "Event type"},
                "element": {
                    "type": "static_select",
                    "action_id": "value",
                    "placeholder": {"type": "plain_text", "text": "Select…"},
                    "options": [
                        {"text": {"type": "plain_text", "text": label}, "value": value}
                        for label, value in _EVENT_TYPES
                    ],
                },
            },

            # ── Title ─────────────────────────────────────────────────────────
            {
                "type": "input",
                "block_id": "title",
                "label": {"type": "plain_text", "text": "Title"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "value",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "e.g. Spinal specialist review — Dr Smith",
                    },
                },
            },

            # ── Description ───────────────────────────────────────────────────
            {
                "type": "input",
                "block_id": "description",
                "label": {"type": "plain_text", "text": "Description (optional)"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "value",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "What happened. What was discussed. What was decided.",
                    },
                },
                "optional": True,
            },

            # ── Provider ──────────────────────────────────────────────────────
            {
                "type": "input",
                "block_id": "provider",
                "label": {"type": "plain_text", "text": "Provider / clinic (optional)"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "value",
                    "placeholder": {"type": "plain_text", "text": "e.g. St Andrew's Pain Clinic"},
                },
                "optional": True,
            },

            # ── Outcome ───────────────────────────────────────────────────────
            {
                "type": "input",
                "block_id": "outcome",
                "label": {"type": "plain_text", "text": "Outcome / result (optional)"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "value",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "What was the outcome or next step?",
                    },
                },
                "optional": True,
            },

            # ── Follow-up ─────────────────────────────────────────────────────
            {
                "type": "input",
                "block_id": "follow_up_required",
                "label": {"type": "plain_text", "text": "Follow-up required?"},
                "element": {
                    "type": "static_select",
                    "action_id": "value",
                    "initial_option": {
                        "text": {"type": "plain_text", "text": "No"},
                        "value": "no",
                    },
                    "options": [
                        {"text": {"type": "plain_text", "text": "Yes"}, "value": "yes"},
                        {"text": {"type": "plain_text", "text": "No"}, "value": "no"},
                    ],
                },
                "optional": True,
            },
            {
                "type": "input",
                "block_id": "follow_up_date",
                "label": {"type": "plain_text", "text": "Follow-up date (if required)"},
                "element": {
                    "type": "datepicker",
                    "action_id": "value",
                    "placeholder": {"type": "plain_text", "text": "Select date"},
                },
                "optional": True,
            },
        ],
    }


# ── Submission handler ────────────────────────────────────────────────────────

def _extract(values: dict, block_id: str) -> str | None:
    block = values.get(block_id, {})
    for action in block.values():
        v = action.get("selected_option") or action.get("selected_date") or action.get("value")
        if isinstance(v, dict):
            return v.get("value")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def handle_health_event_submit(values: dict, user_id: str, client) -> None:
    """Write health event to health_events and DM confirmation to user."""
    event_date        = _extract(values, "event_date") or today_brisbane_iso()
    event_type        = _extract(values, "event_type")
    title             = _extract(values, "title") or "(untitled)"
    description       = _extract(values, "description")
    provider          = _extract(values, "provider")
    outcome           = _extract(values, "outcome")
    follow_up_raw     = _extract(values, "follow_up_required")
    follow_up_required = follow_up_raw == "yes"
    follow_up_date    = _extract(values, "follow_up_date")

    payload: dict = {
        "event_date":        event_date,
        "event_type":        event_type or "other",
        "title":             title,
        "source":            "slack",
        "follow_up_required": follow_up_required,
    }
    if description:   payload["description"]   = description
    if provider:      payload["provider"]       = provider
    if outcome:       payload["outcome"]        = outcome
    if follow_up_date and follow_up_required:
        payload["follow_up_date"] = follow_up_date

    db = _make_supabase()
    saved = False
    if db and db.is_enabled():
        result = db.insert("health_events", payload)
        saved = result.ok
        if saved:
            log.info("[health-event] Inserted health_events: %s on %s", event_type, event_date)
        else:
            log.error("[health-event] Insert failed: %s", result.error)
    else:
        log.warning("[health-event] Supabase unavailable — event not persisted")

    status_line = ":white_check_mark: Event logged." if saved else ":warning: Event received but could not be saved to database."
    event_type_label = dict(_EVENT_TYPES).get(event_type or "", event_type or "—").lower()

    dm_text = (
        f"{status_line}\n\n"
        f"*Health Event — {event_date}*\n"
        f"• *Type:* {event_type_label.capitalize()}\n"
        f"• *Title:* {title}\n"
    )
    if provider:
        dm_text += f"• *Provider:* {provider}\n"
    if follow_up_required and follow_up_date:
        dm_text += f"• *Follow-up:* {follow_up_date}\n"

    try:
        client.chat_postMessage(channel=user_id, text=dm_text)
    except Exception as exc:
        log.error("[health-event] DM failed: %s", exc)
