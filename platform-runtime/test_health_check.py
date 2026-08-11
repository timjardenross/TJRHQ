"""Tests for the /health-check command.

Rewritten 2026-08-11 (Fleet Engineering Review backlog item) — the
previous version of this file imported ALLOWED_FIELDS, calculate_daily_
status, parse_modal_values, _supabase_upsert_health_log, and
_build_confirmation_message, none of which exist in commands/
health_check.py anymore. The module was consolidated at some point
after this file was last touched: modal-value extraction, payload
construction, the Supabase write, and confirmation-message building all
now live inline in handle_health_check_submit() (a single function),
and the GREEN/AMBER/RED daily-status calculation was dropped entirely
(the current confirmation DM just reports saved/not-saved, no traffic
light). This rewrite tests today's actual public API instead of
resurrecting removed functions.

Covers:
  1. Modal shape — required blocks present, stable callback_id
  2. _extract() — Block Kit state parsing (selected_option / value)
  3. handle_health_check_submit — payload construction only ever
     touches the named, hardcoded fields the function extracts (the
     privacy boundary the old ALLOWED_FIELDS constant used to test is
     now structural: there is no code path that could forward an
     arbitrary/clinical field, because nothing reads one)
  4. Supabase failure handling — visible warning DM, no crash
  5. Confirmation DM sent on success

Run: platform-runtime/.venv/bin/python -m pytest platform-runtime/test_health_check.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from commands.health_check import (
    MODAL_CALLBACK_ID,
    build_health_check_modal,
    handle_health_check_submit,
    _extract,
    _make_supabase,
)


# ─── 1. Modal shape ───────────────────────────────────────────────────────────

class TestModalMetadata(unittest.TestCase):

    def test_callback_id_is_stable(self):
        self.assertEqual(MODAL_CALLBACK_ID, "health_check_modal")

    def test_modal_has_required_blocks(self):
        modal = build_health_check_modal()
        self.assertEqual(modal["callback_id"], MODAL_CALLBACK_ID)
        self.assertEqual(modal["type"], "modal")
        block_ids = [b.get("block_id") for b in modal["blocks"]]
        required = [
            "nervous_system_state", "energy", "mood",
            "sleep_hours", "sleep_quality", "pain_score",
            "workload_constraint", "work_location",
        ]
        for req in required:
            self.assertIn(req, block_ids, f"Missing required block: {req}")


# ─── 2. _extract() ────────────────────────────────────────────────────────────

class TestExtract(unittest.TestCase):

    def test_extracts_selected_option_value(self):
        values = {"energy": {"value": {"selected_option": {"value": "high"}}}}
        self.assertEqual(_extract(values, "energy"), "high")

    def test_extracts_plain_text_value(self):
        values = {"notes": {"value": {"value": "Feeling okay"}}}
        self.assertEqual(_extract(values, "notes"), "Feeling okay")

    def test_missing_block_returns_none(self):
        self.assertIsNone(_extract({}, "energy"))

    def test_blank_string_returns_none(self):
        values = {"notes": {"value": {"value": "   "}}}
        self.assertIsNone(_extract(values, "notes"))


# ─── 3 & 4 & 5. Submit handler: payload safety, failure handling, confirmation ─

def _full_values(**overrides):
    defaults = {
        "nervous_system_state": {"value": {"selected_option": {"value": "calm"}}},
        "energy":               {"value": {"selected_option": {"value": "high"}}},
        "mood":                 {"value": {"selected_option": {"value": "positive"}}},
        "sleep_hours":          {"value": {"value": "7.5"}},
        "sleep_quality":        {"value": {"selected_option": {"value": "good"}}},
        "cpap_used":            {"value": {"selected_option": {"value": "yes"}}},
        "cpap_hours":           {"value": {"value": "6"}},
        "pain_score":           {"value": {"value": "2"}},
        "sitting_tolerance_minutes": {"value": {"value": "60"}},
        "workload_constraint":  {"value": {"selected_option": {"value": "normal"}}},
        "work_location":        {"value": {"selected_option": {"value": "home"}}},
        "movement_notes":       {"value": {"value": "short walk"}},
        "notes":                {"value": {"value": "Good day"}},
    }
    defaults.update(overrides)
    return defaults


class TestSubmitPayloadSafety(unittest.TestCase):
    """The old privacy-boundary test checked an ALLOWED_FIELDS allowlist
    that no longer exists — that mechanism was replaced with explicit,
    named field extraction (_extract is only ever called for the fixed
    block_ids above). Verify that guarantee holds by inspecting the
    actual payload the code builds, injecting an unrelated block that a
    naive implementation might have accidentally passed through."""

    def test_payload_only_contains_known_fields(self):
        mock_db = MagicMock()
        mock_db.is_enabled.return_value = True
        mock_db.raw_client.table.return_value.upsert.return_value.execute.return_value = None

        values = _full_values(diagnosis={"value": {"value": "should never be read"}})

        with patch("commands.health_check._make_supabase", return_value=mock_db):
            handle_health_check_submit(values, user_id="U1", client=MagicMock())

        payload = mock_db.raw_client.table.call_args
        upsert_call = mock_db.raw_client.table.return_value.upsert.call_args
        sent_payload = upsert_call[0][0]
        self.assertNotIn("diagnosis", sent_payload)
        allowed = {
            "log_date", "source", "nervous_system_state", "energy", "mood",
            "sleep_quality", "workload_constraint", "sleep_hours", "cpap_used",
            "cpap_hours", "pain_score", "sitting_tolerance_minutes",
            "work_location", "movement_notes", "notes",
        }
        self.assertTrue(set(sent_payload.keys()) <= allowed, set(sent_payload.keys()) - allowed)

    def test_pain_score_clamped_to_0_10(self):
        mock_db = MagicMock()
        mock_db.is_enabled.return_value = True

        values = _full_values(pain_score={"value": {"value": "99"}})
        with patch("commands.health_check._make_supabase", return_value=mock_db):
            handle_health_check_submit(values, user_id="U1", client=MagicMock())

        sent_payload = mock_db.raw_client.table.return_value.upsert.call_args[0][0]
        self.assertEqual(sent_payload["pain_score"], 10)


class TestSupabaseFailureHandling(unittest.TestCase):

    def test_no_client_sends_warning_dm_no_crash(self):
        mock_client = MagicMock()
        with patch("commands.health_check._make_supabase", return_value=None):
            handle_health_check_submit(_full_values(), user_id="U1", client=mock_client)

        mock_client.chat_postMessage.assert_called_once()
        call_text = str(mock_client.chat_postMessage.call_args)
        self.assertIn("could not be saved", call_text.lower())

    def test_upsert_exception_falls_back_to_insert(self):
        mock_db = MagicMock()
        mock_db.is_enabled.return_value = True
        mock_db.raw_client.table.return_value.upsert.return_value.execute.side_effect = RuntimeError("db down")
        mock_db.insert.return_value = MagicMock(ok=True)

        with patch("commands.health_check._make_supabase", return_value=mock_db):
            handle_health_check_submit(_full_values(), user_id="U1", client=MagicMock())

        mock_db.insert.assert_called_once()


class TestConfirmationMessage(unittest.TestCase):

    def test_success_sends_confirmation(self):
        mock_db = MagicMock()
        mock_db.is_enabled.return_value = True
        mock_client = MagicMock()

        with patch("commands.health_check._make_supabase", return_value=mock_db):
            handle_health_check_submit(_full_values(), user_id="U456", client=mock_client)

        mock_client.chat_postMessage.assert_called_once()
        call_text = str(mock_client.chat_postMessage.call_args)
        self.assertIn("U456", call_text)
        self.assertIn("Check-in logged", call_text)


if __name__ == "__main__":
    unittest.main()
