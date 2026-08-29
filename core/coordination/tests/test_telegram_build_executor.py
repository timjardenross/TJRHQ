"""Offline tests for the Telegram approved-build executor.

Run: python -m unittest core.coordination.tests.test_telegram_build_executor
No network / no Supabase / no mistralai: the Supabase client, the coding pass,
and the Telegram notifier are all faked.
"""

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.coordination import telegram_build_executor as ex  # noqa: E402
from core.coordination.engineering_handoff_reader import (  # noqa: E402
    _normalise_token,
    _parse_handoff_file,
)

_PENDING_TOKENS = {"", "PENDING", "PENDINGTRIAGE", "UNASSIGNED", "TRIAGE", "NEW", "OPEN"}

BREQ_BODY = """# Build Request
- Request ID: BREQ-20260617-101010-fix-truncation
- Timestamp: 2026-06-17 10:10:10
- Source: telegram
- Requested By: @tjr
- Status: PENDING_TRIAGE

## Title
Fix message truncation in Chief Engineer comms

## Summary
Replies are cut at 4000 chars; split long messages instead.

## Rationale
Captain loses the tail of long answers.

## Risks
- None identified

## Suggested Next Step
Chunk outgoing messages under the Telegram 4096 limit.

## Conversation Context
(not captured)
"""


def _marker(record_path: str, **over):
    m = {
        "request_id": "APPROVAL-BREQ-20260617-101010-fix-truncation-20260617",
        "source": "telegram-approval",
        "status": "approved",
        "record_path": record_path,
        "conversation_context": "BREQ-20260617-101010-fix-truncation",
        "requested_by": "tg:643108092",
        "title": "Fix message truncation in Chief Engineer comms",
        "summary": "Replies are cut at 4000 chars; split long messages instead.",
    }
    m.update(over)
    return m


class FakeClient:
    """Models the single inbox row with a mutable status, honouring the status
    filter so _claim's conditional update can be exercised."""

    def __init__(self, rows):
        self.rows = {r["request_id"]: dict(r) for r in rows}
        self.update_calls = []

    def select(self, table, columns="*", filters=None):
        out = list(self.rows.values())
        if filters:
            for key, val in filters.items():
                if key == "order":
                    continue
                want = val.split(".", 1)[1]  # "eq.<value>" -> "<value>"
                out = [r for r in out if str(r.get(key, "")) == want]
        return out

    def update(self, table, values, filters):
        self.update_calls.append((dict(values), dict(filters)))
        rid = filters["request_id"].split(".", 1)[1]
        row = self.rows.get(rid)
        if row is None:
            return []
        if "status" in filters:
            want = filters["status"].split(".", 1)[1]
            if row.get("status") != want:
                return []  # conditional update matched nothing (already claimed)
        row.update(values)
        return [dict(row)]


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = _REPO_ROOT / "core" / "coordination" / "tests" / "_tmp"
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.breq = self.tmp / "BREQ-20260617-101010-fix-truncation.md"
        self.breq.write_text(BREQ_BODY, encoding="utf-8")
        self.handoff_dir = self.tmp / "handoffs"
        self.handoff_dir.mkdir(exist_ok=True)
        self._orig_handoff_dir = ex._HANDOFF_DIR
        ex._HANDOFF_DIR = self.handoff_dir
        # 2026-08-29: individual tests below reassign ex._telegram_notify /
        # ex._run_sync_one directly (not via mock.patch), which used to
        # leak across tests since nothing restored them — a later test
        # (e.g. test_telegram_notify_uses_notification_service_...) would
        # silently call whatever the last test's stub left behind instead
        # of the real function. Saved here and restored in tearDown so
        # each test starts from the real implementations.
        self._orig_telegram_notify = ex._telegram_notify
        self._orig_run_sync_one = ex._run_sync_one
        self.notified = []

    def tearDown(self):
        ex._HANDOFF_DIR = self._orig_handoff_dir
        ex._telegram_notify = self._orig_telegram_notify
        ex._run_sync_one = self._orig_run_sync_one
        for p in sorted(self.tmp.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
        self.tmp.rmdir()

    # --- handoff generation ------------------------------------------------
    def test_handoff_is_pending_and_grounded(self):
        marker = _marker(str(self.breq))
        handoff = ex.build_handoff_from_breq(marker, self.breq)
        fields = _parse_handoff_file(handoff)
        self.assertIsNotNone(fields)
        # The two fields run_sync_one's _is_pending() checks:
        self.assertIn("APPROVED", (fields.get("status") or "").upper())
        self.assertIn(_normalise_token(fields.get("batch_status")), _PENDING_TOKENS)
        # Title + grounding sections survive for prompt_builder:
        self.assertEqual(
            fields.get("__mission_title__"),
            "Fix message truncation in Chief Engineer comms",
        )
        body = handoff.read_text(encoding="utf-8").lower()
        for sec in ("## summary", "## rationale", "## suggested next step", "## risks"):
            self.assertIn(sec, body)

    # --- claim / dedup -----------------------------------------------------
    def test_claim_is_single_winner(self):
        marker = _marker(str(self.breq))
        client = FakeClient([marker])
        self.assertTrue(ex._claim(client, marker["request_id"]))   # first wins
        self.assertFalse(ex._claim(client, marker["request_id"]))  # already running

    # --- happy path --------------------------------------------------------
    def test_process_marker_delivered_with_pr(self):
        marker = _marker(str(self.breq))
        client = FakeClient([marker])
        ex._run_sync_one = lambda p: {"status": "delivered", "pr_url": "https://x/pull/9", "artifact": "a.md"}
        ex._telegram_notify = lambda chat, text: self.notified.append((chat, text))

        res = ex.process_marker(client, marker)

        self.assertEqual(res["status"], "delivered")
        self.assertEqual(res["pr_url"], "https://x/pull/9")
        # row ended DELIVERED, and the chat got the PR link
        self.assertEqual(client.rows[marker["request_id"]]["status"], ex.STATUS_DELIVERED)
        self.assertTrue(self.notified)
        self.assertIn("pull/9", self.notified[-1][1])

    def test_process_marker_skips_when_already_claimed(self):
        marker = _marker(str(self.breq), status=ex.STATUS_RUNNING)
        client = FakeClient([marker])
        ex._telegram_notify = lambda chat, text: self.notified.append((chat, text))
        res = ex.process_marker(client, marker)
        self.assertEqual(res["status"], "skipped")
        self.assertFalse(self.notified)

    def test_process_marker_missing_breq_fails_gracefully(self):
        marker = _marker(str(self.tmp / "does-not-exist.md"), conversation_context="nope")
        client = FakeClient([marker])
        ex._telegram_notify = lambda chat, text: self.notified.append((chat, text))
        res = ex.process_marker(client, marker)
        self.assertEqual(res["status"], "failed")
        self.assertEqual(client.rows[marker["request_id"]]["status"], ex.STATUS_FAILED)

    def test_parse_chat_id(self):
        self.assertEqual(ex._parse_chat_id({"requested_by": "tg:643108092"}), "643108092")
        self.assertIsNone(ex._parse_chat_id({"requested_by": "@someone"}))

    def test_telegram_notify_uses_notification_service_with_request_chat_id(self):
        """2026-08-29: migrated off a private sendMessage call onto
        core/platform/notification_service.py's notify(). This build
        executor's chat_id is per-request (whoever triggered the build),
        not the module's env-resolved default — confirms notify()'s
        chat_id override actually reaches the sender, not the default."""
        import os
        from unittest.mock import patch
        import core.platform.notification_service as ns

        calls = []

        def fake_telegram(text, reply_markup=None, chat_id=None):
            calls.append({"text": text, "chat_id": chat_id})
            return True, None, 42

        real_sender = ns._SENDERS[ns.Transport.TELEGRAM]
        ns._SENDERS[ns.Transport.TELEGRAM] = fake_telegram
        try:
            with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "fake-token"}):
                ex._telegram_notify("999888777", "build finished")
        finally:
            ns._SENDERS[ns.Transport.TELEGRAM] = real_sender

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["chat_id"], "999888777")
        self.assertIn("build finished", calls[0]["text"])

    def test_telegram_notify_skips_when_chat_id_absent(self):
        import core.platform.notification_service as ns

        calls = []
        real_sender = ns._SENDERS[ns.Transport.TELEGRAM]
        ns._SENDERS[ns.Transport.TELEGRAM] = lambda *a, **k: calls.append(1) or (True, None, None)
        try:
            ex._telegram_notify(None, "should not send")
        finally:
            ns._SENDERS[ns.Transport.TELEGRAM] = real_sender

        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
