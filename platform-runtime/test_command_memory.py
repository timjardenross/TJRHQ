"""Tests for MSN-0040A — Command Memory MVP integration.

Covers:
  - CommandMemoryClient.insert/update — success/failure detection, Prefer header
  - CommandMemoryClient.select / writes — disabled mode (no creds) is non-blocking
  - save_mission_to_command_memory()  — payload shape, status=Designed, owner default
  - log_decision_to_command_memory()  — DEC- id generation, return value
  - update_mission_status_in_command_memory() — payload shape
  - search_memory() — return shape
  - query handlers (memory_queries) — Slack mrkdwn formatting, empty results,
    usage message, and non-raising on backend error

No live network: the Supabase REST layer is always mocked.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

import command_memory_integration as cmi


def _enabled_client():
    """A CommandMemoryClient that believes it is configured, with request() stubbed."""
    client = cmi.CommandMemoryClient.__new__(cmi.CommandMemoryClient)
    client.url = "https://example.supabase.co"
    client.key = "test-key"
    client._initialized = True
    return client


# ===========================================================================
# CommandMemoryClient: insert / update success detection
# ===========================================================================

class TestClientWrites(unittest.TestCase):

    def test_insert_success_when_row_returned(self):
        client = _enabled_client()
        # PostgREST with return=representation echoes the inserted row.
        client.request = MagicMock(return_value=[{"id": "M-1"}])
        self.assertTrue(client.insert("missions", {"id": "M-1"}))
        # Verify Prefer header requesting representation was sent.
        _, kwargs = client.request.call_args
        self.assertEqual(
            kwargs.get("extra_headers", {}).get("Prefer"),
            "return=representation",
        )

    def test_insert_failure_when_no_row(self):
        client = _enabled_client()
        client.request = MagicMock(return_value=None)
        self.assertFalse(client.insert("missions", {"id": "M-1"}))

    def test_update_failure_when_empty_list(self):
        # Updating a non-existent id returns [] under return=representation.
        client = _enabled_client()
        client.request = MagicMock(return_value=[])
        self.assertFalse(client.update("missions", "M-missing", {"status": "Active"}))

    def test_update_success_when_row_returned(self):
        client = _enabled_client()
        client.request = MagicMock(return_value=[{"id": "M-1", "status": "Active"}])
        self.assertTrue(client.update("missions", "M-1", {"status": "Active"}))


# ===========================================================================
# Disabled mode: no credentials → non-blocking no-ops
# ===========================================================================

class TestDisabledMode(unittest.TestCase):

    def setUp(self):
        self.client = cmi.CommandMemoryClient.__new__(cmi.CommandMemoryClient)
        self.client.url = ""
        self.client.key = ""
        self.client._initialized = False

    def test_insert_returns_false(self):
        self.assertFalse(self.client.insert("missions", {"id": "M-1"}))

    def test_update_returns_false(self):
        self.assertFalse(self.client.update("missions", "M-1", {"status": "Active"}))

    def test_select_returns_empty_list(self):
        self.assertEqual(self.client.select("missions"), [])


# ===========================================================================
# High-level write functions: payload shape
# ===========================================================================

class TestWriteFunctions(unittest.TestCase):

    def test_save_mission_payload(self):
        fake = MagicMock()
        fake.insert.return_value = True
        with patch.object(cmi, "get_client", return_value=fake):
            ok = cmi.save_mission_to_command_memory("M-X", "Test Mission", "U001")
        self.assertTrue(ok)
        table, record = fake.insert.call_args[0]
        self.assertEqual(table, "missions")
        self.assertEqual(record["id"], "M-X")
        self.assertEqual(record["title"], "Test Mission")
        self.assertEqual(record["status"], "Idea")  # M-20260614: /mission-capture persists as Idea (Gap 1 closure)
        self.assertEqual(record["owner"], "U001")  # defaults to creator
        self.assertEqual(record["created_by"], "U001")

    def test_save_mission_owner_override(self):
        fake = MagicMock()
        fake.insert.return_value = True
        with patch.object(cmi, "get_client", return_value=fake):
            cmi.save_mission_to_command_memory("M-X", "T", "U001", owner="U999")
        _, record = fake.insert.call_args[0]
        self.assertEqual(record["owner"], "U999")

    def test_log_decision_returns_generated_id(self):
        fake = MagicMock()
        fake.insert.return_value = True
        with patch.object(cmi, "get_client", return_value=fake):
            decision_id = cmi.log_decision_to_command_memory(
                "We will ship the MVP", "It is ready", "U001"
            )
        self.assertIsNotNone(decision_id)
        self.assertTrue(decision_id.startswith("DEC-"))
        table, record = fake.insert.call_args[0]
        self.assertEqual(table, "decisions")
        self.assertEqual(record["statement"], "We will ship the MVP")
        self.assertEqual(record["status"], "Active")

    def test_log_decision_returns_none_on_failure(self):
        fake = MagicMock()
        fake.insert.return_value = False
        with patch.object(cmi, "get_client", return_value=fake):
            self.assertIsNone(
                cmi.log_decision_to_command_memory("S", "R", "U001")
            )

    def test_update_mission_status_payload(self):
        fake = MagicMock()
        fake.update.return_value = True
        with patch.object(cmi, "get_client", return_value=fake):
            ok = cmi.update_mission_status_in_command_memory("M-X", "Active", "U001")
        self.assertTrue(ok)
        table, record_id, updates = fake.update.call_args[0]
        self.assertEqual(table, "missions")
        self.assertEqual(record_id, "M-X")
        self.assertEqual(updates["status"], "Active")
        self.assertEqual(updates["updated_by"], "U001")


# ===========================================================================
# Read functions
# ===========================================================================

class TestReadFunctions(unittest.TestCase):

    def test_get_active_missions_filters_status(self):
        fake = MagicMock()
        fake.select.return_value = [{"id": "M-1", "title": "T", "owner": "U001"}]
        with patch.object(cmi, "get_client", return_value=fake):
            rows = cmi.get_active_missions()
        self.assertEqual(len(rows), 1)
        _, kwargs = fake.select.call_args
        self.assertEqual(kwargs["filters"], {"status": "eq.Active"})

    def test_search_memory_shape(self):
        fake = MagicMock()
        fake.select.side_effect = [
            [{"id": "M-1", "title": "Slack Commander"}],   # missions
            [{"id": "DEC-1", "statement": "We will use Slack"}],  # decisions
        ]
        with patch.object(cmi, "get_client", return_value=fake):
            result = cmi.search_memory("Slack")
        self.assertIn("missions", result)
        self.assertIn("decisions", result)
        self.assertEqual(len(result["missions"]), 1)
        self.assertEqual(len(result["decisions"]), 1)


# ===========================================================================
# Query handlers (commands/memory_queries.py): Slack formatting
# ===========================================================================

class TestQueryHandlers(unittest.TestCase):

    def setUp(self):
        from commands import memory_queries
        self.mq = memory_queries

    def test_missions_active_formats_results(self):
        ack, respond = MagicMock(), MagicMock()
        with patch.object(
            self.mq, "get_active_missions",
            create=True,
            return_value=[{"id": "M-1", "title": "Test", "owner": "U001"}],
        ):
            # get_active_missions is imported inside the function, so patch source.
            with patch("command_memory_integration.get_active_missions",
                       return_value=[{"id": "M-1", "title": "Test", "owner": "U001"}]):
                self.mq.handle_missions_active(ack, respond)
        ack.assert_called_once()
        out = respond.call_args[0][0]
        self.assertIn("M-1", out)
        self.assertIn("Test", out)

    def test_missions_active_empty(self):
        ack, respond = MagicMock(), MagicMock()
        with patch("command_memory_integration.get_active_missions", return_value=[]):
            self.mq.handle_missions_active(ack, respond)
        self.assertIn("No active missions", respond.call_args[0][0])

    def test_memory_search_requires_query(self):
        ack, respond = MagicMock(), MagicMock()
        self.mq.handle_memory_search(ack, respond, {"text": "   "})
        ack.assert_called_once()
        self.assertIn("Usage", respond.call_args[0][0])

    def test_memory_search_formats_results(self):
        ack, respond = MagicMock(), MagicMock()
        with patch("command_memory_integration.search_memory", return_value={
            "missions": [{"id": "M-1", "title": "Slack Commander"}],
            "decisions": [{"id": "DEC-1", "statement": "We will use Slack"}],
        }):
            self.mq.handle_memory_search(ack, respond, {"text": "Slack"})
        out = respond.call_args[0][0]
        self.assertIn("Slack Commander", out)
        self.assertIn("DEC-1", out)

    def test_handler_does_not_raise_on_backend_error(self):
        ack, respond = MagicMock(), MagicMock()
        with patch("command_memory_integration.get_active_decisions",
                   side_effect=RuntimeError("boom")):
            # Must not propagate — non-blocking by contract.
            self.mq.handle_decisions_active(ack, respond)
        self.assertTrue(respond.called)


# ===========================================================================
# /mission-status handler
# ===========================================================================

class TestMissionStatusHandler(unittest.TestCase):

    def setUp(self):
        from commands import memory_queries
        self.mq = memory_queries

    def test_usage_when_missing_args(self):
        ack, respond = MagicMock(), MagicMock()
        self.mq.handle_mission_status(ack, respond, {"text": "USS-TJR-MSN-0040"})
        ack.assert_called_once()
        self.assertIn("Usage", respond.call_args[0][0])

    def test_invalid_status_rejected(self):
        ack, respond = MagicMock(), MagicMock()
        self.mq.handle_mission_status(
            ack, respond, {"text": "USS-TJR-MSN-0040 Bogus", "user_id": "U001"}
        )
        out = respond.call_args[0][0]
        self.assertIn("Invalid status", out)

    def test_success_path_updates_and_confirms(self):
        ack, respond = MagicMock(), MagicMock()
        with patch("command_memory_integration.update_mission_status_in_command_memory",
                   return_value=True) as mock_update:
            self.mq.handle_mission_status(
                ack, respond, {"text": "USS-TJR-MSN-0040 active", "user_id": "U001"}
            )
        # Status normalised to canonical casing before the write.
        mock_update.assert_called_once_with(
            mission_id="USS-TJR-MSN-0040", new_status="Active", user_id="U001"
        )
        out = respond.call_args[0][0]
        self.assertIn("USS-TJR-MSN-0040", out)
        self.assertIn("Active", out)

    def test_failure_path_reports_no_change(self):
        ack, respond = MagicMock(), MagicMock()
        with patch("command_memory_integration.update_mission_status_in_command_memory",
                   return_value=False):
            self.mq.handle_mission_status(
                ack, respond, {"text": "M-missing Active", "user_id": "U001"}
            )
        out = respond.call_args[0][0]
        self.assertIn("Could not update", out)

    def test_does_not_raise_on_backend_error(self):
        ack, respond = MagicMock(), MagicMock()
        with patch("command_memory_integration.update_mission_status_in_command_memory",
                   side_effect=RuntimeError("boom")):
            self.mq.handle_mission_status(
                ack, respond, {"text": "M-1 Active", "user_id": "U001"}
            )
        self.assertTrue(respond.called)


if __name__ == "__main__":
    unittest.main()
