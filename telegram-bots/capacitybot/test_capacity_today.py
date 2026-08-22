"""
Tests for capacity_today.py — MY CAPACITY TODAY (V02 WP01).

Covers: the V02 WP01 rendering utility (full-body question/option text,
paginated multi-select keyboards, short-label buttons), the deep check-in
extension, and the action-suggestion rule table. Same check()/main() style
as test_voice_capture.py so a bare `python test_capacity_today.py` run
gives a real pass/fail signal.

Run from repo root:
    python telegram-bots/capacitybot/test_capacity_today.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parents[2]))

from telegram_bots.capacitybot.capacity_today import (
    ACTIVE_LOADS,
    ACTIVE_LOADS_SHORT,
    HELPFUL_ACTIONS_OPTIONS,
    IDENTIFIED_NEEDS,
    PAGE_SIZE,
    RECOVERY_FACTORS,
    UNHELPFUL_ACTIONS_OPTIONS,
    kb_capacity,
    kb_deep_multiselect,
    kb_multiselect,
    parse_cb,
    q_active_loads,
    q_capacity,
    q_executive_function,
    render_multiselect_question,
    render_question,
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


# ── V02 WP01 — central rendering utility ─────────────────────────────────────

def test_render_question_shows_full_wording_numbered():
    print("\n── render_question — full option text, numbered ─────────────────")
    text = render_question("How is your capacity?", ["🟢 Sustainable", "🔴 Depleted"])
    check("question text present", "How is your capacity?" in text)
    check("option 1 numbered and full wording present", "1. 🟢 Sustainable" in text)
    check("option 2 numbered and full wording present", "2. 🔴 Depleted" in text)


def test_render_multiselect_question_marks_selected():
    print("\n── render_multiselect_question — full list + selection marks ────")
    text = render_multiselect_question("What's taking capacity?", ["Noise", "Work", "Pain"], "1")
    check("all options listed in body regardless of page", all(o in text for o in ["Noise", "Work", "Pain"]))
    check("selected item marked", "✅" in text)
    check("unselected item marked empty", "▫️" in text)


def test_q_capacity_and_kb_capacity_option_count_match():
    print("\n── q_capacity/kb_capacity — body and buttons stay in sync ───────")
    text = q_capacity()
    kb = kb_capacity()
    check("body lists 3 numbered options", all(f"{i}." in text for i in (1, 2, 3)))
    total_buttons = sum(len(row) for row in kb.inline_keyboard)
    check("keyboard has exactly 3 buttons (no Done row on Q1)", total_buttons == 3)
    check("buttons use compact 'N · short' form, not full label",
          all(len(btn.text) < 20 for row in kb.inline_keyboard for btn in row))


def test_q_executive_function_button_labels_are_compact():
    print("\n── kb_executive_function — long option, compact button ──────────")
    from telegram_bots.capacitybot.capacity_today import kb_executive_function
    text = q_executive_function()
    check("full 'More effort than usual' wording in body", "More effort than usual" in text)
    kb = kb_executive_function("g", "b", "l", "5", "s")
    btn_texts = [b.text for row in kb.inline_keyboard for b in row]
    check("no button carries the full long label",
          not any("More effort than usual" == t for t in btn_texts))
    check("short form appears on a button", any("More effort" in t for t in btn_texts))


# ── V02 WP01 — pagination ────────────────────────────────────────────────────

def test_kb_multiselect_paginates_long_lists():
    print("\n── kb_multiselect — pagination on a 12-item list ─────────────────")
    check("PAGE_SIZE is 4-6 per spec §3.3", 4 <= PAGE_SIZE <= 6)
    kb = kb_multiselect("ct|id=1", "ld", ACTIVE_LOADS, ACTIVE_LOADS_SHORT, "", page=0)
    option_buttons = sum(
        1 for row in kb.inline_keyboard for b in row
        if "·" in b.text and "Previous" not in b.text and "Next" not in b.text
    )
    check(f"page 0 shows at most PAGE_SIZE ({PAGE_SIZE}) option buttons", option_buttons <= PAGE_SIZE)

    nav_texts = [b.text for row in kb.inline_keyboard for b in row]
    check("page 0 has no Previous button (already at start)", not any("Previous" in t for t in nav_texts))
    check("page 0 has a Next button (12 items > PAGE_SIZE)", any("Next" in t for t in nav_texts))

    last_page = (len(ACTIVE_LOADS) - 1) // PAGE_SIZE
    kb_last = kb_multiselect("ct|id=1", "ld", ACTIVE_LOADS, ACTIVE_LOADS_SHORT, "", page=last_page)
    nav_last = [b.text for row in kb_last.inline_keyboard for b in row]
    check("last page has no Next button", not any("Next" in t for t in nav_last))
    check("last page has a Previous button", any("Previous" in t for t in nav_last))


def test_kb_multiselect_preserves_selection_across_pages():
    print("\n── kb_multiselect — selection survives a page change ────────────")
    kb = kb_multiselect("ct|id=1", "ld", ACTIVE_LOADS, ACTIVE_LOADS_SHORT, "0,2", page=0)
    next_btn = next(b for row in kb.inline_keyboard for b in row if "Next" in b.text)
    check("Next button's callback carries the existing selection forward",
          "ld=0,2" in next_btn.callback_data)
    check("Next button's callback advances the page", "pg=1" in next_btn.callback_data)


def test_kb_multiselect_short_list_has_no_pagination_controls():
    print("\n── kb_multiselect — a list under PAGE_SIZE has no Prev/Next ─────")
    short_options = ACTIVE_LOADS[:3]
    short_labels = ACTIVE_LOADS_SHORT[:3]
    kb = kb_multiselect("ct|id=1", "ld", short_options, short_labels, "", page=0)
    nav_texts = [b.text for row in kb.inline_keyboard for b in row]
    check("no Previous/Next when everything fits on one page",
          not any("Previous" in t or "Next" in t for t in nav_texts))


def test_kb_deep_multiselect_toggle():
    print("\n── kb_deep_multiselect toggle math ──────────────────────────────")
    from telegram_bots.capacitybot.capacity_today import RECOVERY_FACTORS_SHORT
    kb = kb_deep_multiselect("42", "rf", RECOVERY_FACTORS, RECOVERY_FACTORS_SHORT, "", page=0)
    first_option_cb = kb.inline_keyboard[0][0].callback_data
    check("untoggled option's callback selects it", first_option_cb == "ctd|id=42|rf=0|pg=0")
    check("base carries the row id", first_option_cb.startswith("ctd|id=42|"))

    kb2 = kb_deep_multiselect("42", "rf", RECOVERY_FACTORS, RECOVERY_FACTORS_SHORT, "0", page=0)
    toggled_off_cb = kb2.inline_keyboard[0][0].callback_data
    check("re-tapping a selected option deselects it", toggled_off_cb == "ctd|id=42|rf=|pg=0")

    kb3 = kb_deep_multiselect("42", "rf", RECOVERY_FACTORS, RECOVERY_FACTORS_SHORT, "0,2", page=0)
    add_cb = kb3.inline_keyboard[0][1].callback_data
    check("tapping a new option preserves prior selections", add_cb == "ctd|id=42|rf=0,2,1|pg=0")

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


def test_q_active_loads_lists_all_12_regardless_of_page():
    print("\n── q_active_loads — full 12-item body even though buttons paginate ─")
    text = q_active_loads("")
    check("all 12 loads present in body", sum(1 for o in ACTIVE_LOADS if o in text) == len(ACTIVE_LOADS))


# ── write_deep_checkin — unchanged data layer ────────────────────────────────

def test_write_deep_checkin_recovery_factors():
    print("\n── write_deep_checkin — recovery_factors (Q5) ───────────────────")
    db, table = _make_db()
    ok, err = asyncio.run(write_deep_checkin(db, "7", {"rf": "0,2"}))
    check("write reports success", ok)
    check("no error message", err is None)
    payload = table.update.call_args[0][0]
    check("recovery_factors decoded from index csv",
          payload.get("recovery_factors") == [RECOVERY_FACTORS[0], RECOVERY_FACTORS[2]])


def test_write_deep_checkin_closing_note():
    print("\n── write_deep_checkin — closing free-text note (tn + nt) ───────")
    db, table = _make_db()
    text = "Argument before lunch, then couldn't settle for an hour."
    asyncio.run(write_deep_checkin(db, "7", {"tn": text, "nt": text}))
    payload = table.update.call_args[0][0]
    check("trigger_note saved", payload.get("trigger_note") == text)
    check("notes saved", payload.get("notes") == text)


# ── suggest_actions — unchanged rule table ───────────────────────────────────

def test_suggest_actions_red_high_stimulation():
    print("\n── suggest_actions — red + high stimulation (spec worked example) ─")
    codes = suggest_actions({"capacity_state": "red", "stimulation_state": "high"})
    check("returns 3-5 codes", 3 <= len(codes) <= 5)
    check("includes reduce_input", "reduce_input" in codes)


def test_suggest_actions_green_default():
    print("\n── suggest_actions — green capacity, no other flags ─────────────")
    codes = suggest_actions({"capacity_state": "green"})
    check("falls through to maintain", codes == ["maintain"])


def test_parse_cb_handles_pagination_field():
    print("\n── parse_cb — pg round-trips like any other field ───────────────")
    f = parse_cb("ct|id=1|ld=0,2|pg=1")
    check("id parsed", f.get("id") == "1")
    check("ld parsed as csv string", f.get("ld") == "0,2")
    check("pg parsed", f.get("pg") == "1")


# ── Wiring smoke tests — app.py's handlers, no real Supabase ─────────────────

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


def test_capacity_callback_active_loads_redraw_passes_page_through():
    print("\n── handle_capacity_callback — ld redraw preserves page ───────────")
    from telegram_bots.capacitybot.app import handle_capacity_callback

    update, context, query = _make_update_and_context("ct|id=99|ld=0|pg=1")
    asyncio.run(handle_capacity_callback(update, context))

    text_arg = query.edit_message_text.call_args[0][0]
    check("full active-loads list still in body on page redraw",
          all(o in text_arg for o in ACTIVE_LOADS))
    kb_arg = query.edit_message_text.call_args[1].get("reply_markup")
    check("keyboard redrawn on the requested page (pg=1 in callbacks)",
          any("pg=1" in b.callback_data for row in kb_arg.inline_keyboard for b in row))


def test_deep_callback_ua_continue_prompts_for_free_text_note():
    print("\n── handle_capacity_deep_callback — ua 'Continue' -> note prompt ─")
    from telegram_bots.capacitybot.app import handle_capacity_deep_callback

    update, context, query = _make_update_and_context("ctd|id=99|ua=0|next=1")
    asyncio.run(handle_capacity_deep_callback(update, context))

    check("prompts for the closing free-text note", "before this" in query.edit_message_text.call_args[0][0])
    check("stashes the row id in user_data for cmd_message to pick up",
          context.user_data.get("capacity_deep_note_id") == "99")


def test_deep_callback_final_clears_pending_note_state():
    print("\n── handle_capacity_deep_callback — final=1 clears pending state ──")
    from telegram_bots.capacitybot.app import handle_capacity_deep_callback

    update, context, query = _make_update_and_context("ctd|id=99|final=1")
    context.user_data["capacity_deep_note_id"] = "99"
    asyncio.run(handle_capacity_deep_callback(update, context))

    check("pending note state cleared on Skip", "capacity_deep_note_id" not in context.user_data)
    check("confirms save", "saved" in query.edit_message_text.call_args[0][0].lower())


def test_reminder_callback_no_duration_shows_picker():
    print("\n── handle_capacity_reminder_callback — no duration -> shows picker ─")
    from telegram_bots.capacitybot.app import handle_capacity_reminder_callback

    update, context, query = _make_update_and_context("ctr|id=99")
    asyncio.run(handle_capacity_reminder_callback(update, context))

    check("no job scheduled yet", context.job_queue.run_once.call_count == 0)
    check("prompts for a duration", "how long" in query.edit_message_text.call_args[0][0].lower())


def test_reminder_callback_with_duration_schedules_job():
    print("\n── handle_capacity_reminder_callback — duration picked -> schedules ─")
    from telegram_bots.capacitybot.app import handle_capacity_reminder_callback

    update, context, query = _make_update_and_context("ctr|id=99|m=45")
    asyncio.run(handle_capacity_reminder_callback(update, context))

    check("schedules exactly one job", context.job_queue.run_once.call_count == 1)
    _, kwargs = context.job_queue.run_once.call_args
    check("fires in 45 minutes (2700s)", kwargs.get("when") == 45 * 60)
    check("confirms to the user", "45 minutes" in query.edit_message_text.call_args[0][0])


def test_cmd_message_intercepts_pending_deep_note():
    print("\n── cmd_message — pending capacity note intercepted ──────────────")
    from telegram_bots.capacitybot.app import cmd_message

    update = MagicMock()
    update.message.text = "Loud open-plan office, skipped lunch."
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {"capacity_deep_note_id": "99"}

    asyncio.run(cmd_message(update, context))

    check("pending state consumed (popped)", "capacity_deep_note_id" not in context.user_data)
    check("replied", update.message.reply_text.called)


def main():
    print("=" * 60)
    print("MY CAPACITY TODAY — V02 WP01 test suite")
    print("=" * 60)

    test_render_question_shows_full_wording_numbered()
    test_render_multiselect_question_marks_selected()
    test_q_capacity_and_kb_capacity_option_count_match()
    test_q_executive_function_button_labels_are_compact()
    test_kb_multiselect_paginates_long_lists()
    test_kb_multiselect_preserves_selection_across_pages()
    test_kb_multiselect_short_list_has_no_pagination_controls()
    test_kb_deep_multiselect_toggle()
    test_kb_deep_multiselect_option_lists_nonempty()
    test_q_active_loads_lists_all_12_regardless_of_page()
    test_write_deep_checkin_recovery_factors()
    test_write_deep_checkin_closing_note()
    test_suggest_actions_red_high_stimulation()
    test_suggest_actions_green_default()
    test_parse_cb_handles_pagination_field()
    test_capacity_callback_active_loads_redraw_passes_page_through()
    test_deep_callback_ua_continue_prompts_for_free_text_note()
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
