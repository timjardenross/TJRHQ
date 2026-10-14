"""R2 alignment, Phase 2 step 2: the 0-10 pain question is gone from the
CapacityBot check-in. The flow, summary, skip ("Done for now") logic and the
intervention snapshot must all still work, and no numeric pain is written."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parents[2]))

import telegram_bots.capacitybot.app as app_module
from telegram_bots.capacitybot import capacity_today as ct
from telegram_bots.capacitybot import intervention_engine as ie
from telegram_bots.capacitybot.app import handle_capacity_callback


def _cb(data: str):
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.data = data
    update = MagicMock()
    update.callback_query = query
    update.effective_chat.id = 1
    context = MagicMock()
    context.user_data = {}
    context.job_queue = MagicMock()
    return update, context, query


def _db():
    table = MagicMock()
    table.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": 7, "capacity_state": "green", "pain_state": "baseline"}])
    table.update.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": 7, "capacity_state": "green", "pain_state": "baseline"}])
    db = MagicMock()
    db.table.return_value = table
    return db, table


def test_pain_intensity_helpers_removed():
    assert not hasattr(ct, "q_pain_score")
    assert not hasattr(ct, "kb_pain_score")


def test_pain_state_question_is_kept():
    assert "usual baseline" in ct.q_pain()


def test_after_pain_state_the_flow_goes_straight_to_nervous_system():
    app_module._supabase = MagicMock()
    update, context, query = _cb("ct|c=g|t=b|p=l")
    asyncio.run(handle_capacity_callback(update, context))
    text = query.edit_message_text.call_args[0][0]
    assert "0=none" not in text and "intensity" not in text.lower()
    assert text == ct.q_regulation()
    kb = query.edit_message_text.call_args[1]["reply_markup"]
    assert kb.inline_keyboard[0][0].callback_data.startswith("ct|c=g|t=b|p=l|r=")
    assert not any("ps=" in b.callback_data for row in kb.inline_keyboard for b in row)
    app_module._supabase = None


def test_old_in_flight_ps_button_still_continues_and_is_not_stored():
    app_module._supabase = MagicMock()
    update, context, query = _cb("ct|c=g|t=b|p=l|ps=5")
    asyncio.run(handle_capacity_callback(update, context))
    assert query.edit_message_text.call_args[0][0] == ct.q_regulation()
    app_module._supabase = None


def test_chain_after_regulation_is_unchanged():
    app_module._supabase = MagicMock()
    update, context, query = _cb("ct|c=g|t=b|p=l|r=s")
    asyncio.run(handle_capacity_callback(update, context))
    assert "emotional load" in query.edit_message_text.call_args[0][0].lower()
    app_module._supabase = None


def test_done_for_now_on_the_pain_screen_saves_a_partial_check_in_without_numeric_pain():
    db, table = _db()
    app_module._supabase = db
    update, context, query = _cb("ct|c=g|t=b|p=b|done=1")
    asyncio.run(handle_capacity_callback(update, context))
    payload = table.insert.call_args[0][0]
    assert payload["pain_state"] == "baseline"
    assert "pain_score" not in payload
    summary = query.edit_message_text.call_args[0][0]
    assert "Pain:" in summary and "Around usual" in summary and "/10" not in summary
    assert "Saved" in summary
    app_module._supabase = None


def test_old_ps_value_is_never_written():
    db, table = _db()
    asyncio.run(ct.write_quick_checkin(db, {"c": "g", "t": "b", "p": "e", "ps": "8"}))
    payload = table.insert.call_args[0][0]
    assert payload["pain_state"] == "elevated"
    assert "pain_score" not in payload


def test_summary_without_any_pain_value_does_not_mention_pain():
    text = ct.render_summary({"capacity_state": "green"})
    assert "Pain" not in text and "/10" not in text


def test_summary_with_a_legacy_row_does_not_print_the_number():
    text = ct.render_summary({"capacity_state": "green", "pain_state": "high", "pain_score": 9})
    assert "Much higher than usual" in text and "/10" not in text and "9" not in text.replace("Much", "")


def test_intervention_snapshot_has_no_numeric_pain_and_handles_missing_value():
    db, table = _db()
    asyncio.run(ie.create_event(db, source="capacity_q9", intervention_id="rest_20",
                                pain_before=None, capacity_before="green"))
    payload = table.insert.call_args[0][0]
    assert "pain_score_before" not in payload
    assert payload["pain_before"] is None
    asyncio.run(ie.create_event(db, source="capacity_q9", intervention_id="rest_20", pain_before="elevated"))
    assert table.insert.call_args[0][0]["pain_before"] == "elevated"


def test_q9_acceptance_snapshot_passes_pain_state_only():
    db, table = _db()
    row = {"id": 7, "capacity_state": "green", "pain_state": "baseline", "pain_score": 6}
    table.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[row])
    created = {}

    async def fake_get(_db, _id):
        return {"id": "rest_20", "requires_followup": False}

    async def fake_create(_db, **kw):
        created.update(kw)
        return True, {"id": 1}, None

    orig_get, orig_create = ie.get_intervention, ie.create_event
    ie.get_intervention, ie.create_event = fake_get, fake_create
    try:
        app_module._supabase = db
        update, context, _query = _cb("ct|id=7|act=rest_20")
        asyncio.run(handle_capacity_callback(update, context))
    finally:
        ie.get_intervention, ie.create_event = orig_get, orig_create
        app_module._supabase = None
    assert created.get("pain_before") == "baseline"
    assert "pain_score_before" not in created
