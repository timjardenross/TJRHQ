"""
Tests for capacity_today.py — MY CAPACITY TODAY (V02 WP01).

Covers: the V02 WP01 rendering utility (full-body question/option text,
paginated multi-select keyboards, short-label buttons) and the deep
check-in extension. The old rule-based action-suggestion table
(suggest_actions) was superseded by intervention_engine.py in WP06 — see
test_intervention_engine.py for its coverage. Same check()/main() style as
test_voice_capture.py so a bare `python test_capacity_today.py` run gives
a real pass/fail signal.

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
    BODY_CLARITY_OPTIONS,
    BURNOUT_FRAMING_OPTIONS,
    COMPENSATION_TYPE_OPTIONS,
    COMPENSATION_TYPE_SHORT,
    COMPENSATION_TYPE_VALUES,
    HELPFUL_ACTIONS_OPTIONS,
    IDENTIFIED_NEEDS,
    PAGE_SIZE,
    PREDICTABILITY_OPTIONS,
    RECOVERY_FACTORS,
    UNHELPFUL_ACTIONS_OPTIONS,
    base_from,
    kb_body_signal_clarity,
    kb_burnout_framing,
    kb_capacity,
    kb_deep_multiselect,
    kb_emotional,
    kb_multiselect,
    kb_pain,
    kb_predictability,
    kb_sleep,
    kb_social,
    kb_stimulation,
    parse_cb,
    q_active_loads,
    q_body_signal_clarity,
    q_burnout_framing,
    q_capacity,
    q_emotional,
    q_executive_function,
    q_predictability,
    q_sleep,
    q_social,
    render_multiselect_question,
    render_question,
    write_deep_checkin,
    write_quick_checkin,
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
    kb = kb_executive_function({"c": "g", "t": "b", "p": "l", "ps": "5", "r": "s"})
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


# ── V3 burnout-tier deep-check questions (Mission 1 Part D) ─────────────────

def test_burnout_tier_option_lists_populated_and_skippable():
    print("\n── V3 burnout-tier option lists — populated, every one has a not-sure value ─")
    check("BURNOUT_FRAMING_OPTIONS has 5 options", len(BURNOUT_FRAMING_OPTIONS) == 5)
    check("burnout framing includes an explicit not-sure/skip option",
          any(code == "ns" for code, _ in BURNOUT_FRAMING_OPTIONS))
    check("COMPENSATION_TYPE_OPTIONS/SHORT/VALUES same length",
          len(COMPENSATION_TYPE_OPTIONS) == len(COMPENSATION_TYPE_SHORT) == len(COMPENSATION_TYPE_VALUES))
    check("BODY_CLARITY_OPTIONS includes 'No idea'",
          any(label == "No idea" for _, label in BODY_CLARITY_OPTIONS))
    check("PREDICTABILITY_OPTIONS includes an 'I don't know' value",
          any(code == "dk" for code, _ in PREDICTABILITY_OPTIONS))


def test_q_and_kb_burnout_framing():
    print("\n── q_burnout_framing/kb_burnout_framing ──────────────────────────")
    text = q_burnout_framing()
    check("all 5 framing options present in body",
          all(label in text for _, label in BURNOUT_FRAMING_OPTIONS))
    kb = kb_burnout_framing("ctd|id=42")
    buttons = [b for row in kb.inline_keyboard for b in row]
    check("5 buttons, one per option", len(buttons) == 5)
    check("callback carries the row id and bf code", buttons[0].callback_data == "ctd|id=42|bf=ib")


def test_q_and_kb_body_signal_clarity():
    print("\n── q_body_signal_clarity/kb_body_signal_clarity ──────────────────")
    text = q_body_signal_clarity()
    check("all body-clarity options present in body",
          all(label in text for _, label in BODY_CLARITY_OPTIONS))
    kb = kb_body_signal_clarity("ctd|id=42")
    buttons = [b for row in kb.inline_keyboard for b in row]
    check("4 buttons, one per option", len(buttons) == 4)


def test_q_and_kb_predictability():
    print("\n── q_predictability/kb_predictability ─────────────────────────────")
    text = q_predictability()
    check("all predictability options present in body",
          all(label in text for _, label in PREDICTABILITY_OPTIONS))
    kb = kb_predictability("ctd|id=42")
    buttons = [b for row in kb.inline_keyboard for b in row]
    check("4 buttons, one per option", len(buttons) == 4)


def test_write_deep_checkin_burnout_framing():
    print("\n── write_deep_checkin — user_burnout_framing ─────────────────────")
    db, table = _make_db()
    asyncio.run(write_deep_checkin(db, "7", {"bf": "mb"}))
    payload = table.update.call_args[0][0]
    check("code decoded to canonical value", payload.get("user_burnout_framing") == "may_be_in_burnout")


def test_write_deep_checkin_compensation_type_stores_canonical_values_not_labels():
    print("\n── write_deep_checkin — compensation_type stores canonical codes ─")
    db, table = _make_db()
    asyncio.run(write_deep_checkin(db, "7", {"cpt": "0,3"}))
    payload = table.update.call_args[0][0]
    check("compensation_type decoded to canonical snake_case values",
          payload.get("compensation_type") == [COMPENSATION_TYPE_VALUES[0], COMPENSATION_TYPE_VALUES[3]])
    check("compensation_type is NOT the display label text (unlike active_loads)",
          payload.get("compensation_type") != [COMPENSATION_TYPE_OPTIONS[0], COMPENSATION_TYPE_OPTIONS[3]])


def test_write_deep_checkin_body_clarity_and_predictability():
    print("\n── write_deep_checkin — body_signal_clarity + predictability ────")
    db, table = _make_db()
    asyncio.run(write_deep_checkin(db, "7", {"bc": "hi", "pd": "ch"}))
    payload = table.update.call_args[0][0]
    check("body_signal_clarity decoded", payload.get("body_signal_clarity") == "hard_to_interpret")
    check("predictability decoded", payload.get("predictability") == "lots_changing")


def test_deep_callback_mp_writes_early_and_asks_burnout_framing():
    print("\n── handle_capacity_deep_callback — mp answered -> asks burnout framing ─")
    from telegram_bots.capacitybot.app import handle_capacity_deep_callback

    update, context, query = _make_update_and_context("ctd|id=99|lc=p|uc=y|mp=n")
    asyncio.run(handle_capacity_deep_callback(update, context))

    text_arg = query.edit_message_text.call_args[0][0]
    check("asks the burnout-framing question next, not recovery duration",
          "frame this period" in text_arg.lower())
    kb_arg = query.edit_message_text.call_args[1].get("reply_markup")
    check("next screen's base is id-only (no lc/uc/mp chained on)",
          all("lc=" not in b.callback_data for row in kb_arg.inline_keyboard for b in row))


def test_deep_callback_bf_asks_compensation_type_multiselect():
    print("\n── handle_capacity_deep_callback — bf answered -> asks compensation type ─")
    from telegram_bots.capacitybot.app import handle_capacity_deep_callback

    update, context, query = _make_update_and_context("ctd|id=99|bf=rb")
    asyncio.run(handle_capacity_deep_callback(update, context))

    text_arg = query.edit_message_text.call_args[0][0]
    check("asks the compensation-type question", "keep functioning" in text_arg.lower())
    check("all compensation-type options in body",
          all(o in text_arg for o in COMPENSATION_TYPE_OPTIONS))


def test_deep_callback_cpt_continue_asks_body_signal_clarity():
    print("\n── handle_capacity_deep_callback — cpt Continue -> asks body-signal clarity ─")
    from telegram_bots.capacitybot.app import handle_capacity_deep_callback

    update, context, query = _make_update_and_context("ctd|id=99|cpt=0,2|next=1")
    asyncio.run(handle_capacity_deep_callback(update, context))

    text_arg = query.edit_message_text.call_args[0][0]
    check("asks body-signal clarity question next", "body's signals" in text_arg.lower())


def test_deep_callback_cpt_toggle_without_continue_redraws_multiselect():
    print("\n── handle_capacity_deep_callback — cpt toggle (no next/done) redraws ─")
    from telegram_bots.capacitybot.app import handle_capacity_deep_callback

    update, context, query = _make_update_and_context("ctd|id=99|cpt=0|pg=0")
    asyncio.run(handle_capacity_deep_callback(update, context))

    text_arg = query.edit_message_text.call_args[0][0]
    check("still on the compensation-type question", "keep functioning" in text_arg.lower())


def test_deep_callback_bc_asks_predictability():
    print("\n── handle_capacity_deep_callback — bc answered -> asks predictability ─")
    from telegram_bots.capacitybot.app import handle_capacity_deep_callback

    update, context, query = _make_update_and_context("ctd|id=99|bc=cl")
    asyncio.run(handle_capacity_deep_callback(update, context))

    text_arg = query.edit_message_text.call_args[0][0]
    check("asks predictability question next", "predictable" in text_arg.lower())


def test_deep_callback_pd_asks_recovery_duration():
    print("\n── handle_capacity_deep_callback — pd answered -> asks recovery duration ─")
    from telegram_bots.capacitybot.app import handle_capacity_deep_callback

    update, context, query = _make_update_and_context("ctd|id=99|pd=su")
    asyncio.run(handle_capacity_deep_callback(update, context))

    text_arg = query.edit_message_text.call_args[0][0]
    check("asks recovery-duration question, unchanged from before this mission",
          "how long did recovery take" in text_arg.lower())


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


# ── Sleep / Emotional / Social (2026-08-22 workbench data-gap review) ────────

def test_q_sleep_lists_all_5_buckets():
    print("\n── q_sleep — all 5 hour buckets in body ──────────────────────────")
    text = q_sleep()
    for bucket in ("Under 5h", "5-6h", "6-7h", "7-8h", "8h+"):
        check(f"'{bucket}' present", bucket in text)


def test_kb_sleep_callbacks_have_bare_base():
    print("\n── kb_sleep — always the true start of the flow (bare 'ct' base) ─")
    kb = kb_sleep()
    first_cb = kb.inline_keyboard[0][0].callback_data
    check("callback has no prior fields, just sl=", first_cb == "ct|sl=u5")


def test_kb_capacity_carries_sleep_forward_when_present():
    print("\n── kb_capacity(f) — carries sl forward after the sleep question ──")
    kb_with_sleep = kb_capacity({"sl": "u5"})
    cb = kb_with_sleep.inline_keyboard[0][0].callback_data
    check("sl carried into the capacity callback", cb.startswith("ct|sl=u5|c="))

    kb_without = kb_capacity()
    cb2 = kb_without.inline_keyboard[0][0].callback_data
    check("no sl segment when the sleep question wasn't asked (repeat check-ins)", cb2 == "ct|c=g")


def test_emotional_question_sits_between_regulation_and_executive_function():
    print("\n── kb_emotional/kb_executive_function — base_from() threads em correctly ─")
    text = q_emotional()
    for label in ("Light", "Moderate", "Heavy", "Overwhelming"):
        check(f"emotional option '{label}' in body", label in text)

    kb_em = kb_emotional({"c": "g", "t": "b", "p": "l", "ps": "5", "r": "s"})
    em_cb = kb_em.inline_keyboard[0][0].callback_data
    check("emotional callback carries every prior field", em_cb == "ct|c=g|t=b|p=l|ps=5|r=s|em=l")

    from telegram_bots.capacitybot.capacity_today import kb_executive_function
    kb_ef = kb_executive_function({"c": "g", "t": "b", "p": "l", "ps": "5", "r": "s", "em": "m"})
    ef_cb = kb_ef.inline_keyboard[0][0].callback_data
    check("executive_function callback carries em forward too", "em=m" in ef_cb and ef_cb.startswith("ct|c=g|t=b|p=l|ps=5|r=s|em=m|e="))


def test_q_social_and_kb_social():
    print("\n── q_social/kb_social — phase-2 shape, matches kb_compensation ──")
    text = q_social()
    for label in ("Plenty", "Some", "Limited", "None left"):
        check(f"social option '{label}' in body", label in text)
    kb = kb_social("ct|id=42")
    cb = kb.inline_keyboard[0][0].callback_data
    check("id-based base carried through", cb == "ct|id=42|so=g")
    done_cb = kb.inline_keyboard[-1][0].callback_data
    check("has a Done row like other phase-2 single-selects", done_cb == "ct|id=42|done=1")


def test_base_from_includes_new_fields_in_canonical_order():
    print("\n── base_from — sl/em/so slot into _FIELD_ORDER correctly ────────")
    f = {"sl": "u5", "c": "g", "t": "b", "em": "l", "e": "g", "so": "m"}
    base = base_from(f)
    check("sleep first", base.index("sl=") < base.index("c="))
    check("emotional between regulation-slot and executive_function", base.index("em=") < base.index("e="))
    check("social present", "so=m" in base)


def test_write_quick_checkin_maps_new_fields():
    print("\n── write_quick_checkin — sleep/emotional/social decoded correctly ─")
    db, table = _make_db()
    asyncio.run(write_quick_checkin(db, {"id": "7", "sl": "78", "em": "h", "so": "n"}))
    payload = table.update.call_args[0][0]
    check("sleep_state decoded", payload.get("sleep_state") == "7_8")
    check("emotional_state decoded", payload.get("emotional_state") == "heavy")
    check("social_state decoded", payload.get("social_state") == "none")


def test_render_summary_includes_new_fields_when_present():
    print("\n── render_summary — sleep/emotional/social shown when present ───")
    from telegram_bots.capacitybot.capacity_today import render_summary
    text = render_summary({
        "sleep_state": "under_5", "emotional_state": "overwhelming", "social_state": "plenty",
    })
    check("sleep line present", "Under 5h" in text)
    check("emotional line present", "Overwhelming" in text)
    check("social line present", "Plenty" in text)


# ── Wiring — app.py's cmd_capacity + handle_capacity_callback ───────────────

def _make_capacity_db(today_checkin_rows=None):
    db = MagicMock()
    table = MagicMock()
    table.select.return_value.gte.return_value.order.return_value.execute.return_value = \
        MagicMock(data=today_checkin_rows or [])
    table.update.return_value.eq.return_value.execute.return_value = MagicMock()
    table.insert.return_value.execute.return_value = MagicMock(data=[{"id": 99}])
    db.table.return_value = table
    return db, table


def test_cmd_capacity_asks_sleep_on_first_checkin_of_day():
    print("\n── cmd_capacity — first check-in today asks sleep first ─────────")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import cmd_capacity

    db, _ = _make_capacity_db(today_checkin_rows=[])
    app_module._supabase = db
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    asyncio.run(cmd_capacity(update, context))

    text_sent = update.message.reply_text.call_args[0][0]
    check("asks about sleep, not capacity, on the first check-in", "sleep" in text_sent.lower())
    app_module._supabase = None


def test_cmd_capacity_skips_sleep_on_repeat_checkin():
    print("\n── cmd_capacity — later check-ins today skip straight to capacity ─")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import cmd_capacity
    from datetime import datetime
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("Australia/Brisbane")).date().isoformat()
    db, _ = _make_capacity_db(today_checkin_rows=[{"log_date": today, "checkin_type": "capacity"}])
    app_module._supabase = db
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    asyncio.run(cmd_capacity(update, context))

    text_sent = update.message.reply_text.call_args[0][0]
    check("asks about capacity directly, sleep already answered today", "capacity right now" in text_sent.lower())
    app_module._supabase = None


def _make_cb_update_and_context(callback_data: str):
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
    return update, context, query


def test_handle_capacity_callback_sleep_then_capacity_then_stimulation():
    print("\n── handle_capacity_callback — sl -> c -> t chain ─────────────────")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_capacity_callback

    app_module._supabase = MagicMock()

    update, context, query = _make_cb_update_and_context("ct|sl=u5")
    asyncio.run(handle_capacity_callback(update, context))
    text1 = query.edit_message_text.call_args[0][0]
    check("after sleep, asks capacity", "capacity right now" in text1.lower())
    kb1 = query.edit_message_text.call_args[1]["reply_markup"]
    check("capacity buttons still carry sl forward", kb1.inline_keyboard[0][0].callback_data.startswith("ct|sl=u5|c="))

    update, context, query = _make_cb_update_and_context("ct|sl=u5|c=g")
    asyncio.run(handle_capacity_callback(update, context))
    text2 = query.edit_message_text.call_args[0][0]
    check("after capacity, asks stimulation", "stimulation" in text2.lower())
    app_module._supabase = None


def test_handle_capacity_callback_regulation_then_emotional_then_ef():
    print("\n── handle_capacity_callback — r -> em -> e chain ─────────────────")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_capacity_callback

    app_module._supabase = MagicMock()

    update, context, query = _make_cb_update_and_context("ct|c=g|t=b|p=l|ps=5|r=s")
    asyncio.run(handle_capacity_callback(update, context))
    text1 = query.edit_message_text.call_args[0][0]
    check("after regulation (nervous system), asks emotional load", "emotional load" in text1.lower())

    update, context, query = _make_cb_update_and_context("ct|c=g|t=b|p=l|ps=5|r=s|em=l")
    asyncio.run(handle_capacity_callback(update, context))
    text2 = query.edit_message_text.call_args[0][0]
    check("after emotional, asks executive function", "think, decide" in text2.lower())
    app_module._supabase = None


def test_handle_capacity_callback_active_loads_then_social_then_compensation():
    print("\n── handle_capacity_callback — ld -> so -> cp chain (phase 2) ─────")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_capacity_callback

    db, table = _make_db()
    app_module._supabase = db

    update, context, query = _make_cb_update_and_context("ct|id=42|ld=0,1|next=1")
    asyncio.run(handle_capacity_callback(update, context))
    text1 = query.edit_message_text.call_args[0][0]
    check("after active loads (next), asks social capacity, not compensation yet", "social capacity" in text1.lower())

    update, context, query = _make_cb_update_and_context("ct|id=42|so=m")
    asyncio.run(handle_capacity_callback(update, context))
    text2 = query.edit_message_text.call_args[0][0]
    check("after social, asks compensation", "push, mask, or compensate" in text2.lower())
    payload = table.update.call_args[0][0]
    check("social_state written before moving on", payload.get("social_state") == "some")
    app_module._supabase = None


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

    test_burnout_tier_option_lists_populated_and_skippable()
    test_q_and_kb_burnout_framing()
    test_q_and_kb_body_signal_clarity()
    test_q_and_kb_predictability()
    test_write_deep_checkin_burnout_framing()
    test_write_deep_checkin_compensation_type_stores_canonical_values_not_labels()
    test_write_deep_checkin_body_clarity_and_predictability()
    test_deep_callback_mp_writes_early_and_asks_burnout_framing()
    test_deep_callback_bf_asks_compensation_type_multiselect()
    test_deep_callback_cpt_continue_asks_body_signal_clarity()
    test_deep_callback_cpt_toggle_without_continue_redraws_multiselect()
    test_deep_callback_bc_asks_predictability()
    test_deep_callback_pd_asks_recovery_duration()

    test_parse_cb_handles_pagination_field()
    test_capacity_callback_active_loads_redraw_passes_page_through()
    test_deep_callback_ua_continue_prompts_for_free_text_note()
    test_deep_callback_final_clears_pending_note_state()
    test_reminder_callback_no_duration_shows_picker()
    test_reminder_callback_with_duration_schedules_job()
    test_cmd_message_intercepts_pending_deep_note()

    test_q_sleep_lists_all_5_buckets()
    test_kb_sleep_callbacks_have_bare_base()
    test_kb_capacity_carries_sleep_forward_when_present()
    test_emotional_question_sits_between_regulation_and_executive_function()
    test_q_social_and_kb_social()
    test_base_from_includes_new_fields_in_canonical_order()
    test_write_quick_checkin_maps_new_fields()
    test_render_summary_includes_new_fields_when_present()
    test_cmd_capacity_asks_sleep_on_first_checkin_of_day()
    test_cmd_capacity_skips_sleep_on_repeat_checkin()
    test_handle_capacity_callback_sleep_then_capacity_then_stimulation()
    test_handle_capacity_callback_regulation_then_emotional_then_ef()
    test_handle_capacity_callback_active_loads_then_social_then_compensation()

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
