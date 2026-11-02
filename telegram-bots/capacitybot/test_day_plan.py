"""The day plan (step 2): reasons, the per-zone prompt, and suggestions tagged with levers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from telegram_bots.capacitybot.day_plan import (
    MAX_SUGGESTIONS,
    ZONE_PROMPT,
    day_reasons,
    render_day_plan,
)

SUGGESTIONS = [
    {"title": "Take a quiet 10 minutes", "management_lever": "recover", "estimated_minutes": 10},
    {"title": "Drop one commitment today", "management_lever": "reduce_load"},
    {"title": "Put on calming music", "management_lever": "regulate", "estimated_minutes": 5},
    {"title": "Rework tomorrow's schedule", "management_lever": "redesign"},
]


def test_reasons_come_from_the_whole_check_in_not_just_the_zone():
    row = {
        "capacity_state": "orange", "pain_state": "elevated", "executive_function": "strained",
        "compensation_load": "high", "regulation_state": "activated", "stimulation_state": "high",
    }
    reasons = day_reasons(row)
    assert len(reasons) == 5
    assert "pain is above your usual" in reasons


def test_missing_or_fine_answers_are_never_listed_as_problems():
    assert day_reasons({"capacity_state": "green", "pain_state": "baseline", "executive_function": "good"}) == []
    assert day_reasons({"capacity_state": "green"}) == []


def test_recent_borrowing_is_mentioned_only_when_there_was_some():
    assert day_reasons({}, recent_debt=(2, 3)) == ["you marked borrowing capacity on 2 of your last 3 evenings"]
    assert day_reasons({}, recent_debt=(0, 3)) == []
    assert day_reasons({}, recent_debt=(0, 0)) == []
    assert day_reasons({}, recent_debt=None) == []


def test_each_zone_gets_its_own_prompt():
    for zone in ("green", "orange", "red"):
        assert ZONE_PROMPT[zone] in render_day_plan({"capacity_state": zone})


def test_orange_asks_the_early_intervention_question():
    plan = render_day_plan({"capacity_state": "orange"})
    assert "reduce, regulate or change before this becomes red" in plan


def test_green_banks_capacity_and_red_is_the_smallest_workable_day():
    assert "Spend some, bank some" in render_day_plan({"capacity_state": "green"})
    red = render_day_plan({"capacity_state": "red"})
    assert "smallest workable day" in red and "Nothing else is held back" in red


def test_at_most_three_suggestions_each_tagged_with_its_lever():
    plan = render_day_plan({"capacity_state": "orange"}, SUGGESTIONS)
    assert MAX_SUGGESTIONS == 3
    assert "1. Take a quiet 10 minutes (Recover, 10 min)" in plan
    assert "2. Drop one commitment today (Reduce)" in plan
    assert "3. Put on calming music (Regulate, 5 min)" in plan
    assert "Rework tomorrow's schedule" not in plan


def test_no_capacity_answer_means_no_plan():
    assert render_day_plan({}) == "" and render_day_plan({"capacity_state": None}) == ""


def test_plan_never_uses_gate_or_pressure_wording():
    for zone in ("green", "orange", "red"):
        plan = render_day_plan({"capacity_state": zone, "pain_state": "high"}, SUGGESTIONS).lower()
        for word in ("should", "must", "deferred", "blocked", "limit", "not allowed", "you need to"):
            assert word not in plan, (zone, word)


def _wired(row, interventions=None, recent=None, fail=False):
    """Run the cp callback with a mocked database and return the text the Captain sees."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from telegram_bots.capacitybot import app

    q = MagicMock(data="ct|id=42|cp=m")
    q.answer = AsyncMock()
    q.edit_message_text = AsyncMock()
    update = MagicMock(callback_query=q)
    rank = AsyncMock(side_effect=RuntimeError("boom")) if fail else AsyncMock(return_value=interventions or [])
    with patch.object(app, "_get_supabase", return_value=MagicMock()), \
         patch.object(app.ct, "write_quick_checkin", AsyncMock(return_value=(True, row, None))), \
         patch.object(app.ct, "fetch_checkin", AsyncMock(return_value=row)), \
         patch.object(app.ct, "fetch_recent", AsyncMock(return_value=recent or [])), \
         patch.object(app.ie, "rank_interventions", rank):
        asyncio.run(app.handle_capacity_callback(update, MagicMock()))
    return q.edit_message_text.call_args[0][0]


def test_quick_check_in_ends_with_the_summary_then_the_plan():
    row = {"id": 42, "capacity_state": "orange", "pain_state": "elevated", "compensation_load": "moderate"}
    text = _wired(row, SUGGESTIONS, recent=[
        {"checkin_type": "evening", "capacity_debt": "yes"},
        {"checkin_type": "evening", "capacity_debt": "no"},
    ])
    assert text.index("MY CAPACITY TODAY") < text.index("TODAY'S PLAN")
    assert "pain is above your usual" in text
    assert "1 of your last 2 evenings" in text
    assert "(Recover, 10 min)" in text


def test_a_failing_plan_never_loses_the_summary():
    row = {"id": 42, "capacity_state": "red"}
    text = _wired(row, fail=True)
    assert "MY CAPACITY TODAY" in text and "Capacity:" in text
