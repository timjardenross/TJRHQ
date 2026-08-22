"""
Tests for /guide — MY CAPACITY TODAY V02 WP08.

Covers guide.py's pure functions and app.py's handler wiring — the
recent-check-in reuse path, the 3-tap fallback, Accept/Another/Why, and
the max_minutes filter added to intervention_engine.rank_interventions.

Run from repo root:
    python telegram-bots/capacitybot/test_guide.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parents[2]))

from telegram_bots.capacitybot.guide import (
    STATE_TO_CAPACITY_CODE,
    STATE_TO_PAIN_CODE,
    STATE_TO_STIM_CODE,
    TIME_TO_MAX_MINUTES,
    kb_offer,
    parse_cb,
    render_offer,
    render_why,
)
from telegram_bots.capacitybot.intervention_engine import rank_interventions

PASS = "PASS"
FAIL = "FAIL"
_results: list[tuple[str, str]] = []


def check(label: str, condition: bool) -> bool:
    tag = PASS if condition else FAIL
    _results.append((tag, label))
    print(f"  [{tag}] {label}")
    return condition


# ── Pure functions ────────────────────────────────────────────────────────────

def test_state_to_code_reverse_maps_are_complete():
    print("\n── state->code reverse maps cover every capacity_checkins value ─")
    check("capacity: green/orange/red all map", set(STATE_TO_CAPACITY_CODE) == {"green", "orange", "red"})
    check("stimulation: low/balanced/high all map", set(STATE_TO_STIM_CODE) == {"low", "balanced", "high"})
    check("pain: all 4 states map", set(STATE_TO_PAIN_CODE) == {"low", "baseline", "elevated", "high"})


def test_time_to_max_minutes():
    print("\n── TIME_TO_MAX_MINUTES — short/medium capped, long uncapped ─────")
    check("under-10 caps at 10", TIME_TO_MAX_MINUTES["s"] == 10)
    check("10-30 caps at 30", TIME_TO_MAX_MINUTES["m"] == 30)
    check("30+ has no cap", TIME_TO_MAX_MINUTES["l"] is None)


def test_render_offer_shows_lever_and_description():
    print("\n── render_offer — shows the management-lever category + full text ─")
    text = render_offer({"title": "Rest", "full_description": "Rest for 20 minutes.",
                          "management_lever": "recover", "estimated_minutes": 20})
    check("lever category shown", "RECOVER" in text)
    check("full description shown", "Rest for 20 minutes." in text)
    check("no markdown asterisks (bot sends plain text)", "*" not in text)


def test_render_why_references_state():
    print("\n── render_why — explanation references the actual state ────────")
    text = render_why({"title": "Move somewhere quieter", "management_lever": "reduce_load"},
                       capacity_state="red", stimulation_state="high", pain_state=None)
    check("references capacity", "depleted" in text.lower())
    check("references stimulation", "too much" in text.lower())


def test_kb_offer_hides_why_after_shown():
    print("\n── kb_offer — 'Why this?' disappears once already shown ─────────")
    kb1 = kb_offer("quieter_place", showing_why=False)
    kb2 = kb_offer("quieter_place", showing_why=True)
    texts1 = [b.text for row in kb1.inline_keyboard for b in row]
    texts2 = [b.text for row in kb2.inline_keyboard for b in row]
    check("Why this? present on first offer", any("Why" in t for t in texts1))
    check("Why this? absent once already shown", not any("Why" in t for t in texts2))
    check("Accept always present", any("I'll do that" in t for t in texts1) and any("I'll do that" in t for t in texts2))


def test_parse_cb_guide_fields():
    print("\n── parse_cb — cg| fields round-trip ──────────────────────────────")
    f = parse_cb("cg|cap=g|stim=b|pain=l|t=m")
    check("all 4 fields parsed", f == {"cap": "g", "stim": "b", "pain": "l", "t": "m"})


# ── rank_interventions max_minutes filter ────────────────────────────────────

def _make_engine_db(interventions, events=None):
    db = MagicMock()
    _table_mocks: dict[str, MagicMock] = {}

    def table_side_effect(name):
        if name in _table_mocks:
            return _table_mocks[name]
        t = MagicMock()
        if name == "capacity_interventions":
            sel = MagicMock()
            sel.eq.return_value.contains.return_value.execute.return_value = MagicMock(data=interventions)
            sel.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=interventions)
            sel.eq.return_value.execute.return_value = MagicMock(data=interventions)
            t.select.return_value = sel
        elif name == "capacity_intervention_events":
            sel = MagicMock()
            sel.in_.return_value.not_.is_.return_value.order.return_value.limit.return_value.execute.return_value = \
                MagicMock(data=events or [])
            t.select.return_value = sel
        _table_mocks[name] = t
        return t

    db.table.side_effect = table_side_effect
    return db


def _iv(iid, minutes):
    return dict(
        intervention_id=iid, title=iid, target_states=[], capacity_allowed=["green", "orange", "red"],
        stimulation_effect="neutral", pain_compatible=True, executive_effort="low",
        estimated_minutes=minutes,
    )


def test_rank_interventions_max_minutes_excludes_too_long():
    print("\n── rank_interventions — max_minutes excludes longer options ─────")
    db = _make_engine_db([_iv("quick", 5), _iv("slow", 45), _iv("no_duration", None)])
    ranked = asyncio.run(rank_interventions(db, capacity_state="green", max_minutes=10))
    ids = [r["intervention_id"] for r in ranked]
    check("short option included", "quick" in ids)
    check("long option excluded", "slow" not in ids)
    check("no-fixed-duration option never excluded by the time filter", "no_duration" in ids)


def test_rank_interventions_no_max_minutes_includes_everything():
    print("\n── rank_interventions — max_minutes=None applies no filter ──────")
    db = _make_engine_db([_iv("quick", 5), _iv("slow", 45)])
    ranked = asyncio.run(rank_interventions(db, capacity_state="green", max_minutes=None))
    check("both included when no time constraint given", len(ranked) == 2)


# ── Wiring — app.py handlers ──────────────────────────────────────────────────

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


def test_guide_callback_fallback_asks_stim_then_pain_then_time():
    print("\n── handle_guide_callback — 3-tap fallback sequence ───────────────")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_guide_callback

    app_module._supabase = _make_engine_db([_iv("rest_20", 20)])

    update, context, query = _make_update_and_context("cg|cap=g")
    asyncio.run(handle_guide_callback(update, context))
    check("asks stimulation next", "stimulation" in query.edit_message_text.call_args[0][0].lower())

    update, context, query = _make_update_and_context("cg|cap=g|stim=b")
    asyncio.run(handle_guide_callback(update, context))
    check("asks pain next", "pain" in query.edit_message_text.call_args[0][0].lower())

    update, context, query = _make_update_and_context("cg|cap=g|stim=b|pain=l")
    asyncio.run(handle_guide_callback(update, context))
    check("asks time next", "time" in query.edit_message_text.call_args[0][0].lower())

    update, context, query = _make_update_and_context("cg|cap=g|stim=b|pain=l|t=m")
    asyncio.run(handle_guide_callback(update, context))
    check("offers an intervention after time is answered", context.user_data.get("guide_current") == "rest_20")
    check("flow context decoded correctly", context.user_data["guide_ctx"]["capacity_state"] == "green")
    check("max_minutes decoded from time bucket", context.user_data["guide_ctx"]["max_minutes"] == 30)
    app_module._supabase = None


def test_guide_offer_another_excludes_and_reoffers():
    print("\n── handle_guide_offer_callback — Another option excludes + re-offers ─")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_guide_offer_callback

    app_module._supabase = _make_engine_db([_iv("a", 10), _iv("b", 10)])
    update, context, query = _make_update_and_context("cgi|iid=a|act=another")
    context.user_data["guide_ctx"] = {"capacity_state": "green", "stimulation_state": None,
                                       "pain_state": None, "max_minutes": None}
    context.user_data["guide_seen"] = []

    asyncio.run(handle_guide_offer_callback(update, context))

    check("declined id recorded", "a" in context.user_data["guide_seen"])
    check("offers a different intervention", context.user_data.get("guide_current") != "a")
    app_module._supabase = None


def test_guide_offer_why_shows_explanation_and_hides_why_button():
    print("\n── handle_guide_offer_callback — Why this? shows explanation ────")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_guide_offer_callback

    app_module._supabase = _make_engine_db([_iv("quiet", 10)])
    update, context, query = _make_update_and_context("cgi|iid=quiet|act=why")
    context.user_data["guide_ctx"] = {"capacity_state": "red", "stimulation_state": "high", "pain_state": None}

    asyncio.run(handle_guide_offer_callback(update, context))

    text = query.edit_message_text.call_args[0][0]
    check("explanation mentions capacity state", "depleted" in text.lower())
    kb = query.edit_message_text.call_args[1]["reply_markup"]
    btn_texts = [b.text for row in kb.inline_keyboard for b in row]
    check("Why button no longer offered", not any("Why" in t for t in btn_texts))
    app_module._supabase = None


def test_guide_offer_accept_logs_event_source_guide():
    print("\n── handle_guide_offer_callback — accept logs source=guide ───────")
    import telegram_bots.capacitybot.app as app_module
    from telegram_bots.capacitybot.app import handle_guide_offer_callback

    db = _make_engine_db([_iv("quiet", 10)])
    db.table("capacity_interventions").insert = MagicMock()
    ev_table = MagicMock()
    ev_table.insert.return_value.execute.return_value = MagicMock(data=[{"id": 99}])
    orig_side_effect = db.table.side_effect

    def side_effect(name):
        if name == "capacity_intervention_events":
            return ev_table
        return orig_side_effect(name)
    db.table.side_effect = side_effect

    app_module._supabase = db
    update, context, query = _make_update_and_context("cgi|iid=quiet|act=accept")
    context.user_data["guide_ctx"] = {"capacity_state": "orange", "stimulation_state": None, "pain_state": None}

    asyncio.run(handle_guide_offer_callback(update, context))

    check("event insert called", ev_table.insert.called)
    payload = ev_table.insert.call_args[0][0]
    check("source is guide", payload["source"] == "guide")
    check("capacity_before carried through", payload["capacity_before"] == "orange")
    check("flow state cleared after accept", "guide_ctx" not in context.user_data)
    app_module._supabase = None


def main():
    print("=" * 60)
    print("/guide — V02 WP08 test suite")
    print("=" * 60)

    test_state_to_code_reverse_maps_are_complete()
    test_time_to_max_minutes()
    test_render_offer_shows_lever_and_description()
    test_render_why_references_state()
    test_kb_offer_hides_why_after_shown()
    test_parse_cb_guide_fields()
    test_rank_interventions_max_minutes_excludes_too_long()
    test_rank_interventions_no_max_minutes_includes_everything()
    test_guide_callback_fallback_asks_stim_then_pain_then_time()
    test_guide_offer_another_excludes_and_reoffers()
    test_guide_offer_why_shows_explanation_and_hides_why_button()
    test_guide_offer_accept_logs_event_source_guide()

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
