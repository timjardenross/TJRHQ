"""
Mission 3 — Telegram plain-text capture-ingress normalisation.

Before this mission, cmd_message's NL-capture branch wrote straight into
personal_tasks — a second capture path that bypassed captured_items and
its enrichment/classification pipeline entirely (the "two competing
intake behaviours" discovery finding). These tests prove the
replacement: the same trigger phrase now persists into captured_items
(like voice/portal/the /note command), leaves classification undecided
for enrichment to determine, and the immediate Telegram reply is an
honest capture acknowledgement — never a "task created" claim, since no
personal_task exists synchronously.

Approved instruction (explicit): do NOT add a Telegram-local
actionability classifier here. parse_capture_intent's regex is used only
to decide "is this new information worth capturing" (vs. falling through
to ordinary chat) and to extract a title/temporal hint for the reply and
provenance — it must never set `classification` on the captured_items
row. That decision belongs to enrichment_worker.py alone.

Run from repo root:
    telegram-bots/xo/.venv/bin/python telegram-bots/xo/test_nl_capture_ingress.py

Matches this directory's existing hand-rolled PASS/FAIL harness
(test_voice_capture.py) — no pytest or pytest-asyncio in this bot's venv.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "12345")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from telegram_bots.xo import app

PASS = "PASS"
FAIL = "FAIL"
_results: list[tuple[str, str]] = []


def check(label: str, condition: bool) -> bool:
    tag = PASS if condition else FAIL
    _results.append((tag, label))
    print(f"  [{tag}] {label}")
    return condition


def _run(coro):
    return asyncio.run(coro)


def _make_update(text: str):
    update = MagicMock()
    update.message.text = text
    update.message.reply_to_message = None
    update.message.message_id = 42
    update.message.reply_text = AsyncMock()
    update.effective_chat.id = 12345
    return update


class _FakeTable:
    def __init__(self, recorder: dict):
        self._recorder = recorder

    def insert(self, row):
        self._recorder["inserted"] = row
        result = MagicMock()
        result.execute = MagicMock(return_value=MagicMock(data=[]))
        return result


class _FakeDB:
    def __init__(self, recorder: dict):
        self._recorder = recorder

    def table(self, name):
        self._recorder["table"] = name
        return _FakeTable(self._recorder)


def test_nl_capture_writes_to_captured_items_not_personal_tasks():
    print("\n── NL capture routes to captured_items ──────────────────────────")
    recorder: dict = {}
    update = _make_update("remind me to send the specialist referral")
    with patch.object(app, "_get_supabase", return_value=_FakeDB(recorder)):
        _run(app.cmd_message(update, MagicMock()))
    check("writes to captured_items, not personal_tasks", recorder.get("table") == "captured_items")


def test_nl_capture_leaves_classification_undetermined():
    print("\n── NL capture never classifies ──────────────────────────────────")
    recorder: dict = {}
    update = _make_update("remind me to send the specialist referral")
    with patch.object(app, "_get_supabase", return_value=_FakeDB(recorder)):
        _run(app.cmd_message(update, MagicMock()))
    row = recorder["inserted"]
    check("no classification field set on the captured_items row", "classification" not in row)
    check("processing_status is pending (awaiting enrichment)", row.get("processing_status") == "pending")


def test_nl_capture_reply_does_not_claim_task_created():
    print("\n── Instant ack is honest, not a task-created claim ──────────────")
    update = _make_update("remind me to send the specialist referral")
    with patch.object(app, "_get_supabase", return_value=_FakeDB({})):
        _run(app.cmd_message(update, MagicMock()))
    reply_text = update.message.reply_text.call_args[0][0].lower()
    check("reply does not say 'task created'", "task created" not in reply_text)
    check("reply does not say 'added to life admin'", "added to life admin" not in reply_text)
    check("reply says 'got it' (capture-only ack)", "got it" in reply_text)


def test_temporal_intent_preserved_as_summary_hint():
    print("\n── Temporal intent survives the captured_items bridge ───────────")
    recorder: dict = {}
    update = _make_update("remind me tomorrow to call the plumber")
    with patch.object(app, "_get_supabase", return_value=_FakeDB(recorder)):
        _run(app.cmd_message(update, MagicMock()))
    row = recorder["inserted"]
    summary = row.get("summary") or {}
    check("summary.parse_source == telegram_nl_capture", summary.get("parse_source") == "telegram_nl_capture")
    check("summary.parsed_due_date is set", summary.get("parsed_due_date") is not None)


def test_insert_failure_gives_honest_error_not_false_ack():
    print("\n── Insert failure never gives a false ack ───────────────────────")
    update = _make_update("remind me to send the specialist referral")
    with patch.object(app, "_get_supabase", return_value=_FakeDB({})), \
         patch.object(_FakeTable, "insert", side_effect=RuntimeError("boom")):
        _run(app.cmd_message(update, MagicMock()))
    reply_text = update.message.reply_text.call_args[0][0]
    check("failure reply signals an error, not success", "couldn't save" in reply_text.lower() or "⚠️" in reply_text)


def test_non_capture_message_does_not_touch_captured_items():
    print("\n── Non-capture chat message is not filed as a capture ───────────")
    recorder: dict = {}
    update = _make_update("how's the weather today")
    with patch.object(app, "_get_supabase", return_value=_FakeDB(recorder)), \
         patch("telegram_bots.xo.debrief_engine.route_debrief_interaction",
               new=AsyncMock(return_value={"handled": False})), \
         patch.object(app, "get_recovery_status", return_value=None), \
         patch.object(app, "get_wellness_snapshot", return_value=None), \
         patch.object(app, "_get_open_missions", return_value=[]), \
         patch.object(app, "_get_recent_turns", return_value=[]), \
         patch.object(app, "_log_conversation_turn"), \
         patch.object(app, "generate_async", new=AsyncMock(return_value=None)):
        _run(app.cmd_message(update, MagicMock()))
    check("plain chat never writes to captured_items", recorder.get("table") != "captured_items")


def main():
    test_nl_capture_writes_to_captured_items_not_personal_tasks()
    test_nl_capture_leaves_classification_undetermined()
    test_nl_capture_reply_does_not_claim_task_created()
    test_temporal_intent_preserved_as_summary_hint()
    test_insert_failure_gives_honest_error_not_false_ack()
    test_non_capture_message_does_not_touch_captured_items()

    passed = sum(1 for tag, _ in _results if tag == PASS)
    total = len(_results)
    failed = [label for tag, label in _results if tag == FAIL]

    print(f"\n{'=' * 60}")
    print(f"{passed}/{total} tests passed")
    if failed:
        print("FAILED:")
        for f in failed:
            print(f"  ✗ {f}")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
