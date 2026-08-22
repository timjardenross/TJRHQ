"""
Tests for /distract + /protocols — MY CAPACITY TODAY V02 WP09.

Run from repo root:
    python telegram-bots/capacitybot/test_distract.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parents[2]))

from telegram_bots.capacitybot.distract import (
    _TIER_ACTIVITIES,
    fetch_protocol,
    fetch_protocol_steps,
    fetch_protocols,
    parse_cb,
    pick_activity,
    render_activity,
    render_protocol,
)

PASS = "PASS"
FAIL = "FAIL"
_results: list[tuple[str, str]] = []


def check(label: str, condition: bool) -> bool:
    tag = PASS if condition else FAIL
    _results.append((tag, label))
    print(f"  [{tag}] {label}")
    return condition


# ── Distraction mode ──────────────────────────────────────────────────────────

def test_tiers_are_all_populated():
    print("\n── all 3 capacity tiers have activities ─────────────────────────")
    for tier in ("r", "o", "g"):
        check(f"tier '{tier}' has activities", len(_TIER_ACTIVITIES[tier]) > 0)


def test_pick_activity_returns_from_correct_tier():
    print("\n── pick_activity — returns something from the requested tier ────")
    for tier in ("r", "o", "g"):
        activity = pick_activity(tier)
        check(f"tier '{tier}' pick is a real member of that tier", activity in _TIER_ACTIVITIES[tier])


def test_pick_activity_respects_exclude():
    print("\n── pick_activity — exclude avoids repeating the same suggestion ─")
    tier = "r"
    all_activities = list(_TIER_ACTIVITIES[tier])
    exclude_all_but_one = all_activities[:-1]
    activity = pick_activity(tier, exclude=exclude_all_but_one)
    check("returns the one remaining un-excluded activity", activity == all_activities[-1])


def test_pick_activity_falls_back_when_everything_excluded():
    print("\n── pick_activity — exhausting the tier still returns something ──")
    tier = "o"
    activity = pick_activity(tier, exclude=list(_TIER_ACTIVITIES[tier]))
    check("falls back to the full tier rather than returning None", activity in _TIER_ACTIVITIES[tier])


def test_render_activity_offers_one_thing_not_a_list():
    print("\n── render_activity — spec §17: ONE bounded activity ─────────────")
    text = render_activity("g", "A creative activity")
    check("mentions exactly the one chosen activity", "A creative activity" in text)
    check("no numbered list of alternatives shown", not any(f"{i}." in text for i in range(1, 6)))


def test_parse_cb_distract_fields():
    print("\n── parse_cb — cd|/cdi| fields round-trip ─────────────────────────")
    f = parse_cb("cdi|cap=o|act=another")
    check("tier parsed", f.get("cap") == "o")
    check("action parsed", f.get("act") == "another")


# ── Rescue protocols — mocked DB ─────────────────────────────────────────────

def _make_db(protocols=None, steps=None):
    db = MagicMock()

    def table_side_effect(name):
        t = MagicMock()
        if name == "capacity_rescue_protocols":
            sel = MagicMock()
            sel.eq.return_value.execute.return_value = MagicMock(data=protocols or [])
            sel.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=protocols or [])
            t.select.return_value = sel
        elif name == "capacity_protocol_steps":
            sel = MagicMock()
            sel.eq.return_value.execute.return_value = MagicMock(data=steps or [])
            t.select.return_value = sel
        return t

    db.table.side_effect = table_side_effect
    return db


def test_fetch_protocols_returns_enabled_only():
    print("\n── fetch_protocols — returns the seeded default protocols ───────")
    protocols = [{"id": 1, "protocol_key": "office_overload", "title": "OFFICE OVERLOAD"}]
    db = _make_db(protocols=protocols)
    result = asyncio.run(fetch_protocols(db))
    check("returns the protocol list", result == protocols)


def test_fetch_protocols_no_db_returns_empty():
    print("\n── fetch_protocols — no Supabase, empty list not a crash ────────")
    result = asyncio.run(fetch_protocols(None))
    check("empty list, no exception", result == [])


def test_fetch_protocol_by_id():
    print("\n── fetch_protocol — single protocol lookup ───────────────────────")
    protocols = [{"id": 2, "title": "RACING BRAIN"}]
    db = _make_db(protocols=protocols)
    result = asyncio.run(fetch_protocol(db, 2))
    check("returns the matching protocol", result == protocols[0])


def test_fetch_protocol_steps_ordered_rendering():
    print("\n── render_protocol — steps rendered in step_order, not insertion order ─")
    protocol = {"title": "RACING BRAIN", "description": "desc"}
    steps = [
        {"step_order": 3, "instruction": "Pick one bounded activity."},
        {"step_order": 1, "instruction": "Brain dump."},
        {"step_order": 2, "instruction": "Reduce incoming information."},
    ]
    text = render_protocol(protocol, steps)
    idx_1 = text.index("Brain dump.")
    idx_2 = text.index("Reduce incoming information.")
    idx_3 = text.index("Pick one bounded activity.")
    check("steps rendered in numeric step_order despite shuffled input order", idx_1 < idx_2 < idx_3)
    check("title present", "RACING BRAIN" in text)
    check("description present", "desc" in text)


def main():
    print("=" * 60)
    print("/distract + /protocols — V02 WP09 test suite")
    print("=" * 60)

    test_tiers_are_all_populated()
    test_pick_activity_returns_from_correct_tier()
    test_pick_activity_respects_exclude()
    test_pick_activity_falls_back_when_everything_excluded()
    test_render_activity_offers_one_thing_not_a_list()
    test_parse_cb_distract_fields()
    test_fetch_protocols_returns_enabled_only()
    test_fetch_protocols_no_db_returns_empty()
    test_fetch_protocol_by_id()
    test_fetch_protocol_steps_ordered_rendering()

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
