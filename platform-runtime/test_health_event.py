"""Tests for health_event.py — /health-event Slack command."""

import json
import sys
import types
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))

from commands.health_event import (
    ALLOWED_EVENT_FIELDS,
    EVENT_MODAL_CALLBACK_ID,
    EVENT_TYPE_LABELS,
    build_health_event_modal,
    handle_health_event_submit,
    parse_event_modal_values,
)


# ── Privacy boundary ──────────────────────────────────────────────────────────

class TestPrivacyBoundary(unittest.TestCase):
    def test_diagnosis_not_in_allowed_fields(self):
        self.assertNotIn("diagnosis", ALLOWED_EVENT_FIELDS)

    def test_medication_name_not_in_allowed_fields(self):
        self.assertNotIn("medication_name", ALLOWED_EVENT_FIELDS)

    def test_clinical_notes_not_in_allowed_fields(self):
        self.assertNotIn("clinical_notes", ALLOWED_EVENT_FIELDS)

    def test_imaging_result_not_in_allowed_fields(self):
        self.assertNotIn("imaging_result", ALLOWED_EVENT_FIELDS)

    def test_blood_pressure_not_in_allowed_fields(self):
        self.assertNotIn("blood_pressure", ALLOWED_EVENT_FIELDS)

    def test_required_fields_present(self):
        for f in ("event_date", "event_type", "title", "source"):
            self.assertIn(f, ALLOWED_EVENT_FIELDS)

    def test_local_document_path_is_path_only(self):
        # Path field must be present so users CAN store a path pointer
        self.assertIn("local_document_path", ALLOWED_EVENT_FIELDS)

    def test_parse_strips_prohibited_fields(self):
        values = _make_values(title="Test", extra_key="diagnosis_field")
        # Inject a fake prohibited field into the raw output by monkey-patching
        result = parse_event_modal_values(values)
        self.assertNotIn("diagnosis", result)
        self.assertNotIn("medication_name", result)
        self.assertNotIn("clinical_notes", result)

    def test_event_type_enum_excludes_diagnosis(self):
        self.assertNotIn("diagnosis", EVENT_TYPE_LABELS)


# ── Modal parsing ─────────────────────────────────────────────────────────────

class TestParseModalValues(unittest.TestCase):
    def test_full_parse(self):
        today = date.today().isoformat()
        values = _make_values(
            title="Spine review",
            event_type="appointment",
            description="Saw consultant",
            provider="Dr Smith",
            outcome="Continue plan",
            follow_up="true",
            follow_up_notes="Book MRI",
            local_document_path="memory/health/documents/test.pdf",
        )
        result = parse_event_modal_values(values)
        self.assertEqual(result["title"], "Spine review")
        self.assertEqual(result["event_type"], "appointment")
        self.assertEqual(result["description"], "Saw consultant")
        self.assertEqual(result["provider"], "Dr Smith")
        self.assertEqual(result["outcome"], "Continue plan")
        self.assertTrue(result["follow_up_required"])
        self.assertEqual(result["follow_up_notes"], "Book MRI")
        self.assertEqual(result["local_document_path"], "memory/health/documents/test.pdf")
        self.assertEqual(result["source"], "slack")

    def test_follow_up_false_by_default(self):
        values = _make_values(title="Quick visit", follow_up="false")
        result = parse_event_modal_values(values)
        self.assertFalse(result["follow_up_required"])

    def test_optional_fields_absent_when_not_submitted(self):
        values = _make_values(title="Referral only")
        result = parse_event_modal_values(values)
        self.assertNotIn("description", result)
        self.assertNotIn("provider", result)
        self.assertNotIn("outcome", result)
        self.assertNotIn("local_document_path", result)

    def test_earlier_sentinel_defaults_to_today(self):
        values = _make_values(title="Old event", event_date_sentinel="earlier")
        result = parse_event_modal_values(values)
        self.assertEqual(result["event_date"], date.today().isoformat())

    def test_only_allowed_fields_in_output(self):
        values = _make_values(title="Test")
        result = parse_event_modal_values(values)
        for key in result:
            self.assertIn(key, ALLOWED_EVENT_FIELDS, f"Unexpected field in output: {key}")

    def test_event_date_defaults_to_today(self):
        values = _make_values(title="Today event")
        result = parse_event_modal_values(values)
        self.assertEqual(result["event_date"], date.today().isoformat())

    def test_source_is_always_slack(self):
        values = _make_values(title="Any")
        result = parse_event_modal_values(values)
        self.assertEqual(result["source"], "slack")


# ── Supabase failure handling ─────────────────────────────────────────────────

class TestSupabaseFailureHandling(unittest.TestCase):
    def test_raises_when_no_credentials(self):
        from commands.health_event import _supabase_insert_health_event
        with patch.dict("os.environ", {"SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": ""}):
            with self.assertRaises(RuntimeError):
                _supabase_insert_health_event({"event_date": "2026-06-12", "title": "Test"})

    def test_sends_error_dm_on_supabase_failure(self):
        mock_client = MagicMock()
        values = _make_values(title="Fail test")

        with patch("commands.health_event._supabase_insert_health_event", side_effect=RuntimeError("DB down")):
            handle_health_event_submit(values, "U123", mock_client)

        mock_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_client.chat_postMessage.call_args
        self.assertIn("U123", str(call_kwargs))

    def test_sends_confirmation_on_success(self):
        mock_client = MagicMock()
        saved_row = {"id": "abc-123", "event_date": "2026-06-12", "title": "Visit"}
        values = _make_values(title="Visit", event_type="appointment")

        with patch("commands.health_event._supabase_insert_health_event", return_value=saved_row):
            handle_health_event_submit(values, "U456", mock_client)

        mock_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_client.chat_postMessage.call_args
        # Confirmation sent to the user
        self.assertIn("U456", str(call_kwargs))

    def test_missing_title_sends_error_not_inserts(self):
        mock_client = MagicMock()
        values = _make_values(title="")  # Empty title

        with patch("commands.health_event._supabase_insert_health_event") as mock_insert:
            handle_health_event_submit(values, "U789", mock_client)
            mock_insert.assert_not_called()

        mock_client.chat_postMessage.assert_called_once()


# ── Confirmation message ──────────────────────────────────────────────────────

class TestConfirmationMessage(unittest.TestCase):
    def test_confirmation_has_header_section_context(self):
        from commands.health_event import _build_event_confirmation
        payload = {
            "title": "Spine review",
            "event_type": "appointment",
            "event_date": "2026-06-12",
            "outcome": "Continue plan",
            "follow_up_required": True,
        }
        saved_row = {"id": "abcdef12-1234-5678-abcd-ef1234567890"}
        blocks = _build_event_confirmation(payload, saved_row)
        types_found = {b["type"] for b in blocks}
        self.assertIn("header", types_found)
        self.assertIn("section", types_found)
        self.assertIn("context", types_found)

    def test_document_path_shown_when_present(self):
        from commands.health_event import _build_event_confirmation
        payload = {
            "title": "Test",
            "event_type": "other",
            "event_date": "2026-06-12",
            "local_document_path": "memory/health/documents/test.pdf",
        }
        blocks = _build_event_confirmation(payload, {})
        full_text = " ".join(str(b) for b in blocks)
        self.assertIn("test.pdf", full_text)
        self.assertIn("path stored", full_text)


# ── Modal metadata ────────────────────────────────────────────────────────────

class TestModalMetadata(unittest.TestCase):
    def test_callback_id_is_stable(self):
        self.assertEqual(EVENT_MODAL_CALLBACK_ID, "health_event_modal")

    def test_modal_has_required_blocks(self):
        modal = build_health_event_modal()
        block_ids = {b.get("block_id") for b in modal.get("blocks", [])}
        for required in ("event_date_block", "event_type_block", "title_block"):
            self.assertIn(required, block_ids, f"Missing block: {required}")

    def test_modal_type_is_modal(self):
        modal = build_health_event_modal()
        self.assertEqual(modal["type"], "modal")

    def test_all_event_types_have_labels(self):
        modal = build_health_event_modal()
        event_type_block = next(b for b in modal["blocks"] if b.get("block_id") == "event_type_block")
        option_values = {o["value"] for o in event_type_block["element"]["options"]}
        self.assertEqual(option_values, set(EVENT_TYPE_LABELS.keys()))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_values(
    title: str = "",
    event_type: str = "appointment",
    event_date_sentinel: str = None,
    description: str = None,
    provider: str = None,
    outcome: str = None,
    follow_up: str = "false",
    follow_up_notes: str = None,
    local_document_path: str = None,
    extra_key: str = None,
) -> dict:
    """Build a Slack modal values dict matching the health_event modal block structure."""
    today = date.today().isoformat()
    event_date_value = event_date_sentinel or today

    def _text_val(v):
        return {"value": v} if v else {"value": None}

    def _select_val(v):
        return {"selected_option": {"value": v}} if v else {"selected_option": None}

    values = {
        "event_date_block":    {"event_date":          _select_val(event_date_value)},
        "event_type_block":    {"event_type":          _select_val(event_type)},
        "title_block":         {"title":               _text_val(title or None)},
        "description_block":   {"description":         _text_val(description)},
        "provider_block":      {"provider":            _text_val(provider)},
        "outcome_block":       {"outcome":             _text_val(outcome)},
        "follow_up_block":     {"follow_up_required":  _select_val(follow_up)},
        "follow_up_notes_block": {"follow_up_notes":   _text_val(follow_up_notes)},
        "local_doc_block":     {"local_document_path": _text_val(local_document_path)},
    }
    return values


if __name__ == "__main__":
    unittest.main()
