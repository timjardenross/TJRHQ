"""Health Event — /health-event Slack command.

Opens a guided modal for recording a significant health timeline event
(appointment, procedure, imaging ordered, medication change summary, etc.).

Writes to health_events (Supabase). local_document_path stores a path
pointer only — no file content ever reaches Supabase.

Privacy boundary:
  - event_type enum excludes 'diagnosis' — diagnoses are not stored
  - local_document_path is a short text path, not file content
  - description/outcome are capped at 2000/1000 chars
  - No medication names, clinical notes verbatim, or imaging results

Public API:
    EVENT_MODAL_CALLBACK_ID          str
    build_health_event_modal()       -> dict
    parse_event_modal_values(values) -> dict
    handle_health_event_submit(values, user_id, client) -> None
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any

# Allow import from core/health/supabase_client when running from slack-bot/
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.health.supabase_client import supabase_insert as _shared_insert

log = logging.getLogger(__name__)

EVENT_MODAL_CALLBACK_ID = "health_event_modal"

# ── Privacy boundary ──────────────────────────────────────────────────────────
ALLOWED_EVENT_FIELDS = frozenset({
    "event_date", "event_type", "title", "description",
    "provider", "outcome", "follow_up_required", "follow_up_date",
    "follow_up_notes", "local_document_path", "source",
})

EVENT_TYPE_LABELS = {
    "appointment":       "Appointment",
    "procedure":         "Procedure",
    "surgery":           "Surgery",
    "imaging_ordered":   "Imaging ordered",
    "medication_change": "Medication change (summary only)",
    "symptom_onset":     "Symptom onset",
    "symptom_change":    "Symptom change",
    "recovery_milestone":"Recovery milestone",
    "referral":          "Referral",
    "pharmacy":          "Pharmacy",
    "other":             "Other",
}


# ── Modal definition ──────────────────────────────────────────────────────────

def build_health_event_modal(prefill_date: str | None = None) -> dict:
    """Return the Slack Block Kit view payload for the health event modal."""
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    # Build a set of recent date options (last 14 days + today)
    date_options = []
    for days_ago in range(0, 15):
        d = (date.today() - timedelta(days=days_ago)).isoformat()
        label = "Today" if days_ago == 0 else ("Yesterday" if days_ago == 1 else d)
        date_options.append({"text": {"type": "plain_text", "text": label}, "value": d})
    date_options.append({"text": {"type": "plain_text", "text": "Earlier (enter in notes)"}, "value": "earlier"})

    event_type_options = [
        {"text": {"type": "plain_text", "text": label}, "value": key}
        for key, label in EVENT_TYPE_LABELS.items()
    ]

    return {
        "type": "modal",
        "callback_id": EVENT_MODAL_CALLBACK_ID,
        "title": {"type": "plain_text", "text": "Log Health Event"},
        "submit": {"type": "plain_text", "text": "Log Event"},
        "close":  {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            # ── Event basics ─────────────────────────────────────────────────
            {
                "type": "input",
                "block_id": "event_date_block",
                "label": {"type": "plain_text", "text": "Event date"},
                "element": {
                    "type": "static_select",
                    "action_id": "event_date",
                    "placeholder": {"type": "plain_text", "text": "Select…"},
                    "options": date_options,
                    "initial_option": date_options[0],  # today
                },
            },
            {
                "type": "input",
                "block_id": "event_type_block",
                "label": {"type": "plain_text", "text": "Event type"},
                "element": {
                    "type": "static_select",
                    "action_id": "event_type",
                    "placeholder": {"type": "plain_text", "text": "Select…"},
                    "options": event_type_options,
                },
            },
            {
                "type": "input",
                "block_id": "title_block",
                "label": {"type": "plain_text", "text": "Title"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "title",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "e.g. Spine specialist review",
                    },
                    "max_length": 200,
                },
            },
            # ── Details ──────────────────────────────────────────────────────
            {
                "type": "input",
                "block_id": "description_block",
                "label": {"type": "plain_text", "text": "Description (optional, max 2000 chars)"},
                "optional": True,
                "element": {
                    "type": "plain_text_input",
                    "action_id": "description",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Summary of what happened — no clinical notes verbatim",
                    },
                    "max_length": 2000,
                },
            },
            {
                "type": "input",
                "block_id": "provider_block",
                "label": {"type": "plain_text", "text": "Provider / location (optional)"},
                "optional": True,
                "element": {
                    "type": "plain_text_input",
                    "action_id": "provider",
                    "placeholder": {"type": "plain_text", "text": "e.g. Spine Specialist, GP, Physio"},
                    "max_length": 100,
                },
            },
            {
                "type": "input",
                "block_id": "outcome_block",
                "label": {"type": "plain_text", "text": "Outcome / plan (optional, max 1000 chars)"},
                "optional": True,
                "element": {
                    "type": "plain_text_input",
                    "action_id": "outcome",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "e.g. Continue current plan, follow-up MRI ordered",
                    },
                    "max_length": 1000,
                },
            },
            # ── Follow-up ────────────────────────────────────────────────────
            {
                "type": "input",
                "block_id": "follow_up_block",
                "label": {"type": "plain_text", "text": "Follow-up required?"},
                "element": {
                    "type": "static_select",
                    "action_id": "follow_up_required",
                    "placeholder": {"type": "plain_text", "text": "Select…"},
                    "options": [
                        {"text": {"type": "plain_text", "text": "No"}, "value": "false"},
                        {"text": {"type": "plain_text", "text": "Yes"}, "value": "true"},
                    ],
                    "initial_option": {"text": {"type": "plain_text", "text": "No"}, "value": "false"},
                },
            },
            {
                "type": "input",
                "block_id": "follow_up_date_block",
                "label": {"type": "plain_text", "text": "Follow-up date (optional)"},
                "optional": True,
                "element": {
                    "type": "datepicker",
                    "action_id": "follow_up_date",
                    "placeholder": {"type": "plain_text", "text": "Select date…"},
                },
            },
            {
                "type": "input",
                "block_id": "follow_up_notes_block",
                "label": {"type": "plain_text", "text": "Follow-up notes (optional)"},
                "optional": True,
                "element": {
                    "type": "plain_text_input",
                    "action_id": "follow_up_notes",
                    "placeholder": {"type": "plain_text", "text": "What needs to happen next?"},
                    "max_length": 500,
                },
            },
            # ── Local document ───────────────────────────────────────────────
            {
                "type": "section",
                "block_id": "doc_note_section",
                "text": {
                    "type": "mrkdwn",
                    "text": "📁 *Local document* — enter the file path if you have a related document stored locally. _Path reference only — no content is uploaded to Supabase._",
                },
            },
            {
                "type": "input",
                "block_id": "local_doc_block",
                "label": {"type": "plain_text", "text": "Local document path (optional)"},
                "optional": True,
                "element": {
                    "type": "plain_text_input",
                    "action_id": "local_document_path",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "memory/health/documents/2026-06-12-spine-review.pdf",
                    },
                    "max_length": 300,
                },
            },
        ],
    }


# ── Modal value parser ────────────────────────────────────────────────────────

def parse_event_modal_values(values: dict) -> dict:
    """Extract submitted modal values into a flat dict for DB insert.

    Enforces privacy boundary: only ALLOWED_EVENT_FIELDS pass through.
    """
    def _select(block: str, action: str):
        try:
            return values[block][action]["selected_option"]["value"]
        except (KeyError, TypeError):
            return None

    def _text(block: str, action: str):
        try:
            v = values[block][action]["value"]
            return v.strip() if v else None
        except (KeyError, TypeError):
            return None

    def _date(block: str, action: str):
        """Extract date from a Slack datepicker element (returns YYYY-MM-DD string)."""
        try:
            return values[block][action]["selected_date"]
        except (KeyError, TypeError):
            return None

    follow_up_val = _select("follow_up_block", "follow_up_required")
    follow_up_bool = follow_up_val == "true"

    event_date_val = _select("event_date_block", "event_date")
    # "earlier" is a sentinel — caller puts date in description
    if event_date_val == "earlier":
        event_date_val = date.today().isoformat()  # default to today, note in description

    raw = {
        "event_date":          event_date_val or date.today().isoformat(),
        "event_type":          _select("event_type_block", "event_type"),
        "title":               _text("title_block", "title"),
        "description":         _text("description_block", "description"),
        "provider":            _text("provider_block", "provider"),
        "outcome":             _text("outcome_block", "outcome"),
        "follow_up_required":  follow_up_bool,
        "follow_up_date":      _date("follow_up_date_block", "follow_up_date"),
        "follow_up_notes":     _text("follow_up_notes_block", "follow_up_notes"),
        "local_document_path": _text("local_doc_block", "local_document_path"),
        "source":              "slack",
    }

    # Strip None values; enforce privacy boundary
    return {k: v for k, v in raw.items() if v is not None and k in ALLOWED_EVENT_FIELDS}


# ── Supabase insert ───────────────────────────────────────────────────────────

def _supabase_insert_health_event(payload: dict) -> dict:
    """Insert a new row to health_events via shared Supabase client (WP-3).
    Events are not upserted — each submission creates a distinct timeline entry."""
    return _shared_insert("health_events", payload)


# ── Confirmation message ──────────────────────────────────────────────────────

def _build_event_confirmation(payload: dict, saved_row: dict) -> list:
    event_date = payload.get("event_date", date.today().isoformat())
    event_type = EVENT_TYPE_LABELS.get(payload.get("event_type", "other"), "Event")
    title = payload.get("title", "—")
    outcome = payload.get("outcome", "")
    follow_up = payload.get("follow_up_required", False)
    follow_up_date = payload.get("follow_up_date", "")
    follow_up_notes = payload.get("follow_up_notes", "")
    doc_path = payload.get("local_document_path", "")
    row_id = saved_row.get("id", "")

    lines = [f"*Type:* {event_type}   *Date:* {event_date}"]
    if outcome:
        lines.append(f"*Outcome:* {outcome[:200]}")
    if follow_up:
        fu_line = "*Follow-up required*"
        if follow_up_date:
            fu_line += f" — by {follow_up_date}"
        if follow_up_notes:
            fu_line += f" — {follow_up_notes[:100]}"
        lines.append(fu_line)
    if doc_path:
        lines.append(f"*Document:* `{doc_path}` _(path stored — file stays local)_")

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🏥 Health Event Logged — {title[:60]}"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"Saved to health timeline · id `{row_id[:8]}…`" if row_id else "Saved to health timeline"},
            ],
        },
    ]
    return blocks


# ── Main submit handler ───────────────────────────────────────────────────────

def handle_health_event_submit(
    values: dict,
    user_id: str,
    client: Any,
) -> None:
    """Process event modal submission. Always sends feedback; never raises."""
    try:
        payload = parse_event_modal_values(values)
        log.info("[health-event] Parsed fields: %s for user=%s", list(payload.keys()), user_id)

        if not payload.get("title"):
            client.chat_postMessage(
                channel=user_id,
                text="⚠️ Health event not saved — title is required.",
            )
            return

        saved_row = _supabase_insert_health_event(payload)
        log.info("[health-event] Inserted row id=%s", saved_row.get("id"))

        blocks = _build_event_confirmation(payload, saved_row)
        client.chat_postMessage(
            channel=user_id,
            text=f"Health event logged — {payload.get('title', '')}",
            blocks=blocks,
        )

    except RuntimeError as exc:
        log.error("[health-event] Supabase write failed: %s", exc)
        _send_error_dm(client, user_id, str(exc))
    except Exception as exc:
        log.error("[health-event] Unexpected error: %s — %s", type(exc).__name__, exc)
        _send_error_dm(client, user_id, f"{type(exc).__name__}: {exc}")


def _send_error_dm(client: Any, user_id: str, reason: str) -> None:
    try:
        client.chat_postMessage(
            channel=user_id,
            text="⚠️ Health event could not be saved.",
            blocks=[{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "⚠️ *Health event could not be saved.*\n\n"
                        f"Reason: `{reason[:300]}`\n\n"
                        "Your data was not stored. Please try again."
                    ),
                },
            }],
        )
    except Exception as dm_exc:
        log.error("[health-event] Could not send error DM: %s", dm_exc)
