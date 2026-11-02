#!/usr/bin/env python3
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
from unittest.mock import AsyncMock, MagicMock, patch

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
    NATURAL_REGULATION_OPTIONS,
    PAGE_SIZE,
    PREDICTABILITY_OPTIONS,
    RECOVERY_FACTORS,
    SENSORY_CHANNEL_KEYS,
    SENSORY_CHANNEL_LABELS,
    SENSORY_CHANNEL_SHORT,
    SENSORY_CHANNELS,
    SENSORY_RESPONSE_OPTIONS,
    UNHELPFUL_ACTIONS_OPTIONS,
    base_from,
    kb_after_quick,
    kb_body_signal_clarity,
    kb_burnout_framing,
    kb_capacity,
    kb_cpap,
    kb_deep_emotional,
    kb_deep_multiselect,
    kb_deep_social,
    kb_multiselect,
    kb_natural_regulation,
    kb_predictability,
    kb_sensory_channel_response,
    kb_suppressed_regulation,
    parse_cb,
    q_active_loads,
    q_body_signal_clarity,
    q_burnout_framing,
    q_capacity,
    q_cpap,
    q_emotional,
    q_executive_function,
    q_natural_regulation,
    q_predictability,
    q_sensory_channel_response,
    q_social,
    q_suppressed_regulation,
    render_multiselect_question,
    render_question,
    write_deep_checkin,
    write_deep_sensory_channel,
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


def test_deep_callback_mp_writes_early_and_asks_emotional_load():
    print("\n── handle_capacity_deep_callback — mp answered -> asks emotional load ─")
    from telegram_bots.capacitybot.app import handle_capacity_deep_callback

    update, context, query = _make_update_and_context("ctd|id=99|lc=p|uc=y|mp=n")
    # The handler writes the row as soon as mp is answered. Without a mocked database it would hit
    # the real client and reply "Could not save", so this test only passed with live credentials.
    with patch("telegram_bots.capacitybot.app._get_supabase", return_value=MagicMock()):
        asyncio.run(handle_capacity_deep_callback(update, context))

    text_arg = query.edit_message_text.call_args[0][0]
    check("asks emotional load next (moved here from the quick check-in), not recovery duration",
          "emotional load" in text_arg.lower())
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


def test_deep_callback_pd_asks_sensory_channels():
    print("\n── handle_capacity_deep_callback — pd answered -> asks sensory channels (V3 Mission 3) ─")
    from telegram_bots.capacitybot.app import handle_capacity_deep_callback

    update, context, query = _make_update_and_context("ctd|id=99|pd=su")
    asyncio.run(handle_capacity_deep_callback(update, context))

    text_arg = query.edit_message_text.call_args[0][0]
    check("asks the sensory-channels question next, not recovery duration",
          "stand out" in text_arg.lower())
    check("all 8 sensory channels present in body",
          all(label in text_arg for label in SENSORY_CHANNEL_LABELS))


# ── V3 Mission 3 — Sensory + Regulation Profile (§10/§11) ───────────────────

def test_sensory_channel_option_lists_populated():
    print("\n── sensory channel option lists — populated, index/label/short in sync ─")
    check("SENSORY_CHANNELS has 8 channels", len(SENSORY_CHANNELS) == 8)
    check("SENSORY_CHANNEL_KEYS/LABELS/SHORT same length",
          len(SENSORY_CHANNEL_KEYS) == len(SENSORY_CHANNEL_LABELS) == len(SENSORY_CHANNEL_SHORT) == 8)
    check("SENSORY_RESPONSE_OPTIONS has 5 responses (V3 doc §10)", len(SENSORY_RESPONSE_OPTIONS) == 5)
    check("sensory response options include an 'unknown' value",
          any(code == "uk" for code, _ in SENSORY_RESPONSE_OPTIONS))
    check("NATURAL_REGULATION_OPTIONS has 14 options (V3 doc §11)", len(NATURAL_REGULATION_OPTIONS) == 14)
    check("natural regulation options include an 'I don't know' value",
          any(code == "dk" for code, _ in NATURAL_REGULATION_OPTIONS))


def test_q_and_kb_sensory_channel_response():
    print("\n── q_sensory_channel_response/kb_sensory_channel_response ───────")
    text = q_sensory_channel_response("0")
    check("names the flagged channel (auditory) in the question",
          SENSORY_CHANNEL_LABELS[0] in text)
    check("all 5 response options present in body",
          all(label in text for _, label in SENSORY_RESPONSE_OPTIONS))
    kb = kb_sensory_channel_response("99", "0", "2,4")
    buttons = [b for row in kb.inline_keyboard for b in row]
    check("5 buttons, one per response option", len(buttons) == 5)
    check("callback carries row id, current channel idx, and remaining queue",
          buttons[0].callback_data == "ctd|id=99|sci=0|scq=2,4|scr=ra")


def test_q_and_kb_natural_regulation():
    print("\n── q_natural_regulation/kb_natural_regulation ────────────────────")
    text = q_natural_regulation()
    check("all 14 natural-regulation options present in body",
          all(label in text for _, label in NATURAL_REGULATION_OPTIONS))
    kb = kb_natural_regulation("ctd|id=42")
    buttons = [b for row in kb.inline_keyboard for b in row]
    check("15 buttons: 14 options + Skip", len(buttons) == 15)
    check("Skip button present", any("Skip" in b.text for b in buttons))


def test_q_and_kb_suppressed_regulation():
    print("\n── q_suppressed_regulation/kb_suppressed_regulation ──────────────")
    text = q_suppressed_regulation()
    check("frames as compensation-cost learning, not correction",
          "compensation" in text.lower() and "fix" not in text.lower())
    kb = kb_suppressed_regulation("ctd|id=42")
    buttons = [b for row in kb.inline_keyboard for b in row]
    check("Yes/No/Skip — 3 buttons", len(buttons) == 3)
    check("callbacks carry the row id and sr code",
          buttons[0].callback_data == "ctd|id=42|sr=y")


def test_write_deep_checkin_natural_regulation_and_suppressed():
    print("\n── write_deep_checkin — natural_regulation_response + suppressed_regulation_response ─")
    db, table = _make_db()
    asyncio.run(write_deep_checkin(db, "7", {"nr": "ba", "sr": "y"}))
    payload = table.update.call_args[0][0]
    check("natural_regulation_response decoded", payload.get("natural_regulation_response") == "be_alone")
    check("suppressed_regulation_response decoded to boolean True", payload.get("suppressed_regulation_response") is True)

    db2, table2 = _make_db()
    asyncio.run(write_deep_checkin(db2, "7", {"nr": "skip", "sr": "skip"}))
    payload2 = table2.update.call_args[0][0]
    check("nr=skip is not written", "natural_regulation_response" not in payload2)
    check("sr=skip is not written", "suppressed_regulation_response" not in payload2)


def test_write_deep_sensory_channel_merges_without_clobbering():
    print("\n── write_deep_sensory_channel — read-merge-write, doesn't clobber prior channels ─")
    db, table = _make_db()
    table.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
        MagicMock(data=[{"sensory_channels": {"auditory": "reduce_avoid"}}])
    ok, err = asyncio.run(write_deep_sensory_channel(db, "7", "visual", "neutral"))
    check("write reports success", ok)
    check("no error message", err is None)
    payload = table.update.call_args[0][0]
    check("previously-set channel preserved", payload["sensory_channels"].get("auditory") == "reduce_avoid")
    check("new channel merged in", payload["sensory_channels"].get("visual") == "neutral")


def test_deep_callback_sc_skip_goes_straight_to_natural_regulation():
    print("\n── handle_capacity_deep_callback — sc Done with nothing flagged -> natural regulation ─")
    from telegram_bots.capacitybot.app import handle_capacity_deep_callback

    update, context, query = _make_update_and_context("ctd|id=99|sc=|done=1")
    asyncio.run(handle_capacity_deep_callback(update, context))

    text_arg = query.edit_message_text.call_args[0][0]
    check("skips the per-channel loop entirely, asks natural regulation next",
          "want right now" in text_arg.lower())


def test_deep_callback_sc_toggle_without_continue_redraws_multiselect():
    print("\n── handle_capacity_deep_callback — sc toggle (no next/done) redraws ─")
    from telegram_bots.capacitybot.app import handle_capacity_deep_callback

    update, context, query = _make_update_and_context("ctd|id=99|sc=0|pg=0")
    asyncio.run(handle_capacity_deep_callback(update, context))

    text_arg = query.edit_message_text.call_args[0][0]
    check("still on the sensory-channels question", "stand out" in text_arg.lower())


def test_deep_callback_sc_flagged_channels_asks_first_channel_response():
    print("\n── handle_capacity_deep_callback — sc Continue with 2 flagged -> asks first channel ─")
    from telegram_bots.capacitybot.app import handle_capacity_deep_callback

    update, context, query = _make_update_and_context("ctd|id=99|sc=0,3|next=1")
    asyncio.run(handle_capacity_deep_callback(update, context))

    text_arg = query.edit_message_text.call_args[0][0]
    check("asks about the first flagged channel (index 0 = auditory)",
          SENSORY_CHANNEL_LABELS[0] in text_arg)
    kb_arg = query.edit_message_text.call_args[1].get("reply_markup")
    check("remaining queue (index 3) carried in the callback base",
          all("scq=3" in b.callback_data for row in kb_arg.inline_keyboard for b in row))


def test_deep_callback_scr_advances_to_next_flagged_channel():
    print("\n── handle_capacity_deep_callback — scr answered, queue not empty -> next channel ─")
    from telegram_bots.capacitybot.app import handle_capacity_deep_callback

    db, table = _make_db()
    table.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[{}])
    import telegram_bots.capacitybot.app as app_module
    app_module._supabase = db

    update, context, query = _make_update_and_context("ctd|id=99|sci=0|scq=3|scr=ra")
    asyncio.run(handle_capacity_deep_callback(update, context))

    text_arg = query.edit_message_text.call_args[0][0]
    check("moves on to the next flagged channel (index 3 = smell)",
          SENSORY_CHANNEL_LABELS[3] in text_arg)
    app_module._supabase = None


def test_deep_callback_scr_last_channel_advances_to_natural_regulation():
    print("\n── handle_capacity_deep_callback — scr answered, queue empty -> natural regulation ─")
    from telegram_bots.capacitybot.app import handle_capacity_deep_callback

    db, table = _make_db()
    table.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[{}])
    import telegram_bots.capacitybot.app as app_module
    app_module._supabase = db

    update, context, query = _make_update_and_context("ctd|id=99|sci=3|scq=|scr=nu")
    asyncio.run(handle_capacity_deep_callback(update, context))

    text_arg = query.edit_message_text.call_args[0][0]
    check("empty queue -> asks natural regulation, not another channel",
          "want right now" in text_arg.lower())
    app_module._supabase = None


def test_deep_callback_nr_asks_suppressed_regulation():
    print("\n── handle_capacity_deep_callback — nr answered -> asks suppressed-regulation ─")
    from telegram_bots.capacitybot.app import handle_capacity_deep_callback

    update, context, query = _make_update_and_context("ctd|id=99|nr=rs")
    asyncio.run(handle_capacity_deep_callback(update, context))

    text_arg = query.edit_message_text.call_args[0][0]
    check("asks the suppressed-regulation question next", "stopping yourself" in text_arg.lower())


def test_deep_callback_sr_asks_recovery_duration():
    print("\n── handle_capacity_deep_callback — sr answered -> asks recovery duration ─")
    from telegram_bots.capacitybot.app import handle_capacity_deep_callback

    update, context, query = _make_update_and_context("ctd|id=99|sr=n")
    asyncio.run(handle_capacity_deep_callback(update, context))

    text_arg = query.edit_message_text.call_args[0][0]
    check("asks recovery-duration question, rejoining the pre-existing flow",
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

def test_q_cpap_asks_yes_no_with_skip():
    print("\n── q_cpap — one yes/no question, skippable ───────────────────────")
    text = q_cpap()
    check("asks about CPAP", "cpap" in text.lower())
    for label in ("Yes", "No", "Skip"):
        check(f"'{label}' present", label in text)
    check("no hour buckets any more", "5-6h" not in text)


def test_kb_cpap_callbacks_have_bare_base():
    print("\n── kb_cpap — always the true start of the flow (bare 'ct' base) ──")
    cbs = [b.callback_data for row in kb_cpap().inline_keyboard for b in row]
    check("callbacks have no prior fields, just cx=", cbs == ["ct|cx=y", "ct|cx=n", "ct|cx=x"])


def test_kb_capacity_carries_cpap_forward_when_present():
    print("\n── kb_capacity(f) — carries cx forward after the CPAP question ───")
    cb = kb_capacity({"cx": "y"}).inline_keyboard[0][0].callback_data
    check("cx carried into the capacity callback", cb.startswith("ct|cx=y|c="))
    cb2 = kb_capacity().inline_keyboard[0][0].callback_data
    check("no cx segment when the question wasn't asked (repeat check-ins)", cb2 == "ct|c=g")


def test_emotional_question_is_in_go_deeper():
    print("\n── q_emotional/kb_deep_emotional — write-through, id-only base ────")
    text = q_emotional()
    for label in ("Light", "Moderate", "Heavy", "Overwhelming"):
        check(f"emotional option '{label}' in body", label in text)
    cbs = [b.callback_data for row in kb_deep_emotional("42").inline_keyboard for b in row]
    check("deep base is id-only", cbs[0] == "ctd|id=42|em=l")
    check("skippable", cbs[-1] == "ctd|id=42|em=x")


def test_q_social_and_kb_deep_social():
    print("\n── q_social/kb_deep_social — write-through, id-only base ─────────")
    text = q_social()
    for label in ("Plenty", "Some", "Limited", "None left"):
        check(f"social option '{label}' in body", label in text)
    cbs = [b.callback_data for row in kb_deep_social("42").inline_keyboard for b in row]
    check("deep base is id-only", cbs[0] == "ctd|id=42|so=g")
    check("skippable", cbs[-1] == "ctd|id=42|so=x")


def test_kb_after_quick_offers_suggestions_as_an_option():
    print("\n── kb_after_quick — suggestions are optional, not a question ─────")
    cbs = [b.callback_data for row in kb_after_quick("42").inline_keyboard for b in row]
    check("offers suggestions", "ct|id=42|sug=1" in cbs)
    check("offers go deeper", "ctd|id=42" in cbs)


def test_base_from_includes_new_fields_in_canonical_order():
    print("\n── base_from — sl/em/so slot into _FIELD_ORDER correctly ────────")
    f = {"sl": "u5", "cx": "y", "c": "g", "t": "b", "em": "l", "e": "g", "so": "m"}
    base = base_from(f)
    check("sleep first", base.index("sl=") < base.index("c="))
    check("cpap before capacity", base.index("cx=") < base.index("c=g"))
    check("emotional between regulation-slot and executive_function", base.index("em=") < base.index("e="))
    check("social present", "so=m" in base)


def test_write_quick_checkin_stores_cpap_and_skip_stores_nothing():
    print("\n── write_quick_checkin — cpap_used true/false, skip stores nothing ─")
    for code, expected in (("y", True), ("n", False)):
        db, table = _make_db()
        asyncio.run(write_quick_checkin(db, {"id": "7", "cx": code}))
        check(f"cx={code} -> {expected}", table.update.call_args[0][0].get("cpap_used") is expected)
    db, table = _make_db()
    asyncio.run(write_quick_checkin(db, {"id": "7", "cx": "x"}))
    check("skip -> nothing stored", "cpap_used" not in table.update.call_args[0][0])


def test_write_deep_checkin_stores_emotional_and_social_and_skip_stores_nothing():
    print("\n── write_deep_checkin — emotional/social moved here ──────────────")
    db, table = _make_db()
    asyncio.run(write_deep_checkin(db, "7", {"em": "h"}))
    check("emotional stored", table.update.call_args[0][0].get("emotional_state") == "heavy")
    db, table = _make_db()
    asyncio.run(write_deep_checkin(db, "7", {"so": "n"}))
    check("social stored", table.update.call_args[0][0].get("social_state") == "none")
    db, table = _make_db()
    asyncio.run(write_deep_checkin(db, "7", {"em": "x", "so": "x"}))
    payload = table.update.call_args[0][0]
    check("skip stores nothing", "emotional_state" not in payload and "social_state" not in payload)


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
        "sleep_state": "under_5", "emotional_state": "overwhelming", "social_state": "plenty", "cpap_used": False,
    })
    check("cpap line present", "CPAP: No" in text)
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


def test_cmd_capacity_asks_cpap_on_first_checkin_of_day():
    print("\n── cmd_capacity — first check-in today asks the CPAP question first ─")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import cmd_capacity

    db, _ = _make_capacity_db(today_checkin_rows=[])
    app_module._supabase = db
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    asyncio.run(cmd_capacity(update, context))

    text_sent = update.message.reply_text.call_args[0][0]
    check("asks about CPAP, not capacity, on the first check-in", "cpap" in text_sent.lower())
    app_module._supabase = None


def test_cmd_capacity_skips_cpap_on_repeat_checkin():
    print("\n── cmd_capacity — later check-ins today skip straight to capacity ─")
    from datetime import datetime
    from zoneinfo import ZoneInfo

    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import cmd_capacity

    today = datetime.now(ZoneInfo("Australia/Melbourne")).date().isoformat()
    db, _ = _make_capacity_db(today_checkin_rows=[{"log_date": today, "checkin_type": "capacity"}])
    app_module._supabase = db
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    asyncio.run(cmd_capacity(update, context))

    text_sent = update.message.reply_text.call_args[0][0]
    check("asks about capacity directly, CPAP already answered today", "capacity right now" in text_sent.lower())
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


def test_handle_capacity_callback_cpap_then_capacity_then_stimulation():
    print("\n── handle_capacity_callback — cx -> c -> t chain ─────────────────")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_capacity_callback

    app_module._supabase = MagicMock()

    update, context, query = _make_cb_update_and_context("ct|cx=y")
    asyncio.run(handle_capacity_callback(update, context))
    text1 = query.edit_message_text.call_args[0][0]
    check("after CPAP, asks capacity", "capacity right now" in text1.lower())
    kb1 = query.edit_message_text.call_args[1]["reply_markup"]
    check("capacity buttons still carry cx forward", kb1.inline_keyboard[0][0].callback_data.startswith("ct|cx=y|c="))

    update, context, query = _make_cb_update_and_context("ct|cx=y|c=g")
    asyncio.run(handle_capacity_callback(update, context))
    text2 = query.edit_message_text.call_args[0][0]
    check("after capacity, asks stimulation", "stimulation" in text2.lower())
    app_module._supabase = None


def test_handle_capacity_callback_regulation_goes_straight_to_executive_function():
    print("\n── handle_capacity_callback — r -> e (emotional moved to Go deeper) ─")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_capacity_callback

    app_module._supabase = MagicMock()

    update, context, query = _make_cb_update_and_context("ct|c=g|t=b|p=l|ps=5|r=s")
    asyncio.run(handle_capacity_callback(update, context))
    text1 = query.edit_message_text.call_args[0][0]
    check("after regulation, asks executive function", "think, decide" in text1.lower())
    check("emotional load is no longer asked in the quick check-in", "emotional load" not in text1.lower())

    update, context, query = _make_cb_update_and_context("ct|c=g|t=b|p=l|ps=5|r=s|em=l")
    asyncio.run(handle_capacity_callback(update, context))
    text2 = query.edit_message_text.call_args[0][0]
    check("an old in-flight emotional button still carries on to executive function", "think, decide" in text2.lower())
    app_module._supabase = None


def test_handle_capacity_callback_active_loads_then_compensation_then_summary_with_suggestions_option():
    print("\n── handle_capacity_callback — ld -> cp -> summary + optional suggestions ──")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_capacity_callback

    db, table = _make_db()
    table.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"id": 42, "capacity_state": "orange"}])
    app_module._supabase = db

    update, context, query = _make_cb_update_and_context("ct|id=42|ld=0,1|next=1")
    asyncio.run(handle_capacity_callback(update, context))
    text1 = query.edit_message_text.call_args[0][0]
    check("after active loads (next), asks compensation (social moved to Go deeper)", "push, mask, or compensate" in text1.lower())
    check("social capacity is no longer asked", "social capacity" not in text1.lower())

    update, context, query = _make_cb_update_and_context("ct|id=42|cp=m")
    asyncio.run(handle_capacity_callback(update, context))
    check("compensation is written", table.update.call_args[0][0].get("compensation_load") == "moderate")
    kb = query.edit_message_text.call_args[1]["reply_markup"]
    cbs = [b.callback_data for row in kb.inline_keyboard for b in row]
    check("the quick check-in ends with a summary and a suggestions button", "ct|id=42|sug=1" in cbs)
    check("needs is not asked automatically", "what do you need" not in query.edit_message_text.call_args[0][0].lower())

    update, context, query = _make_cb_update_and_context("ct|id=42|sug=1")
    asyncio.run(handle_capacity_callback(update, context))
    check("tapping suggestions asks what would help", "help your system" in query.edit_message_text.call_args[0][0].lower())
    app_module._supabase = None


def test_midday_is_one_tap():
    print("\n── handle_midday_callback — capacity answer saves the check-in ───")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_midday_callback

    db, table = _make_db()
    app_module._supabase = db
    update, context, query = _make_cb_update_and_context("cm|c=o")
    asyncio.run(handle_midday_callback(update, context))
    payload = table.insert.call_args[0][0]
    check("saved on the first tap", payload.get("checkin_type") == "midday" and payload.get("capacity_state") == "orange")
    check("no follow-up question", "saved" in query.edit_message_text.call_args[0][0].lower())
    app_module._supabase = None


def test_deep_callback_mp_now_asks_emotional_then_social_then_burnout_framing():
    print("\n── handle_capacity_deep_callback — mp -> em -> so -> framing ─────")
    from telegram_bots.capacitybot.app import handle_capacity_deep_callback

    db, table = _make_db()
    import telegram_bots.capacitybot.app as app_module
    app_module._supabase = db

    update, context, query = _make_update_and_context("ctd|id=99|lc=p|uc=y|mp=n")
    asyncio.run(handle_capacity_deep_callback(update, context))
    check("after masking, asks emotional load", "emotional load" in query.edit_message_text.call_args[0][0].lower())

    update, context, query = _make_update_and_context("ctd|id=99|em=h")
    asyncio.run(handle_capacity_deep_callback(update, context))
    check("after emotional, asks social capacity", "social capacity" in query.edit_message_text.call_args[0][0].lower())
    check("emotional written", table.update.call_args[0][0].get("emotional_state") == "heavy")

    update, context, query = _make_update_and_context("ctd|id=99|so=x")
    asyncio.run(handle_capacity_deep_callback(update, context))
    check("after social (skipped), asks burnout framing", "frame this period" in query.edit_message_text.call_args[0][0].lower())
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
    test_deep_callback_mp_writes_early_and_asks_emotional_load()
    test_deep_callback_bf_asks_compensation_type_multiselect()
    test_deep_callback_cpt_continue_asks_body_signal_clarity()
    test_deep_callback_cpt_toggle_without_continue_redraws_multiselect()
    test_deep_callback_bc_asks_predictability()
    test_deep_callback_pd_asks_sensory_channels()

    test_sensory_channel_option_lists_populated()
    test_q_and_kb_sensory_channel_response()
    test_q_and_kb_natural_regulation()
    test_q_and_kb_suppressed_regulation()
    test_write_deep_checkin_natural_regulation_and_suppressed()
    test_write_deep_sensory_channel_merges_without_clobbering()
    test_deep_callback_sc_skip_goes_straight_to_natural_regulation()
    test_deep_callback_sc_toggle_without_continue_redraws_multiselect()
    test_deep_callback_sc_flagged_channels_asks_first_channel_response()
    test_deep_callback_scr_advances_to_next_flagged_channel()
    test_deep_callback_scr_last_channel_advances_to_natural_regulation()
    test_deep_callback_nr_asks_suppressed_regulation()
    test_deep_callback_sr_asks_recovery_duration()

    test_parse_cb_handles_pagination_field()
    test_capacity_callback_active_loads_redraw_passes_page_through()
    test_deep_callback_ua_continue_prompts_for_free_text_note()
    test_deep_callback_final_clears_pending_note_state()
    test_reminder_callback_no_duration_shows_picker()
    test_reminder_callback_with_duration_schedules_job()
    test_cmd_message_intercepts_pending_deep_note()

    test_q_cpap_asks_yes_no_with_skip()
    test_kb_cpap_callbacks_have_bare_base()
    test_kb_capacity_carries_cpap_forward_when_present()
    test_emotional_question_is_in_go_deeper()
    test_q_social_and_kb_deep_social()
    test_kb_after_quick_offers_suggestions_as_an_option()
    test_write_quick_checkin_stores_cpap_and_skip_stores_nothing()
    test_write_deep_checkin_stores_emotional_and_social_and_skip_stores_nothing()
    test_base_from_includes_new_fields_in_canonical_order()
    test_write_quick_checkin_maps_new_fields()
    test_render_summary_includes_new_fields_when_present()
    test_cmd_capacity_asks_cpap_on_first_checkin_of_day()
    test_cmd_capacity_skips_cpap_on_repeat_checkin()
    test_handle_capacity_callback_cpap_then_capacity_then_stimulation()
    test_handle_capacity_callback_regulation_goes_straight_to_executive_function()
    test_handle_capacity_callback_active_loads_then_compensation_then_summary_with_suggestions_option()
    test_midday_is_one_tap()
    test_deep_callback_mp_now_asks_emotional_then_social_then_burnout_framing()

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
