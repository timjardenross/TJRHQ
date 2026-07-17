"""Offline tests for the Telegram approval-marker helper.

Run from the telegram-bot dir:
    python -m unittest tests.test_approval
"""

import sys
import unittest
from pathlib import Path

_BOT_DIR = Path(__file__).resolve().parent.parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

import approval  # noqa: E402

BREQ_BODY = """# Build Request
- Request ID: BREQ-20260617-101010-fix-truncation
- Status: PENDING_TRIAGE

## Title
Fix message truncation

## Summary
Replies are cut at 4000 chars.
"""

REQUEST_ID = "BREQ-20260617-101010-fix-truncation"


class FakeRestrictedClient:
    def __init__(self):
        self.rows = []

    def append_build_request(self, row):
        self.rows.append(row)


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = _BOT_DIR / "tests" / "_tmp_inbox"
        self.tmp.mkdir(parents=True, exist_ok=True)
        (self.tmp / f"{REQUEST_ID}.md").write_text(BREQ_BODY, encoding="utf-8")
        self._orig_inbox = approval.INBOX_DIR
        approval.INBOX_DIR = self.tmp

    def tearDown(self):
        approval.INBOX_DIR = self._orig_inbox
        for p in sorted(self.tmp.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
        self.tmp.rmdir()

    def test_find_breq_exact_and_missing(self):
        self.assertIsNotNone(approval._find_breq(REQUEST_ID))
        self.assertIsNone(approval._find_breq("BREQ-does-not-exist"))

    def test_marker_row_shape(self):
        path = approval._find_breq(REQUEST_ID)
        row = approval.build_marker_row(REQUEST_ID, 643108092, path)
        self.assertEqual(row["source"], approval.APPROVAL_SOURCE)
        self.assertEqual(row["status"], "approved")
        self.assertEqual(row["requested_by"], "tg:643108092")
        self.assertEqual(row["conversation_context"], REQUEST_ID)
        self.assertEqual(row["title"], "Fix message truncation")
        self.assertTrue(row["request_id"].startswith(f"APPROVAL-{REQUEST_ID}-"))
        self.assertTrue(row["record_path"].endswith(f"{REQUEST_ID}.md"))

    def test_submit_requires_db(self):
        with self.assertRaises(approval.ApprovalError):
            approval.submit_approval(REQUEST_ID, 1, supabase_client=None)

    def test_submit_unknown_id(self):
        with self.assertRaises(approval.ApprovalError):
            approval.submit_approval("BREQ-nope", 1, supabase_client=FakeRestrictedClient())

    def test_submit_happy_path(self):
        client = FakeRestrictedClient()
        marker_id = approval.submit_approval(REQUEST_ID, 643108092, client)
        self.assertEqual(len(client.rows), 1)
        self.assertEqual(client.rows[0]["request_id"], marker_id)
        self.assertEqual(client.rows[0]["status"], "approved")


if __name__ == "__main__":
    unittest.main()
