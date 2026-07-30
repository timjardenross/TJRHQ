"""Tests for telegram-bot/notebook_writer.py (EXEC-010C WP3)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_BOT_DIR = Path(__file__).resolve().parent.parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

import notebook_writer


class TestCaptureNote(unittest.TestCase):

    def _make_client(self, note_id: str = "uuid-abcd") -> MagicMock:
        client = MagicMock()
        chain = MagicMock()
        chain.execute.return_value.data = [{"id": note_id}]
        client.table.return_value.insert.return_value = chain
        return client

    # ── Empty content ──────────────────────────────────────────────────────────

    def test_empty_content_returns_none(self):
        result = notebook_writer.capture_note("", client=self._make_client())
        self.assertIsNone(result)

    def test_whitespace_only_returns_none(self):
        result = notebook_writer.capture_note("   ", client=self._make_client())
        self.assertIsNone(result)

    # ── No client ─────────────────────────────────────────────────────────────

    def test_none_client_with_no_env_returns_none(self):
        with patch.dict("os.environ", {}, clear=True):
            result = notebook_writer.capture_note("content", client=None)
        self.assertIsNone(result)

    # ── Successful capture ─────────────────────────────────────────────────────

    def test_returns_note_id_on_success(self):
        client = self._make_client("uuid-abcd")
        result = notebook_writer.capture_note("Test idea", client=client)
        self.assertEqual(result, "uuid-abcd")

    def test_inserts_correct_source(self):
        client = self._make_client()
        notebook_writer.capture_note("Content", source="telegram", client=client)
        insert_args = client.table.return_value.insert.call_args[0][0]
        self.assertEqual(insert_args["source"], "telegram")

    def test_inserts_captured_status(self):
        client = self._make_client()
        notebook_writer.capture_note("Content", client=client)
        insert_args = client.table.return_value.insert.call_args[0][0]
        self.assertEqual(insert_args["status"], "CAPTURED")

    def test_content_stripped(self):
        client = self._make_client()
        notebook_writer.capture_note("  trimmed  ", client=client)
        insert_args = client.table.return_value.insert.call_args[0][0]
        self.assertEqual(insert_args["raw_content"], "trimmed")

    def test_title_stored_when_provided(self):
        client = self._make_client()
        notebook_writer.capture_note("Content", title="My Title", client=client)
        insert_args = client.table.return_value.insert.call_args[0][0]
        self.assertEqual(insert_args.get("title"), "My Title")

    def test_title_truncated_to_255(self):
        client = self._make_client()
        long_title = "X" * 300
        notebook_writer.capture_note("Content", title=long_title, client=client)
        insert_args = client.table.return_value.insert.call_args[0][0]
        self.assertLessEqual(len(insert_args["title"]), 255)

    def test_tags_passed_through(self):
        client = self._make_client()
        notebook_writer.capture_note("Content", tags=["strategy", "ops"], client=client)
        insert_args = client.table.return_value.insert.call_args[0][0]
        self.assertEqual(insert_args["tags"], ["strategy", "ops"])

    # ── Failure handling ───────────────────────────────────────────────────────

    def test_exception_returns_none(self):
        client = MagicMock()
        client.table.return_value.insert.return_value.execute.side_effect = Exception("DB error")
        result = notebook_writer.capture_note("Content", client=client)
        self.assertIsNone(result)

    def test_empty_response_data_returns_none(self):
        client = MagicMock()
        client.table.return_value.insert.return_value.execute.return_value.data = []
        result = notebook_writer.capture_note("Content", client=client)
        self.assertIsNone(result)


# ── get_client_or_none ─────────────────────────────────────────────────────────

class TestGetClientOrNone(unittest.TestCase):

    def test_returns_none_when_no_env(self):
        with patch.dict("os.environ", {}, clear=True):
            result = notebook_writer.get_client_or_none()
        self.assertIsNone(result)

    def test_returns_none_when_only_url_set(self):
        with patch.dict("os.environ", {"SUPABASE_URL": "https://example.supabase.co"}, clear=True):
            result = notebook_writer.get_client_or_none()
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
