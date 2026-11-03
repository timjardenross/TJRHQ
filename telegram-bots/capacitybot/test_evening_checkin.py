"""Evening reflection: whole-day compensation + "was today a good day?" (migration 0247)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))
for _k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SUPABASE_URL", "SUPABASE_KEY"):
    os.environ.setdefault(_k, "test")

from core.health.good_day import provisional_good_day
from telegram_bots.capacitybot import capacity_today as ct


def _callbacks(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def test_every_evening_callback_fits_telegrams_64_byte_limit():
    f = {"dt": "s", "cp": "e", "hf": "12"}
    for kb in (ct.kb_evening_compensation(f), ct.kb_evening_helpful(f), ct.kb_evening_good_day(f)):
        assert all(len(c.encode()) <= 64 for c in _callbacks(kb))


def test_each_step_carries_the_answers_so_far_in_order():
    f = {"dt": "s", "cp": "m", "hf": "3"}
    assert all(c.startswith("cte|dt=s|cp=m|hf=3|gd=") for c in _callbacks(ct.kb_evening_good_day(f)))
    assert all(c.startswith("cte|dt=s|cp=m|hf=") for c in _callbacks(ct.kb_evening_helpful(f)))
    assert all(c.startswith("cte|dt=s|cp=") for c in _callbacks(ct.kb_evening_compensation(f)))


def test_compensation_and_good_day_are_skippable():
    assert any(c.endswith("cp=x") for c in _callbacks(ct.kb_evening_compensation({"dt": "s"})))
    assert any(c.endswith("gd=x") for c in _callbacks(ct.kb_evening_good_day({"dt": "s"})))
    assert "Skip" in ct.q_evening_compensation() and "Skip" in ct.q_evening_good_day()


def _write(f):
    db = MagicMock()
    import asyncio

    saved, err = asyncio.run(ct.write_evening(db, f))
    assert saved and err is None
    return db.table.return_value.insert.call_args[0][0]


def test_answers_are_stored_in_the_evening_only_columns():
    p = _write({"dt": "s", "cp": "m", "hf": "0", "gd": "k"})
    assert p["day_compensation_load"] == "moderate" and p["good_day"] == "kind_of"
    assert p["checkin_type"] == "evening"
    assert "capacity_debt" not in p  # borrowed capacity is no longer asked or stored
    assert "compensation_load" not in p  # the start-of-day column is never written by the evening flow


def test_skipped_answers_store_nothing():
    p = _write({"dt": "d", "cp": "x", "hf": "0", "gd": "x"})
    assert "day_compensation_load" not in p and "good_day" not in p


def test_good_day_rule_judges_only_what_was_answered():
    assert provisional_good_day({"day_trajectory": "same", "day_compensation_load": "moderate"}) is True
    assert provisional_good_day({"day_trajectory": "same"}) is True  # missing compensation != bad
    assert provisional_good_day({"day_trajectory": "declined"}) is False
    assert provisional_good_day({"day_trajectory": "same", "day_compensation_load": "extreme"}) is False
    assert provisional_good_day({}) is None and provisional_good_day(None) is None


def test_borrowed_capacity_is_not_part_of_the_rule():
    """Captain's call 2026-11-03: yes / maybe / no on borrowing must not change the verdict."""
    base = {"day_trajectory": "same", "day_compensation_load": "moderate"}
    for debt in ("no", "maybe", "yes", None):
        assert provisional_good_day({**base, "capacity_debt": debt}) is True


def test_the_captains_own_answer_wins_over_the_rule():
    bad_on_paper = {"day_trajectory": "declined", "day_compensation_load": "extreme"}
    assert provisional_good_day({**bad_on_paper, "good_day": "yes"}) is True
    good_on_paper = {"day_trajectory": "same", "day_compensation_load": "low"}
    assert provisional_good_day({**good_on_paper, "good_day": "no"}) is False
    assert provisional_good_day({**good_on_paper, "good_day": "kind_of"}) is True  # falls through to the rule


@pytest.mark.parametrize("data,expect_text", [
    ("cte|dt=s", "push, mask"),
    ("cte|dt=s|cp=m", "What helped most"),
    ("cte|dt=s|cp=m|hf=1", "good day"),
    ("cte|dt=s|cp=m|hf=1|cd=n", "good day"),  # old button from before the question was dropped
])
def test_handler_walks_the_questions_in_order(data, expect_text):
    import asyncio
    from unittest.mock import AsyncMock

    from telegram_bots.capacitybot import app

    q = MagicMock(data=data)
    q.answer = AsyncMock()
    q.edit_message_text = AsyncMock()
    update = MagicMock(callback_query=q)
    asyncio.run(app.handle_capacity_evening_callback(update, MagicMock()))
    assert expect_text in q.edit_message_text.call_args[0][0]


def test_handler_saves_after_the_good_day_answer():
    import asyncio
    from unittest.mock import AsyncMock, patch

    from telegram_bots.capacitybot import app

    db = MagicMock()
    q = MagicMock(data="cte|dt=s|cp=m|hf=1|cd=n|gd=y")
    q.answer = AsyncMock()
    q.edit_message_text = AsyncMock()
    with patch.object(app, "_get_supabase", return_value=db):
        asyncio.run(app.handle_capacity_evening_callback(MagicMock(callback_query=q), MagicMock()))
    payload = db.table.return_value.insert.call_args[0][0]
    assert payload["good_day"] == "yes" and payload["day_compensation_load"] == "moderate"
    assert "saved" in q.edit_message_text.call_args[0][0].lower()


def test_morning_push_asks_the_cpap_question_on_the_first_check_in():
    """The 08:00 push must use the CPAP question; it used to call the removed sleep functions."""
    import asyncio
    from unittest.mock import AsyncMock, patch

    from telegram_bots.capacitybot import app

    context = MagicMock()
    context.bot.send_message = AsyncMock()
    with patch.object(app, "_get_supabase", return_value=MagicMock()), \
         patch.object(app.ct, "fetch_recent", AsyncMock(return_value=[])):
        asyncio.run(app._job_morning_push(context))
    text = context.bot.send_message.call_args[0][1]
    assert "CPAP" in text


# ── Good-day counts in the summaries ────────────────────────────────────────

def _evening(day, **kw):
    return {"checkin_type": "evening", "log_date": day, "captured_at": f"{day}T20:00:00", **kw}


GOOD = {"day_trajectory": "same", "day_compensation_load": "low"}
BAD = {"day_trajectory": "declined"}


def test_counts_good_days_and_the_longest_consecutive_run():
    from core.health.good_day import summarize_good_days

    rows = [
        _evening("2026-11-01", **GOOD), _evening("2026-11-02", **GOOD), _evening("2026-11-03", **GOOD),
        _evening("2026-11-04", **BAD),
        _evening("2026-11-05", **GOOD),
    ]
    assert summarize_good_days(rows) == {"judged": 5, "good": 4, "longest_run": 3}


def test_a_day_with_no_evening_ends_a_run_and_is_not_counted():
    from core.health.good_day import summarize_good_days

    rows = [_evening("2026-11-01", **GOOD), _evening("2026-11-03", **GOOD)]  # the 2nd has no row
    assert summarize_good_days(rows) == {"judged": 2, "good": 2, "longest_run": 1}


def test_the_latest_evening_of_a_day_is_used_and_other_rows_are_ignored():
    from core.health.good_day import summarize_good_days

    rows = [
        _evening("2026-11-01", **BAD),
        {**_evening("2026-11-01", **GOOD), "captured_at": "2026-11-01T22:00:00"},
        {"checkin_type": "capacity", "log_date": "2026-11-02", "capacity_state": "green"},
        _evening("2026-11-03"),  # nothing answered: no verdict
    ]
    assert summarize_good_days(rows) == {"judged": 1, "good": 1, "longest_run": 1}
    assert summarize_good_days([]) == {"judged": 0, "good": 0, "longest_run": 0}


def test_the_summary_line_and_its_absence():
    rows = [_evening("2026-11-01", **GOOD), _evening("2026-11-02", **BAD)]
    assert ct.good_day_line(rows) == "Good days: 1 of 2 evenings (longest run: 1 day)"
    assert ct.good_day_line([_evening("2026-11-01", **GOOD), _evening("2026-11-02", **GOOD)]).endswith("(longest run: 2 days)")
    assert ct.good_day_line([]) is None
    assert ct.good_day_line([{"checkin_type": "capacity", "log_date": "2026-11-01"}]) is None


def test_week_month_and_therapy_summaries_show_the_count():
    rows = [
        {"checkin_type": "capacity", "log_date": "2026-11-01", "capacity_state": "orange"},
        _evening("2026-11-01", **GOOD),
        _evening("2026-11-02", **BAD),
    ]
    assert "Good days: 1 of 2 evenings" in ct.render_trend_summary(rows, "This week")
    assert "Good days: 1 of 2 evenings" in ct.render_therapy_summary(rows, 2)
