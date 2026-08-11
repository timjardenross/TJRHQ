"""Tests for health_event.py — /health-event Slack command.

Rewritten 2026-08-11 (Fleet Engineering Review backlog item) — the
previous version imported ALLOWED_EVENT_FIELDS, EVENT_TYPE_LABELS,
parse_event_modal_values, _supabase_insert_health_event, and
_build_event_confirmation, none of which exist anymore. Same
consolidation as health_check.py: modal parsing, payload construction,
the Supabase insert, and confirmation-message building are now inline
in handle_health_event_submit(); the modal itself dropped
local_document_path entirely. The privacy boundary the old
ALLOWED_EVENT_FIELDS constant tested is now structural — verified
below by checking the actual payload the code sends, not a removed
allowlist constant.

Run: platform-runtime/.venv/bin/python -m pytest platform-runtime/test_health_event.py -v
"""

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))

from commands.health_event import (
    EVENT_MODAL_CALLBACK_ID,
    _EVENT_TYPES,
    build_health_event_modal,
    handle_health_event_submit,
    _extract,
)


# ── Modal metadata ────────────────────────────────────────────────────────────

class TestModalMetadata(unittest.TestCase):
    def test_callback_id_is_stable(self):
        self.assertEqual(EVENT_MODAL_CALLBACK_ID, "health_event_modal")

    def test_modal_type_is_modal(self):
        modal = build_health_event_modal()
        self.assertEqual(modal["type"], "modal")

    def test_modal_has_required_blocks(self):
        modal = build_health_event_modal()
        block_ids = {b.get("block_id") for b in modal["blocks"]}
        for required in ("event_date", "event_type", "title"):
            self.assertIn(required, block_ids, f"Missing block: {required}")

    def test_all_event_types_have_labels(self):
        modal = build_health_event_modal()
        event_type_block = next(b for b in modal["blocks"] if b.get("block_id") == "event_type")
        option_values = {o["value"] for o in event_type_block["element"]["options"]}
        self.assertEqual(option_values, {value for _, value in _EVENT_TYPES})

    def test_no_clinical_document_upload(self):
        """Modal's own copy says 'no clinical documents are uploaded' —
        confirm no file-input block exists to contradict that."""
        modal = build_health_event_modal()
        element_types = {b.get("element", {}).get("type") for b in modal["blocks"] if "element" in b}
        self.assertNotIn("file_input", element_types)


# ── _extract() ─────────────────────────────────────────────────────────────────

class TestExtract(unittest.TestCase):
    def test_extracts_selected_option(self):
        values = {"event_type": {"value": {"selected_option": {"value": "appointment"}}}}
        self.assertEqual(_extract(values, "event_type"), "appointment")

    def test_extracts_selected_date(self):
        values = {"event_date": {"value": {"selected_date": "2026-06-12"}}}
        self.assertEqual(_extract(values, "event_date"), "2026-06-12")

    def test_extracts_plain_text(self):
        values = {"title": {"value": {"value": "Spine review"}}}
        self.assertEqual(_extract(values, "title"), "Spine review")

    def test_missing_returns_none(self):
        self.assertIsNone(_extract({}, "title"))


# ── Submit handler: payload safety, failure handling, confirmation ─────────────

def _full_values(**overrides):
    defaults = {
        "event_date":   {"value": {"selected_date": "2026-06-12"}},
        "event_type":   {"value": {"selected_option": {"value": "appointment"}}},
        "title":        {"value": {"value": "Spine review"}},
        "description":  {"value": {"value": "Saw consultant"}},
        "provider":     {"value": {"value": "Dr Smith"}},
        "outcome":      {"value": {"value": "Continue plan"}},
        "follow_up_required": {"value": {"selected_option": {"value": "yes"}}},
        "follow_up_date": {"value": {"selected_date": "2026-07-01"}},
    }
    defaults.update(overrides)
    return defaults


class TestSubmitPayloadSafety(unittest.TestCase):

    def test_payload_only_contains_known_fields(self):
        """No code path reads a clinical field (diagnosis/medication_name/
        clinical_notes/imaging_result/blood_pressure) — _extract is only
        ever called for the named block_ids in handle_health_event_submit.
        Verify the actual insert payload, not a removed allowlist."""
        mock_db = MagicMock()
        mock_db.is_enabled.return_value = True
        mock_db.insert.return_value = MagicMock(ok=True)

        with patch("commands.health_event._make_supabase", return_value=mock_db):
            handle_health_event_submit(_full_values(), user_id="U1", client=MagicMock())

        sent_payload = mock_db.insert.call_args[0][1]
        for prohibited in ("diagnosis", "medication_name", "clinical_notes",
                           "imaging_result", "blood_pressure"):
            self.assertNotIn(prohibited, sent_payload)
        allowed = {
            "event_date", "event_type", "title", "source", "follow_up_required",
            "description", "provider", "outcome", "follow_up_date",
        }
        self.assertTrue(set(sent_payload.keys()) <= allowed, set(sent_payload.keys()) - allowed)
        self.assertEqual(sent_payload["title"], "Spine review")
        self.assertTrue(sent_payload["follow_up_required"])

    def test_follow_up_date_omitted_when_not_required(self):
        mock_db = MagicMock()
        mock_db.is_enabled.return_value = True
        mock_db.insert.return_value = MagicMock(ok=True)

        values = _full_values(follow_up_required={"value": {"selected_option": {"value": "no"}}})
        with patch("commands.health_event._make_supabase", return_value=mock_db):
            handle_health_event_submit(values, user_id="U1", client=MagicMock())

        sent_payload = mock_db.insert.call_args[0][1]
        self.assertFalse(sent_payload["follow_up_required"])
        self.assertNotIn("follow_up_date", sent_payload)

    def test_missing_title_defaults_to_untitled(self):
        mock_db = MagicMock()
        mock_db.is_enabled.return_value = True
        mock_db.insert.return_value = MagicMock(ok=True)

        values = _full_values(title={"value": {"value": None}})
        with patch("commands.health_event._make_supabase", return_value=mock_db):
            handle_health_event_submit(values, user_id="U1", client=MagicMock())

        sent_payload = mock_db.insert.call_args[0][1]
        self.assertEqual(sent_payload["title"], "(untitled)")


class TestSupabaseFailureHandling(unittest.TestCase):

    def test_no_client_sends_warning_dm_no_crash(self):
        mock_client = MagicMock()
        with patch("commands.health_event._make_supabase", return_value=None):
            handle_health_event_submit(_full_values(), user_id="U123", client=mock_client)

        mock_client.chat_postMessage.assert_called_once()
        call_text = str(mock_client.chat_postMessage.call_args)
        self.assertIn("U123", call_text)
        self.assertIn("could not be saved", call_text.lower())

    def test_insert_failure_sends_warning_not_confirmation(self):
        mock_db = MagicMock()
        mock_db.is_enabled.return_value = True
        mock_db.insert.return_value = MagicMock(ok=False, error="insert failed")
        mock_client = MagicMock()

        with patch("commands.health_event._make_supabase", return_value=mock_db):
            handle_health_event_submit(_full_values(), user_id="U789", client=mock_client)

        call_text = str(mock_client.chat_postMessage.call_args)
        self.assertIn("could not be saved", call_text.lower())


class TestConfirmationMessage(unittest.TestCase):

    def test_success_sends_confirmation(self):
        mock_db = MagicMock()
        mock_db.is_enabled.return_value = True
        mock_db.insert.return_value = MagicMock(ok=True)
        mock_client = MagicMock()

        with patch("commands.health_event._make_supabase", return_value=mock_db):
            handle_health_event_submit(_full_values(), user_id="U456", client=mock_client)

        call_text = str(mock_client.chat_postMessage.call_args)
        self.assertIn("U456", call_text)
        self.assertIn("Event logged", call_text)
        self.assertIn("Spine review", call_text)


if __name__ == "__main__":
    unittest.main()
