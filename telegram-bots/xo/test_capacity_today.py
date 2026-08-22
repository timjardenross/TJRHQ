"""
Tests for capacity_today.py — MY CAPACITY TODAY.

Covers the deep check-in extension (recovery_factors/helpful_actions/
unhelpful_actions/free-text note) and the action-suggestion rule table,
neither of which had coverage before. Same check()/main() style as
test_voice_capture.py so a bare `python test_capacity_today.py` run gives a
real pass/fail signal (pytest just executes each test_* function without
asserting on check()'s return value).

Run from repo root:
    python telegram-bots/xo/test_capacity_today.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parents[2]))

from telegram_bots.xo.capacity_today import (
    HELPFUL_ACTIONS_OPTIONS,
    RECOVERY_FACTORS,
    UNHELPFUL_ACTIONS_OPTIONS,
    kb_deep_multiselect,
    parse_cb,
    suggest_actions,
    write_deep_checkin,
)

PASS = "PASS"
FAIL = "FAIL"
_results: list[tuple[str, str]] = []


def check(label: str, condition: bool) -> bool:
    tag = PASS if condition else FAIL
    _results.append((tag, label))
    print(f"  [{tag}] {label}")
    return condition


def _make_db():
    table = MagicMock()
    table.update.return_value.eq.return_value.execute.return_value = MagicMock()
    db = MagicMock()
    db.table.return_value = table
    return db, table


# ── kb_deep_multiselect ───────────────────────────────────────────────────────

def test_kb_deep_multiselect_toggle():
    print("\n── kb_deep_multiselect toggle math ──────────────────────────────")
    kb = kb_deep_multiselect("42", "rf", RECOVERY_FACTORS, "")
    first_option_cb = kb.inline_keyboard[0][0].callback_data
    check("untoggled option's callback selects it", first_option_cb == "ctd|id=42|rf=0")
    check("base carries the row id", first_option_cb.startswith("ctd|id=42|"))

    kb2 = kb_deep_multiselect("42", "rf", RECOVERY_FACTORS, "0")
    toggled_off_cb = kb2.inline_keyboard[0][0].callback_data
    check("re-tapping a selected option deselects it", toggled_off_cb == "ctd|id=42|rf=")

    kb3 = kb_deep_multiselect("42", "rf", RECOVERY_FACTORS, "0,2")
    # option 1 is not yet selected — tapping it should ADD to the existing set
    add_cb = kb3.inline_keyboard[0][1].callback_data
    check("tapping a new option preserves prior selections", add_cb == "ctd|id=42|rf=0,2,1")

    continue_row = kb3.inline_keyboard[-2]
    done_row = kb3.inline_keyboard[-1]
    check("Continue button carries selection forward unchanged",
          continue_row[0].callback_data == "ctd|id=42|rf=0,2|next=1")
    check("Done button carries selection forward unchanged",
          done_row[0].callback_data == "ctd|id=42|rf=0,2|done=1")


def test_kb_deep_multiselect_option_lists_nonempty():
    print("\n── deep check-in option lists are populated ─────────────────────")
    check("RECOVERY_FACTORS has options", len(RECOVERY_FACTORS) > 0)
    check("HELPFUL_ACTIONS_OPTIONS has options", len(HELPFUL_ACTIONS_OPTIONS) > 0)
    check("UNHELPFUL_ACTIONS_OPTIONS has options", len(UNHELPFUL_ACTIONS_OPTIONS) > 0)
    check("helpful/unhelpful lists are distinct (not accidentally aliased)",
          HELPFUL_ACTIONS_OPTIONS is not UNHELPFUL_ACTIONS_OPTIONS)


# ── write_deep_checkin — new fields ──────────────────────────────────────────

def test_write_deep_checkin_recovery_factors():
    print("\n── write_deep_checkin — recovery_factors (Q5) ───────────────────")
    db, table = _make_db()
    ok, err = asyncio.run(write_deep_checkin(db, "7", {"rf": "0,2"}))
    check("write reports success", ok)
    check("no error message", err is None)
    payload = table.update.call_args[0][0]
    check("recovery_factors decoded from index csv",
          payload.get("recovery_factors") == [RECOVERY_FACTORS[0], RECOVERY_FACTORS[2]])


def test_write_deep_checkin_helpful_and_unhelpful_actions():
    print("\n── write_deep_checkin — helpful/unhelpful actions (Q6/Q7) ───────")
    db, table = _make_db()
    asyncio.run(write_deep_checkin(db, "7", {"ha": "1"}))
    ha_payload = table.update.call_args[0][0]
    check("helpful_actions decoded", ha_payload.get("helpful_actions") == [HELPFUL_ACTIONS_OPTIONS[1]])

    db2, table2 = _make_db()
    asyncio.run(write_deep_checkin(db2, "7", {"ua": "0,1"}))
    ua_payload = table2.update.call_args[0][0]
    check("unhelpful_actions decoded",
          ua_payload.get("unhelpful_actions") == [UNHELPFUL_ACTIONS_OPTIONS[0], UNHELPFUL_ACTIONS_OPTIONS[1]])


def test_write_deep_checkin_empty_selection_still_writes_empty_list():
    print("\n── write_deep_checkin — empty multi-select still saves [] ──────")
    db, table = _make_db()
    # "Continue"/"Done" tapped with nothing selected -> csv is "" not None
    asyncio.run(write_deep_checkin(db, "7", {"rf": ""}))
    payload = table.update.call_args[0][0]
    check("empty csv still writes an explicit empty list (not skipped)",
          payload.get("recovery_factors") == [])


def test_write_deep_checkin_closing_note():
    print("\n── write_deep_checkin — closing free-text note (tn + nt) ───────")
    db, table = _make_db()
    text = "Argument before lunch, then couldn't settle for an hour."
    asyncio.run(write_deep_checkin(db, "7", {"tn": text, "nt": text}))
    payload = table.update.call_args[0][0]
    check("trigger_note saved", payload.get("trigger_note") == text)
    check("notes saved", payload.get("notes") == text)


def test_write_deep_checkin_only_touches_provided_fields():
    print("\n── write_deep_checkin — partial payload doesn't fabricate fields ─")
    db, table = _make_db()
    asyncio.run(write_deep_checkin(db, "7", {"lc": "p"}))
    payload = table.update.call_args[0][0]
    check("load_category present", "load_category" in payload)
    check("recovery_factors absent when rf not passed", "recovery_factors" not in payload)
    check("helpful_actions absent when ha not passed", "helpful_actions" not in payload)
    check("trigger_note absent when tn not passed", "trigger_note" not in payload)


# ── suggest_actions — previously untested ────────────────────────────────────

def test_suggest_actions_red_high_stimulation():
    print("\n── suggest_actions — red + high stimulation (spec worked example) ─")
    codes = suggest_actions({"capacity_state": "red", "stimulation_state": "high"})
    check("returns 3-5 codes", 3 <= len(codes) <= 5)
    check("includes reduce_input", "reduce_input" in codes)


def test_suggest_actions_extreme_compensation():
    print("\n── suggest_actions — extreme compensation ───────────────────────")
    codes = suggest_actions({"compensation_load": "extreme"})
    check("caps at 5 codes even though the rule adds 7", len(codes) <= 5)
    check("includes stop_performing", "stop_performing" in codes)


def test_suggest_actions_green_default():
    print("\n── suggest_actions — green capacity, no other flags ─────────────")
    codes = suggest_actions({"capacity_state": "green"})
    check("falls through to maintain", codes == ["maintain"])


def test_suggest_actions_no_signal():
    print("\n── suggest_actions — no fields set at all ───────────────────────")
    codes = suggest_actions({})
    check("returns empty list rather than raising", codes == [])


# ── parse_cb sanity for the new fields ───────────────────────────────────────

def test_parse_cb_handles_new_field_names():
    print("\n── parse_cb — rf/ha/ua/final round-trip ─────────────────────────")
    f = parse_cb("ctd|id=7|rf=0,2|next=1")
    check("id parsed", f.get("id") == "7")
    check("rf parsed as csv string", f.get("rf") == "0,2")
    check("next flag parsed", f.get("next") == "1")

    f2 = parse_cb("ctd|id=7|final=1")
    check("final flag parsed", f2.get("final") == "1")


# ── Wiring smoke tests — app.py's handlers, no real Supabase ─────────────────
# Verifies the control flow (which message/keyboard comes next, what gets
# stashed in user_data, that job_queue.run_once is actually called) rather
# than DB persistence, which the write_deep_checkin tests above already
# cover directly. _get_supabase() returns None in this environment (no
# SUPABASE_URL configured), so every write! call degrades to its documented
# "Supabase unavailable" failure path — that's fine here, this is checking
# wiring, not persistence.

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


def test_deep_callback_ua_continue_prompts_for_free_text_note():
    print("\n── handle_capacity_deep_callback — ua 'Continue' -> note prompt ─")
    from telegram_bots.xo.app import handle_capacity_deep_callback

    update, context, query = _make_update_and_context("ctd|id=99|ua=0|next=1")
    asyncio.run(handle_capacity_deep_callback(update, context))

    check("prompts for the closing free-text note", "before this" in query.edit_message_text.call_args[0][0])
    check("stashes the row id in user_data for cmd_message to pick up",
          context.user_data.get("capacity_deep_note_id") == "99")


def test_deep_callback_ua_done_skips_straight_to_note_prompt():
    print("\n── handle_capacity_deep_callback — ua 'Done for now' -> note prompt ─")
    from telegram_bots.xo.app import handle_capacity_deep_callback

    update, context, query = _make_update_and_context("ctd|id=99|ua=0|done=1")
    asyncio.run(handle_capacity_deep_callback(update, context))

    check("Done also lands on the note prompt (not a different exit)",
          "before this" in query.edit_message_text.call_args[0][0])
    check("row id stashed", context.user_data.get("capacity_deep_note_id") == "99")


def test_deep_callback_final_clears_pending_note_state():
    print("\n── handle_capacity_deep_callback — final=1 clears pending state ──")
    from telegram_bots.xo.app import handle_capacity_deep_callback

    update, context, query = _make_update_and_context("ctd|id=99|final=1")
    context.user_data["capacity_deep_note_id"] = "99"
    asyncio.run(handle_capacity_deep_callback(update, context))

    check("pending note state cleared on Skip", "capacity_deep_note_id" not in context.user_data)
    check("confirms save", "saved" in query.edit_message_text.call_args[0][0].lower())


def test_reminder_callback_no_duration_shows_picker():
    print("\n── handle_capacity_reminder_callback — no duration -> shows picker ─")
    from telegram_bots.xo.app import handle_capacity_reminder_callback

    update, context, query = _make_update_and_context("ctr|id=99")
    asyncio.run(handle_capacity_reminder_callback(update, context))

    check("no job scheduled yet", context.job_queue.run_once.call_count == 0)
    check("prompts for a duration", "how long" in query.edit_message_text.call_args[0][0].lower())


def test_reminder_callback_with_duration_schedules_job():
    print("\n── handle_capacity_reminder_callback — duration picked -> schedules ─")
    from telegram_bots.xo.app import handle_capacity_reminder_callback

    update, context, query = _make_update_and_context("ctr|id=99|m=45")
    asyncio.run(handle_capacity_reminder_callback(update, context))

    check("schedules exactly one job", context.job_queue.run_once.call_count == 1)
    _, kwargs = context.job_queue.run_once.call_args
    check("fires in 45 minutes (2700s)", kwargs.get("when") == 45 * 60)
    check("confirms to the user", "45 minutes" in query.edit_message_text.call_args[0][0])


def test_cmd_message_intercepts_pending_deep_note():
    print("\n── cmd_message — pending capacity note intercepted before LLM ───")
    from telegram_bots.xo.app import cmd_message

    update = MagicMock()
    update.message.text = "Loud open-plan office, skipped lunch."
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {"capacity_deep_note_id": "99"}

    asyncio.run(cmd_message(update, context))

    check("pending state consumed (popped)", "capacity_deep_note_id" not in context.user_data)
    check("replied without reaching the LLM path", update.message.reply_text.called)


def main():
    print("=" * 60)
    print("MY CAPACITY TODAY — deep check-in test suite")
    print("=" * 60)

    test_kb_deep_multiselect_toggle()
    test_kb_deep_multiselect_option_lists_nonempty()
    test_write_deep_checkin_recovery_factors()
    test_write_deep_checkin_helpful_and_unhelpful_actions()
    test_write_deep_checkin_empty_selection_still_writes_empty_list()
    test_write_deep_checkin_closing_note()
    test_write_deep_checkin_only_touches_provided_fields()
    test_suggest_actions_red_high_stimulation()
    test_suggest_actions_extreme_compensation()
    test_suggest_actions_green_default()
    test_suggest_actions_no_signal()
    test_parse_cb_handles_new_field_names()
    test_deep_callback_ua_continue_prompts_for_free_text_note()
    test_deep_callback_ua_done_skips_straight_to_note_prompt()
    test_deep_callback_final_clears_pending_note_state()
    test_reminder_callback_no_duration_shows_picker()
    test_reminder_callback_with_duration_schedules_job()
    test_cmd_message_intercepts_pending_deep_note()

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
