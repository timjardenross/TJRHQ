"""
Tests for /experiment — V3 Mission 4: Personal Experiment Engine.

Covers experiments.py's pure rendering/parsing functions and app.py's
handler wiring (menu -> propose (free text via cmd_message + buttons) ->
save -> activate (with reminder scheduling) -> complete/stop), against a
mocked Supabase client — same style as test_helpme.py, the closest existing
analogue (propose/reassess shape).

Run from repo root:
    python telegram-bots/capacitybot/test_experiments.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parents[2]))

from telegram_bots.capacitybot.experiments import (
    TRIAL_WINDOW_PRESETS,
    kb_activate_reminder,
    kb_experiment_detail,
    kb_menu,
    parse_cb,
    render_experiment_detail,
    render_menu,
)

PASS = "PASS"
FAIL = "FAIL"
_results: list[tuple[str, str]] = []


def check(label: str, condition: bool) -> bool:
    tag = PASS if condition else FAIL
    _results.append((tag, label))
    print(f"  [{tag}] {label}")
    return condition


def _experiment(**overrides) -> dict:
    base = dict(
        id=1,
        hypothesis="Using a quieter work location may reduce post-work recovery cost.",
        target_condition=None,
        proposed_change="Use the quiet room before overload for two weeks.",
        baseline_window=None,
        trial_window=None,
        outcome_measures=[],
        status="proposed",
        result=None,
        confidence=None,
        notes=None,
        started_at=None,
        completed_at=None,
    )
    base.update(overrides)
    return base


# ── Pure rendering/parsing functions ─────────────────────────────────────────

def test_render_menu_empty_vs_populated():
    print("\n── render_menu — empty vs populated ──────────────────────────────")
    check("empty menu says no experiments", "No experiments" in render_menu([]))
    text = render_menu([_experiment(status="proposed"), _experiment(id=2, status="active")])
    check("proposed shows Worth testing label", "[Worth testing]" in text)
    check("active shows In progress label", "[In progress]" in text)


def test_kb_menu_has_propose_button_and_view_per_experiment():
    print("\n── kb_menu — view buttons + always a propose button ──────────────")
    kb = kb_menu([_experiment(id=5)])
    texts_and_cb = [(b.text, b.callback_data) for row in kb.inline_keyboard for b in row]
    check("view button for experiment 5", any(cb == "cx|a=view|id=5" for _t, cb in texts_and_cb))
    check("propose button present", any(cb == "cx|a=propose" for _t, cb in texts_and_cb))


def test_render_experiment_detail_includes_core_fields():
    print("\n── render_experiment_detail — hypothesis/change/status shown ─────")
    text = render_experiment_detail(_experiment(
        target_condition="Office auditory load",
        baseline_window="4 of 5 office afternoons reached Stretched or Depleted.",
        trial_window="2 weeks",
        outcome_measures=["3pm capacity", "sensory load"],
    ))
    check("hypothesis present", "Using a quieter work location" in text)
    check("proposed change present", "quiet room before overload" in text)
    check("target condition present", "Office auditory load" in text)
    check("baseline present", "4 of 5 office afternoons" in text)
    check("trial window present", "2 weeks" in text)
    check("outcome measures present", "3pm capacity" in text and "sensory load" in text)
    check("reversible/stoppable framing present, never a commitment",
          "stoppable" in text.lower() or "reversible" in text.lower())
    check("never framed as a medical treatment", "treatment" not in text.lower() or "not a treatment" in text.lower())


def test_kb_experiment_detail_status_specific_actions():
    print("\n── kb_experiment_detail — proposed vs active action buttons ──────")
    proposed_cbs = [b.callback_data for row in kb_experiment_detail(_experiment(id=9, status="proposed")).inline_keyboard for b in row]
    check("proposed offers activate", any("cx|a=activate|id=9" == cb for cb in proposed_cbs))
    check("proposed offers stop", any("cx|a=stop|id=9" == cb for cb in proposed_cbs))
    check("proposed does not offer complete", not any("a=complete" in cb for cb in proposed_cbs))

    active_cbs = [b.callback_data for row in kb_experiment_detail(_experiment(id=9, status="active")).inline_keyboard for b in row]
    check("active offers complete", any("cx|a=complete|id=9" == cb for cb in active_cbs))
    check("active offers stop", any("cx|a=stop|id=9" == cb for cb in active_cbs))

    completed_cbs = [b.callback_data for row in kb_experiment_detail(_experiment(id=9, status="completed")).inline_keyboard for b in row]
    check("completed offers no status-change actions, just Back",
          all("a=activate" not in cb and "a=complete" not in cb and "a=stop" not in cb for cb in completed_cbs))


def test_kb_activate_reminder_presets_map_to_days():
    print("\n── kb_activate_reminder — presets carry the right day counts ─────")
    kb = kb_activate_reminder(3)
    cbs = [b.callback_data for row in kb.inline_keyboard for b in row]
    for _code, _label, days in TRIAL_WINDOW_PRESETS:
        check(f"preset for {days} days present", f"cx|a=activate_confirm|id=3|d={days}" in cbs)
    check("no-reminder option present", "cx|a=activate_confirm|id=3|d=0" in cbs)


def test_parse_cb_experiment_fields():
    print("\n── parse_cb — cx| action + id + extra fields ──────────────────────")
    f = parse_cb("cx|a=activate_confirm|id=7|d=14")
    check("action parsed", f.get("a") == "activate_confirm")
    check("id parsed", f.get("id") == "7")
    check("days parsed", f.get("d") == "14")


# ── Wiring — app.py handlers against a mocked Supabase client ───────────────

def _make_db(experiments=None):
    db = MagicMock()
    _table_mocks: dict[str, MagicMock] = {}

    def table_side_effect(name):
        if name in _table_mocks:
            return _table_mocks[name]
        t = MagicMock()
        if name == "capacity_experiments":
            sel = MagicMock()
            sel.in_.return_value.order.return_value.execute.return_value = MagicMock(data=experiments or [])
            sel.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=experiments or [])
            t.select.return_value = sel
            t.insert.return_value.execute.return_value = MagicMock(data=[{**_experiment(), "id": 42}])
            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
        _table_mocks[name] = t
        return t

    db.table.side_effect = table_side_effect
    return db


def _make_update_and_context(callback_data: str | None = None, text: str | None = None):
    context = MagicMock()
    context.user_data = {}
    context.job_queue = MagicMock()
    context.bot.send_message = AsyncMock()

    if callback_data is not None:
        query = MagicMock()
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        query.data = callback_data
        update = MagicMock()
        update.callback_query = query
        update.effective_chat.id = 12345
        return update, context, query

    update = MagicMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.effective_chat.id = 12345
    return update, context, None


def test_cmd_experiment_clears_stale_state_and_shows_menu():
    print("\n── cmd_experiment — clears stale flow state, shows menu ──────────")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import cmd_experiment

    app_module._supabase = _make_db(experiments=[])
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {"experiment_stage": "hypothesis", "experiment_draft": {"stale": True}}

    asyncio.run(cmd_experiment(update, context))

    check("replied with the menu", update.message.reply_text.called)
    check("stale flow state cleared", "experiment_stage" not in context.user_data and "experiment_draft" not in context.user_data)
    app_module._supabase = None


def test_propose_flow_hypothesis_then_change_then_save_now():
    print("\n── propose flow — hypothesis -> change -> Save now ────────────────")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_experiment_callback, cmd_message

    app_module._supabase = _make_db()

    # tap "Propose new"
    update, context, query = _make_update_and_context(callback_data="cx|a=propose")
    asyncio.run(handle_experiment_callback(update, context))
    check("propose sets hypothesis stage", context.user_data.get("experiment_stage") == "hypothesis")

    # reply with hypothesis text
    update, context2, _ = _make_update_and_context(text="Quiet room helps in the afternoon")
    context2.user_data["experiment_stage"] = "hypothesis"
    asyncio.run(cmd_message(update, context2))
    check("hypothesis saved to draft", context2.user_data["experiment_draft"]["hypothesis"] == "Quiet room helps in the afternoon")
    check("advances to proposed_change stage", context2.user_data.get("experiment_stage") == "proposed_change")

    # reply with proposed_change text
    context2.user_data["experiment_stage"] = "proposed_change"
    update2, _, _ = _make_update_and_context(text="Move to the quiet room before 2pm")
    asyncio.run(cmd_message(update2, context2))
    check("proposed_change saved to draft", context2.user_data["experiment_draft"]["proposed_change"] == "Move to the quiet room before 2pm")
    check("stage cleared after minimal fields collected", "experiment_stage" not in context2.user_data)

    # tap "Save now"
    update3, context2b, query3 = _make_update_and_context(callback_data="cx|a=save_now")
    context2b.user_data["experiment_draft"] = context2.user_data["experiment_draft"]
    asyncio.run(handle_experiment_callback(update3, context2b))
    db = app_module._supabase
    check("experiment inserted", db.table("capacity_experiments").insert.called)
    payload = db.table("capacity_experiments").insert.call_args[0][0]
    check("hypothesis carried through", payload["hypothesis"] == "Quiet room helps in the afternoon")
    check("status is proposed", payload["status"] == "proposed")
    check("draft cleared after save", "experiment_draft" not in context2b.user_data)
    app_module._supabase = None


def test_add_details_branch_walks_through_optional_fields():
    print("\n── propose flow — add details -> baseline -> trial preset -> measures ─")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_experiment_callback, cmd_message

    app_module._supabase = _make_db()
    context = MagicMock()
    context.user_data = {"experiment_draft": {"hypothesis": "H", "proposed_change": "C"}}
    context.job_queue = MagicMock()

    # add_details -> target_condition stage
    update, _, query = _make_update_and_context(callback_data="cx|a=add_details")
    update_ctx = context
    asyncio.run(handle_experiment_callback(update, update_ctx))
    check("moves to target_condition stage", update_ctx.user_data.get("experiment_stage") == "target_condition")

    # skip target_condition -> baseline stage
    update, _, query = _make_update_and_context(callback_data="cx|a=skip_target_condition")
    asyncio.run(handle_experiment_callback(update, update_ctx))
    check("moves to baseline stage", update_ctx.user_data.get("experiment_stage") == "baseline")

    # reply baseline text
    update, _, _ = _make_update_and_context(text="4 of 5 afternoons were rough")
    asyncio.run(cmd_message(update, update_ctx))
    check("baseline saved", update_ctx.user_data["experiment_draft"]["baseline_window"] == "4 of 5 afternoons were rough")
    check("stage cleared, trial window question next (no stage — buttons)", "experiment_stage" not in update_ctx.user_data)

    # tap a trial-window preset (2 weeks = 14 days)
    update, _, query = _make_update_and_context(callback_data="cx|a=trial|d=14")
    asyncio.run(handle_experiment_callback(update, update_ctx))
    check("trial_window label saved from preset", update_ctx.user_data["experiment_draft"]["trial_window"] == "2 weeks")

    # skip outcome measures -> saves the experiment
    update, _, query = _make_update_and_context(callback_data="cx|a=skip_measures")
    asyncio.run(handle_experiment_callback(update, update_ctx))
    db = app_module._supabase
    payload = db.table("capacity_experiments").insert.call_args[0][0]
    check("full draft persisted including baseline/trial", payload["baseline_window"] == "4 of 5 afternoons were rough")
    check("trial_window persisted", payload["trial_window"] == "2 weeks")
    check("outcome_measures defaults to empty list on skip", payload["outcome_measures"] == [])
    app_module._supabase = None


def test_activate_schedules_reminder_via_job_queue():
    print("\n── activate_confirm — mark active + schedule reminder (job_queue) ─")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_experiment_callback

    app_module._supabase = _make_db(experiments=[_experiment(id=8, status="active")])
    update, context, query = _make_update_and_context(callback_data="cx|a=activate_confirm|id=8|d=7")
    asyncio.run(handle_experiment_callback(update, context))

    db = app_module._supabase
    check("status update called (mark_active)", db.table("capacity_experiments").update.called)
    update_payload = db.table("capacity_experiments").update.call_args[0][0]
    check("status set to active", update_payload["status"] == "active")
    check("reminder scheduled via job_queue.run_once — same mechanism as /helpme",
          context.job_queue.run_once.call_count == 1)
    app_module._supabase = None


def test_activate_no_reminder_when_days_zero():
    print("\n── activate_confirm — d=0 (no reminder) skips scheduling ─────────")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_experiment_callback

    app_module._supabase = _make_db(experiments=[_experiment(id=8, status="active")])
    update, context, query = _make_update_and_context(callback_data="cx|a=activate_confirm|id=8|d=0")
    asyncio.run(handle_experiment_callback(update, context))
    check("no reminder scheduled", context.job_queue.run_once.call_count == 0)
    app_module._supabase = None


def test_complete_flow_result_then_confidence():
    print("\n── complete flow — result (free text) -> confidence (buttons) ────")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_experiment_callback, cmd_message

    app_module._supabase = _make_db(experiments=[_experiment(id=3, status="completed", result="Helped a lot")])
    context = MagicMock()
    context.user_data = {}
    context.job_queue = MagicMock()

    update, _, query = _make_update_and_context(callback_data="cx|a=complete|id=3")
    asyncio.run(handle_experiment_callback(update, context))
    check("stage set to result, target id recorded", context.user_data.get("experiment_stage") == "result")
    check("target id recorded", context.user_data.get("experiment_target_id") == "3")

    update, _, _ = _make_update_and_context(text="Post-work recovery was noticeably better.")
    asyncio.run(cmd_message(update, context))
    check("pending result stashed", context.user_data.get("experiment_pending_result") == "Post-work recovery was noticeably better.")
    check("stage cleared, awaiting confidence tap", "experiment_stage" not in context.user_data)

    update, _, query = _make_update_and_context(callback_data="cx|a=conf|id=3|c=moderate")
    asyncio.run(handle_experiment_callback(update, context))
    db = app_module._supabase
    check("complete update called", db.table("capacity_experiments").update.called)
    payload = db.table("capacity_experiments").update.call_args[0][0]
    check("status set to completed", payload["status"] == "completed")
    check("result written", payload["result"] == "Post-work recovery was noticeably better.")
    check("confidence written", payload["confidence"] == "moderate")
    check("pending result cleared", "experiment_pending_result" not in context.user_data)
    app_module._supabase = None


def test_stop_now_writes_stopped_with_no_reason():
    print("\n── stop_now — stoppable without giving a reason (spec §15) ───────")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_experiment_callback

    app_module._supabase = _make_db(experiments=[_experiment(id=4, status="stopped")])
    context = MagicMock()
    context.user_data = {"experiment_stage": "stop_reason", "experiment_target_id": "4"}
    context.job_queue = MagicMock()

    update, _, query = _make_update_and_context(callback_data="cx|a=stop_now|id=4")
    asyncio.run(handle_experiment_callback(update, context))

    db = app_module._supabase
    payload = db.table("capacity_experiments").update.call_args[0][0]
    check("status set to stopped", payload["status"] == "stopped")
    check("result is None when stopped without a reason", payload.get("result") is None)
    check("flow state cleared", "experiment_stage" not in context.user_data)
    app_module._supabase = None


def test_stop_with_reason_via_free_text():
    print("\n── stop with a reason — free text -> stopped with result ─────────")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import cmd_message

    app_module._supabase = _make_db(experiments=[_experiment(id=6, status="stopped", result="Made evenings worse")])
    context = MagicMock()
    context.user_data = {"experiment_stage": "stop_reason", "experiment_target_id": "6"}

    update, _, _ = _make_update_and_context(text="Made evenings worse, stopping.")
    asyncio.run(cmd_message(update, context))

    db = app_module._supabase
    payload = db.table("capacity_experiments").update.call_args[0][0]
    check("status set to stopped", payload["status"] == "stopped")
    check("reason written as result", payload["result"] == "Made evenings worse, stopping.")
    check("flow state cleared", "experiment_stage" not in context.user_data)
    app_module._supabase = None


def main():
    print("=" * 60)
    print("/experiment — V3 Mission 4 test suite")
    print("=" * 60)

    test_render_menu_empty_vs_populated()
    test_kb_menu_has_propose_button_and_view_per_experiment()
    test_render_experiment_detail_includes_core_fields()
    test_kb_experiment_detail_status_specific_actions()
    test_kb_activate_reminder_presets_map_to_days()
    test_parse_cb_experiment_fields()
    test_cmd_experiment_clears_stale_state_and_shows_menu()
    test_propose_flow_hypothesis_then_change_then_save_now()
    test_add_details_branch_walks_through_optional_fields()
    test_activate_schedules_reminder_via_job_queue()
    test_activate_no_reminder_when_days_zero()
    test_complete_flow_result_then_confidence()
    test_stop_now_writes_stopped_with_no_reason()
    test_stop_with_reason_via_free_text()

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
