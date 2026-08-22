"""
Tests for /helpme — MY CAPACITY TODAY V02 WP04 + WP05.

Covers helpme.py's pure rendering/parsing functions and app.py's handler
wiring (state selection -> optional clarifying tap -> ranked offer ->
accept/skip/stop -> reassessment), against a mocked Supabase client — same
style as the other capacitybot test files.

Run from repo root:
    python telegram-bots/capacitybot/test_helpme.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parents[2]))

from telegram_bots.capacitybot.helpme import (
    HELP_STATE_OPTIONS,
    OUTCOME_OPTIONS,
    kb_helpme_entry,
    kb_offer,
    parse_cb,
    q_helpme_entry,
    render_accepted,
    render_offer,
)

PASS = "PASS"
FAIL = "FAIL"
_results: list[tuple[str, str]] = []


def check(label: str, condition: bool) -> bool:
    tag = PASS if condition else FAIL
    _results.append((tag, label))
    print(f"  [{tag}] {label}")
    return condition


# ── Pure rendering functions ─────────────────────────────────────────────────

def test_q_helpme_entry_lists_all_9_states():
    print("\n── q_helpme_entry — all 9 states fully worded in the body ───────")
    text = q_helpme_entry()
    check("all 9 full state descriptions present",
          all(label in text for _, label in HELP_STATE_OPTIONS))


def test_kb_helpme_entry_buttons_are_compact():
    print("\n── kb_helpme_entry — compact buttons, full text stays in body ───")
    kb = kb_helpme_entry()
    total = sum(len(row) for row in kb.inline_keyboard)
    check("9 state buttons", total == 9)
    check("no button carries a full long description",
          not any("Everything feels like too much" == b.text
                  for row in kb.inline_keyboard for b in row))


def test_parse_cb_helpme_fields():
    print("\n── parse_cb — ch| state + optional context/triage fields ────────")
    f = parse_cb("ch|s=unknown|cap=g|stim=b|pain=l")
    check("state parsed", f.get("s") == "unknown")
    check("triage capacity parsed", f.get("cap") == "g")
    check("triage stimulation parsed", f.get("stim") == "b")
    check("triage pain parsed", f.get("pain") == "l")


def test_render_offer_includes_full_description_and_minutes():
    print("\n── render_offer — full description + duration shown ─────────────")
    text = render_offer({"title": "Move somewhere quieter",
                          "full_description": "Move to a quieter environment for 10 minutes.",
                          "estimated_minutes": 10})
    check("full description present", "Move to a quieter environment" in text)
    check("duration present", "10 min" in text)
    check("asks if worth trying", "Worth trying" in text)


def test_kb_offer_has_four_action_buttons():
    print("\n── kb_offer — Accept / Something else / Can't do that / Stop ────")
    kb = kb_offer("overwhelmed", "quiet_10")
    texts = [b.text for row in kb.inline_keyboard for b in row]
    check("accept button present", any("I'll do that" in t for t in texts))
    check("something-else button present", any("Something else" in t for t in texts))
    check("stop button present", any("Stop" in t for t in texts))
    accept_cb = next(b.callback_data for row in kb.inline_keyboard for b in row if "I'll do that" in b.text)
    check("accept callback carries state+intervention_id+act=accept",
          accept_cb == "chi|s=overwhelmed|iid=quiet_10|act=accept")


def test_render_accepted_mentions_reminder_when_present():
    print("\n── render_accepted — reminder mention only when scheduled ───────")
    with_reminder = render_accepted({"title": "Rest"}, 20)
    without = render_accepted({"title": "Rest"}, None)
    check("mentions reminder window when scheduled", "20 minutes" in with_reminder)
    check("no reminder mention when not scheduled", "minutes" not in without)


# ── Wiring — app.py handlers against a mocked Supabase client ───────────────

def _make_db(interventions=None, events=None):
    db = MagicMock()
    _table_mocks: dict[str, MagicMock] = {}

    def table_side_effect(name):
        if name in _table_mocks:
            return _table_mocks[name]
        t = MagicMock()
        if name == "capacity_interventions":
            sel = MagicMock()
            sel.eq.return_value.contains.return_value.execute.return_value = MagicMock(data=interventions or [])
            sel.eq.return_value.execute.return_value = MagicMock(data=interventions or [])
            t.select.return_value = sel
        elif name == "capacity_intervention_events":
            sel = MagicMock()
            sel.in_.return_value.not_.is_.return_value.order.return_value.limit.return_value.execute.return_value = \
                MagicMock(data=events or [])
            t.select.return_value = sel
            t.insert.return_value.execute.return_value = MagicMock(data=[{"id": 77}])
            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
        _table_mocks[name] = t
        return t

    db.table.side_effect = table_side_effect
    return db


def _make_update_and_context(callback_data: str):
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.data = callback_data

    update = MagicMock()
    update.callback_query = query
    update.effective_chat.id = 12345

    context = MagicMock()
    context.user_data = {}
    context.job_queue = MagicMock()
    context.bot.send_message = AsyncMock()
    return update, context, query


def _intervention(iid, **overrides):
    base = dict(
        intervention_id=iid, title=iid, full_description=iid, button_label=iid,
        target_states=["overwhelmed"], capacity_allowed=["green", "orange", "red"],
        stimulation_effect="neutral", pain_compatible=True, executive_effort="low",
        estimated_minutes=10, requires_followup=True,
    )
    base.update(overrides)
    return base


def test_cmd_helpme_shows_entry_and_clears_prior_flow_state():
    print("\n── cmd_helpme — shows entry, clears any stale flow state ────────")
    from telegram_bots.capacitybot.app import cmd_helpme

    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {"helpme_ctx": {"stale": True}, "helpme_seen": ["x"]}

    asyncio.run(cmd_helpme(update, context))

    check("replied with the entry question", update.message.reply_text.called)
    check("stale flow state cleared", "helpme_ctx" not in context.user_data and "helpme_seen" not in context.user_data)


def test_helpme_callback_overwhelmed_asks_reduce_first():
    print("\n── handle_helpme_callback — overwhelmed asks 'reduce first' ─────")
    from telegram_bots.capacitybot.app import _get_supabase, handle_helpme_callback
    import telegram_bots.capacitybot.app as app_module

    app_module._supabase = _make_db(interventions=[_intervention("quiet_10")])
    update, context, query = _make_update_and_context("ch|s=overwhelmed")
    asyncio.run(handle_helpme_callback(update, context))

    check("asks the reduce-first clarifying question", "easiest to reduce" in query.edit_message_text.call_args[0][0])
    app_module._supabase = None


def test_helpme_callback_flat_goes_straight_to_offer():
    print("\n── handle_helpme_callback — flat (no clarifier) goes straight to offer ─")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_helpme_callback

    app_module._supabase = _make_db(interventions=[_intervention("move_5", target_states=["flat"])])
    update, context, query = _make_update_and_context("ch|s=flat")
    asyncio.run(handle_helpme_callback(update, context))

    check("offers an intervention directly (no extra question)",
          context.user_data.get("helpme_current") == "move_5")
    check("flow context stored", context.user_data.get("helpme_ctx") is not None)
    app_module._supabase = None


def test_helpme_callback_unknown_runs_triage_then_offers():
    print("\n── handle_helpme_callback — unknown state runs 3-step triage ────")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_helpme_callback

    app_module._supabase = _make_db(interventions=[_intervention("maintain", target_states=["unknown"])])

    update, context, query = _make_update_and_context("ch|s=unknown")
    asyncio.run(handle_helpme_callback(update, context))
    check("triage step 1: asks capacity", "capacity" in query.edit_message_text.call_args[0][0].lower())

    update, context, query = _make_update_and_context("ch|s=unknown|cap=g")
    asyncio.run(handle_helpme_callback(update, context))
    check("triage step 2: asks stimulation", "stimulation" in query.edit_message_text.call_args[0][0].lower())

    update, context, query = _make_update_and_context("ch|s=unknown|cap=g|stim=b")
    asyncio.run(handle_helpme_callback(update, context))
    check("triage step 3: asks pain", "pain" in query.edit_message_text.call_args[0][0].lower())

    update, context, query = _make_update_and_context("ch|s=unknown|cap=g|stim=b|pain=l")
    asyncio.run(handle_helpme_callback(update, context))
    check("triage complete: offers an intervention", context.user_data.get("helpme_current") == "maintain")
    check("triage answers decoded into flow context",
          context.user_data["helpme_ctx"]["capacity_state"] == "green")
    app_module._supabase = None


def test_offer_skip_excludes_and_reoffers():
    print("\n── handle_helpme_offer_callback — skip excludes and re-offers ───")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_helpme_offer_callback

    app_module._supabase = _make_db(interventions=[
        _intervention("a", target_states=["overwhelmed"]),
        _intervention("b", target_states=["overwhelmed"]),
    ])
    update, context, query = _make_update_and_context("chi|s=overwhelmed|iid=a|act=skip")
    context.user_data["helpme_ctx"] = {"capacity_state": None, "stimulation_state": None, "pain_state": None}
    context.user_data["helpme_seen"] = []

    asyncio.run(handle_helpme_offer_callback(update, context))

    check("declined id recorded", "a" in context.user_data["helpme_seen"])
    check("offers a different intervention", context.user_data.get("helpme_current") != "a")
    app_module._supabase = None


def test_offer_stop_clears_flow_state():
    print("\n── handle_helpme_offer_callback — stop ends the flow cleanly ────")
    from telegram_bots.capacitybot.app import handle_helpme_offer_callback

    update, context, query = _make_update_and_context("chi|s=overwhelmed|iid=a|act=stop")
    context.user_data["helpme_ctx"] = {}
    context.user_data["helpme_seen"] = ["a"]

    asyncio.run(handle_helpme_offer_callback(update, context))

    check("confirms stopping", "stop" in query.edit_message_text.call_args[0][0].lower())
    check("flow state cleared", "helpme_ctx" not in context.user_data and "helpme_seen" not in context.user_data)


def test_offer_accept_logs_event_and_schedules_reminder():
    print("\n── handle_helpme_offer_callback — accept logs event + schedules reminder ─")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_helpme_offer_callback

    db = _make_db(interventions=[_intervention("quiet_10", requires_followup=True, estimated_minutes=10)])
    app_module._supabase = db
    update, context, query = _make_update_and_context("chi|s=overwhelmed|iid=quiet_10|act=accept")
    context.user_data["helpme_ctx"] = {"capacity_state": "red", "stimulation_state": "high", "pain_state": None}

    asyncio.run(handle_helpme_offer_callback(update, context))

    check("logs the accepted event", db.table("capacity_intervention_events").insert.called)
    payload = db.table("capacity_intervention_events").insert.call_args[0][0]
    check("event source is helpme", payload["source"] == "helpme")
    check("capacity_before carried through from flow context", payload["capacity_before"] == "red")
    check("reminder scheduled (requires_followup=True)", context.job_queue.run_once.call_count == 1)
    check("flow state cleared after accept", "helpme_ctx" not in context.user_data)
    app_module._supabase = None


def test_offer_accept_no_followup_skips_reminder():
    print("\n── handle_helpme_offer_callback — accept, requires_followup=False -> no reminder ─")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_helpme_offer_callback

    db = _make_db(interventions=[_intervention("maintain", requires_followup=False)])
    app_module._supabase = db
    update, context, query = _make_update_and_context("chi|s=unknown|iid=maintain|act=accept")
    context.user_data["helpme_ctx"] = {"capacity_state": "green", "stimulation_state": None, "pain_state": None}

    asyncio.run(handle_helpme_offer_callback(update, context))

    check("no reminder scheduled", context.job_queue.run_once.call_count == 0)
    app_module._supabase = None


def test_reassessment_full_flow_writes_outcome():
    print("\n── handle_helpme_reassessment_callback — full 3-step flow ───────")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_helpme_reassessment_callback

    db = _make_db()
    app_module._supabase = db

    update, context, query = _make_update_and_context("chr|ev=77|o=better")
    asyncio.run(handle_helpme_reassessment_callback(update, context))
    check("asks capacity-after next", "capacity" in query.edit_message_text.call_args[0][0].lower())

    update, context, query = _make_update_and_context("chr|ev=77|o=better|ca=orange")
    asyncio.run(handle_helpme_reassessment_callback(update, context))
    check("asks would-use-again next", "again" in query.edit_message_text.call_args[0][0].lower())

    update, context, query = _make_update_and_context("chr|ev=77|o=better|ca=orange|ua=yes")
    asyncio.run(handle_helpme_reassessment_callback(update, context))
    check("confirms the reassessment was logged", "logged" in query.edit_message_text.call_args[0][0].lower())
    payload = db.table("capacity_intervention_events").update.call_args[0][0]
    check("outcome written", payload["outcome"] == "better")
    check("capacity_after written", payload["capacity_after"] == "orange")
    check("would_use_again written", payload["would_use_again"] == "yes")
    app_module._supabase = None


def test_reassessment_skip_writes_nulls_not_the_string_skip():
    print("\n── handle_helpme_reassessment_callback — Skip -> null, not 'skip' ─")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_helpme_reassessment_callback

    db = _make_db()
    app_module._supabase = db
    update, context, query = _make_update_and_context("chr|ev=77|o=worse|ca=skip|ua=skip")
    asyncio.run(handle_helpme_reassessment_callback(update, context))
    payload = db.table("capacity_intervention_events").update.call_args[0][0]
    check("capacity_after is None, not the literal string 'skip'", payload.get("capacity_after") is None)
    check("would_use_again is None, not the literal string 'skip'", payload.get("would_use_again") is None)
    app_module._supabase = None


def main():
    print("=" * 60)
    print("/helpme — V02 WP04 + WP05 test suite")
    print("=" * 60)

    test_q_helpme_entry_lists_all_9_states()
    test_kb_helpme_entry_buttons_are_compact()
    test_parse_cb_helpme_fields()
    test_render_offer_includes_full_description_and_minutes()
    test_kb_offer_has_four_action_buttons()
    test_render_accepted_mentions_reminder_when_present()
    test_cmd_helpme_shows_entry_and_clears_prior_flow_state()
    test_helpme_callback_overwhelmed_asks_reduce_first()
    test_helpme_callback_flat_goes_straight_to_offer()
    test_helpme_callback_unknown_runs_triage_then_offers()
    test_offer_skip_excludes_and_reoffers()
    test_offer_stop_clears_flow_state()
    test_offer_accept_logs_event_and_schedules_reminder()
    test_offer_accept_no_followup_skips_reminder()
    test_reassessment_full_flow_writes_outcome()
    test_reassessment_skip_writes_nulls_not_the_string_skip()

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
