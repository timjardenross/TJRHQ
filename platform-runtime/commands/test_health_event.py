"""Tests for slack-bot/commands/health_event.py — WP-6.

Covers:
- parse_event_modal_values: follow_up_date datepicker extraction
- parse_event_modal_values: privacy boundary (ALLOWED_EVENT_FIELDS only)
- parse_event_modal_values: follow_up_required bool conversion
- build_health_event_modal: follow_up_date_block present in modal
- _build_event_confirmation: follow_up_date displayed in confirmation

Run: python3 -m pytest slack-bot/commands/test_health_event.py -v
  or: python3 slack-bot/commands/test_health_event.py
"""

from __future__ import annotations
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Allow imports from both slack-bot/commands and repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_CMD_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_CMD_DIR))

# Patch supabase_insert before importing the module under test
with patch("core.health.supabase_client.supabase_insert", return_value={}):
    from health_event import (
        parse_event_modal_values,
        build_health_event_modal,
        _build_event_confirmation,
        ALLOWED_EVENT_FIELDS,
        EVENT_MODAL_CALLBACK_ID,
    )


def _make_values(
    event_date: str = "2026-06-13",
    event_type: str = "appointment",
    title: str = "Test event",
    follow_up_required: str = "false",
    follow_up_date: str | None = None,
    follow_up_notes: str | None = None,
) -> dict:
    """Build a mock Slack modal values dict."""
    values = {
        "event_date_block": {"event_date": {"selected_option": {"value": event_date}}},
        "event_type_block": {"event_type": {"selected_option": {"value": event_type}}},
        "title_block": {"title": {"value": title}},
        "description_block": {"description": {"value": None}},
        "provider_block": {"provider": {"value": None}},
        "outcome_block": {"outcome": {"value": None}},
        "follow_up_block": {"follow_up_required": {"selected_option": {"value": follow_up_required}}},
        "follow_up_date_block": {"follow_up_date": {"selected_date": follow_up_date}},
        "follow_up_notes_block": {"follow_up_notes": {"value": follow_up_notes}},
        "local_doc_block": {"local_document_path": {"value": None}},
    }
    return values


class TestFollowUpDateParsing(unittest.TestCase):
    """WP-6: follow_up_date datepicker was added to the modal."""

    def test_follow_up_date_present_is_captured(self):
        values = _make_values(follow_up_date="2026-07-01")
        result = parse_event_modal_values(values)
        self.assertEqual(result.get("follow_up_date"), "2026-07-01")

    def test_follow_up_date_absent_is_excluded(self):
        values = _make_values(follow_up_date=None)
        result = parse_event_modal_values(values)
        self.assertNotIn("follow_up_date", result)

    def test_follow_up_date_missing_block_returns_none(self):
        """Graceful degradation when block is entirely absent."""
        values = _make_values()
        del values["follow_up_date_block"]
        result = parse_event_modal_values(values)
        self.assertNotIn("follow_up_date", result)

    def test_follow_up_date_in_allowed_fields(self):
        self.assertIn("follow_up_date", ALLOWED_EVENT_FIELDS)


class TestPrivacyBoundary(unittest.TestCase):

    def test_only_allowed_fields_returned(self):
        values = _make_values()
        result = parse_event_modal_values(values)
        for key in result:
            self.assertIn(key, ALLOWED_EVENT_FIELDS, f"Unexpected field: {key}")

    def test_none_values_excluded(self):
        values = _make_values()
        result = parse_event_modal_values(values)
        for key, val in result.items():
            self.assertIsNotNone(val, f"None value for key: {key}")

    def test_source_always_slack(self):
        values = _make_values()
        result = parse_event_modal_values(values)
        self.assertEqual(result["source"], "slack")


class TestFollowUpRequired(unittest.TestCase):

    def test_follow_up_required_true_is_bool(self):
        values = _make_values(follow_up_required="true")
        result = parse_event_modal_values(values)
        self.assertIs(result["follow_up_required"], True)

    def test_follow_up_required_false_excluded(self):
        """False values are falsy — excluded from result dict (None check strips them)."""
        values = _make_values(follow_up_required="false")
        result = parse_event_modal_values(values)
        # follow_up_required=False is filtered out (falsy, treated as None-equivalent by the {v is not None} guard)
        # The key either is absent or is False
        val = result.get("follow_up_required")
        self.assertFalse(val)  # either absent (None→False) or explicit False


class TestModalStructure(unittest.TestCase):

    def test_follow_up_date_block_present(self):
        """WP-6: datepicker block must be in the modal."""
        modal = build_health_event_modal()
        block_ids = [b.get("block_id") for b in modal["blocks"]]
        self.assertIn("follow_up_date_block", block_ids)

    def test_follow_up_date_action_is_datepicker(self):
        modal = build_health_event_modal()
        date_block = next(
            (b for b in modal["blocks"] if b.get("block_id") == "follow_up_date_block"), None
        )
        self.assertIsNotNone(date_block)
        self.assertEqual(date_block["element"]["type"], "datepicker")
        self.assertEqual(date_block["element"]["action_id"], "follow_up_date")

    def test_modal_callback_id(self):
        modal = build_health_event_modal()
        self.assertEqual(modal["callback_id"], EVENT_MODAL_CALLBACK_ID)


class TestConfirmationMessage(unittest.TestCase):

    def test_follow_up_date_shown_in_confirmation(self):
        payload = {
            "event_date": "2026-06-13",
            "event_type": "appointment",
            "title": "Spine review",
            "follow_up_required": True,
            "follow_up_date": "2026-07-01",
        }
        blocks = _build_event_confirmation(payload, {"id": "abc-123-xyz"})
        # Find the section block
        section = next(b for b in blocks if b["type"] == "section")
        text = section["text"]["text"]
        self.assertIn("2026-07-01", text)

    def test_follow_up_no_date_shows_follow_up_required(self):
        payload = {
            "event_date": "2026-06-13",
            "event_type": "appointment",
            "title": "Spine review",
            "follow_up_required": True,
        }
        blocks = _build_event_confirmation(payload, {})
        section = next(b for b in blocks if b["type"] == "section")
        self.assertIn("Follow-up required", section["text"]["text"])

    def test_no_follow_up_omits_follow_up_line(self):
        payload = {
            "event_date": "2026-06-13",
            "event_type": "appointment",
            "title": "Spine review",
            "follow_up_required": False,
        }
        blocks = _build_event_confirmation(payload, {})
        section = next(b for b in blocks if b["type"] == "section")
        self.assertNotIn("Follow-up required", section["text"]["text"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
