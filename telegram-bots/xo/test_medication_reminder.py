"""Daily medication reminder (medication_reminder.py): 07:00 first
reminder, repeat every 15 min until confirmed, 22:00 hard stop, and the
confirmation paths (button / command / plain text)."""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

meds = pytest.importorskip("telegram_bots.xo.medication_reminder")


@pytest.fixture(autouse=True)
def _tmp_state(tmp_path, monkeypatch):
    state = tmp_path / "state.json"
    monkeypatch.setattr(meds, "STATE_PATH", state)
    # default args were bound at import time — rebind to the temp file
    for fn in ("_load_state", "_save_state", "is_confirmed", "mark_confirmed", "is_outstanding"):
        f = getattr(meds, fn)
        defaults = list(f.__defaults__)
        defaults[-1] = state
        monkeypatch.setattr(f, "__defaults__", tuple(defaults))
    return state


def _at(h, m=0):
    return datetime(2026, 9, 24, h, m, tzinfo=meds.TZ)


# ── window / state ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("h,m,expected", [
    (6, 59, False), (7, 0, True), (13, 30, True), (21, 59, True), (22, 0, False), (23, 30, False),
])
def test_outstanding_window(h, m, expected):
    assert meds.is_outstanding(_at(h, m)) is expected


def test_confirmation_stops_outstanding_for_that_day_only():
    meds.mark_confirmed(_at(8).date())
    assert meds.is_outstanding(_at(9)) is False
    assert meds.is_outstanding(_at(9) + timedelta(days=1)) is True


def test_corrupt_state_file_is_treated_as_unconfirmed(_tmp_state):
    _tmp_state.write_text("{not json")
    assert meds.is_outstanding(_at(9)) is True


# ── natural-language confirmation ────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "taken", "Taken!", "done", "took them", "I've taken them", "ive taken my meds",
    "just took my medicines", "had my tablets", "meds taken", "Already had them",
])
def test_confirmation_phrases(text):
    assert meds.is_confirmation_text(text)


@pytest.mark.parametrize("text", [
    "what's my capacity today", "I haven't finished the report", "remind me tomorrow",
    "done with the brief, what's next?", "taken over by events",
])
def test_non_confirmation_phrases(text):
    assert not meds.is_confirmation_text(text)


def test_reminder_text_counts():
    assert "time to take your medicines" in meds.reminder_text(1)
    assert "Reminder #3" in meds.reminder_text(3)


# ── real JobQueue: 15-min repeat, stop on confirm ────────────────────────────

def test_nag_repeats_until_confirmed(monkeypatch):
    from telegram.ext import Application

    monkeypatch.setattr(meds, "INTERVAL_MINUTES", 0.001)  # ~60ms so the test runs quickly
    monkeypatch.setattr(meds, "is_outstanding", lambda now=None, path=None: not meds.is_confirmed(meds.today()))

    async def run():
        app = Application.builder().token("123:test").build()
        bot = MagicMock()
        bot.send_message = AsyncMock()
        jq = app.job_queue
        jq.set_application(app)
        # route the job context's bot to our mock
        monkeypatch.setattr(type(app), "bot", property(lambda self: bot))
        await jq.start()
        try:
            await meds.resume_if_due(bot, jq, 42)
            assert bot.send_message.await_count == 1
            await asyncio.sleep(0.35)
            sent_before = bot.send_message.await_count
            assert sent_before >= 3, sent_before
            assert "Reminder #2" in bot.send_message.await_args_list[1].args[1]

            meds.confirm(jq)
            await asyncio.sleep(0.2)
            assert bot.send_message.await_count == sent_before
            assert not jq.get_jobs_by_name(meds.NAG_JOB_NAME)
        finally:
            await jq.stop(wait=False)

    asyncio.run(run())


def test_schedule_registers_0700_brisbane_daily_job():
    jq = MagicMock()
    meds.schedule(jq, 42)
    kwargs = jq.run_daily.call_args.kwargs
    assert kwargs["time"].hour == 7 and kwargs["time"].minute == 0
    assert kwargs["time"].tzinfo == meds.TZ
    assert kwargs["chat_id"] == 42


def test_daily_job_skips_if_already_confirmed():
    meds.mark_confirmed(meds.today())
    ctx = MagicMock()
    ctx.bot.send_message = AsyncMock()
    asyncio.run(meds._job_daily(ctx))
    ctx.bot.send_message.assert_not_awaited()
    ctx.job_queue.run_repeating.assert_not_called()
