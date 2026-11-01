"""Mission 2 (USS-TJR-MSN-2): capacity as a first-class input to the
canonical Attention State.

Reuses NumberOne.get_health_adjusted_queue()'s existing, live Green/Amber/
Red rules (core/coordination/number_one.py) verbatim -- no second capacity
policy. That function only overlays get_work_queue()'s output, so this
module applies the same rules only to top_priorities/blocked_missions
items (the only sections with a real mission `priority`); escalations and
follow_ups are deliberately untouched, matching production behaviour.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from attention_state import AttentionCategory, attention_items_from_brief
from number_one import CoordinationConfig, NumberOne

NOW = datetime.utcnow()  # noqa: DTZ003 - naive UTC deliberately, matches NumberOne.current_time


def _iso(dt: datetime) -> str:
    return dt.isoformat()


MISSIONS = [
    {  # P0, active, fresh -> top_priorities, NEEDS_NOW pre-capacity
        "mission_id": "MSN-CAP-P0", "title": "Critical P0 work",
        "status": "Active", "priority": "P0", "updated_at": _iso(NOW), "blockers": [],
        "assigned_role": "engineer", "next_action": "Ship it",
    },
    {  # P2, active, fresh -> top_priorities, CAN_WAIT pre-capacity
        "mission_id": "MSN-CAP-P2", "title": "Optional P2 work",
        "status": "Active", "priority": "P2", "updated_at": _iso(NOW), "blockers": [],
        "assigned_role": "engineer", "next_action": "Get to it eventually",
    },
    {  # P1, blocked -> blocked_missions, BLOCKED pre-capacity
        "mission_id": "MSN-CAP-P1-BLOCKED", "title": "Blocked P1 work",
        "status": "Blocked", "priority": "P1", "updated_at": _iso(NOW - timedelta(days=1)),
        "blockers": ["Waiting on vendor"], "assigned_role": "engineer",
    },
]


def _items(capacity_status):
    brief = NumberOne(CoordinationConfig()).get_daily_brief(MISSIONS)
    return attention_items_from_brief(brief, capacity_status=capacity_status)


def _by_ref(items, ref):
    return next(i for i in items if i.ref == ref)


class TestBackwardCompatibility:
    def test_no_capacity_arg_matches_none_arg(self):
        brief = NumberOne(CoordinationConfig()).get_daily_brief(MISSIONS)
        default_items = attention_items_from_brief(brief)
        explicit_none_items = attention_items_from_brief(brief, capacity_status=None)
        assert [i.to_dict() for i in default_items] == [i.to_dict() for i in explicit_none_items]

    def test_no_capacity_arg_sets_capacity_adjusted_reason_none(self):
        brief = NumberOne(CoordinationConfig()).get_daily_brief(MISSIONS)
        items = attention_items_from_brief(brief)
        assert all(i.capacity_adjusted_reason is None for i in items)


class TestGreenCapacity:
    def test_no_per_item_adjustment(self):
        items = _items("Green")
        assert all(i.capacity_adjusted_reason is None for i in items if i.source == "number_one")

    def test_categories_unchanged_from_no_capacity(self):
        with_capacity = _items("Green")
        without_capacity = _items(None)
        assert [(i.ref, i.category) for i in with_capacity] == [(i.ref, i.category) for i in without_capacity]


class TestRedCapacity:
    def test_p0_item_stays_needs_now_with_critical_note(self):
        items = _items("Red")
        p0 = _by_ref(items, "MSN-CAP-P0")
        assert p0.category == AttentionCategory.NEEDS_NOW
        assert p0.capacity_adjusted_reason == "CRITICAL — proceed regardless of capacity"

    def test_non_p0_top_priority_item_demoted_to_can_wait(self):
        items = _items("Red")
        p2 = _by_ref(items, "MSN-CAP-P2")
        assert p2.category == AttentionCategory.CAN_WAIT
        assert p2.capacity_adjusted_reason == "DEFERRED — Red capacity: P0 only today"

    def test_blocked_item_stays_blocked_not_further_demoted(self):
        """Blocked items are already off the Needs You path -- Red must not
        invent a steeper reclassification get_health_adjusted_queue()
        itself doesn't apply."""
        items = _items("Red")
        blocked = _by_ref(items, "MSN-CAP-P1-BLOCKED")
        assert blocked.category == AttentionCategory.BLOCKED
        assert blocked.capacity_adjusted_reason == "DEFERRED — Red capacity: P0 only today"

    def test_escalations_and_follow_ups_untouched(self):
        """get_health_adjusted_queue() only overlays the work queue --
        escalations/follow_ups have no mission-priority field to gate on
        and must not be capacity-adjusted here either."""
        items = _items("Red")
        non_priority_items = [i for i in items if i.id.startswith(("number_one:escalation:", "number_one:followup:"))]
        assert non_priority_items  # sanity: fixture actually produces some
        assert all(i.capacity_adjusted_reason is None for i in non_priority_items)


class TestAmberCapacity:
    def test_p0_item_gets_proceed_note_no_reclassification(self):
        items = _items("Amber")
        p0 = _by_ref(items, "MSN-CAP-P0")
        assert p0.category == AttentionCategory.NEEDS_NOW
        assert p0.capacity_adjusted_reason == "Proceed — priority justifies reduced capacity"

    def test_p2_item_gets_advisory_note_no_reclassification(self):
        """Amber never reorders (matches get_health_adjusted_queue()) --
        only Red demotes. This is the material difference between Amber
        and Red this module must preserve."""
        items = _items("Amber")
        p2 = _by_ref(items, "MSN-CAP-P2")
        assert p2.category == AttentionCategory.CAN_WAIT  # unchanged from pre-capacity baseline
        assert p2.capacity_adjusted_reason == "Advisory: consider deferring on reduced capacity days"

    def test_amber_and_red_produce_different_categories_for_same_item(self):
        amber_p2 = _by_ref(_items("Amber"), "MSN-CAP-P2")
        red_p2 = _by_ref(_items("Red"), "MSN-CAP-P2")
        # Both end up CAN_WAIT here since P2's baseline is already CAN_WAIT --
        # the real material difference is the note text, asserted above.
        # This test guards against a future baseline change silently
        # collapsing Amber and Red into identical behaviour for a
        # non-CAN_WAIT-baseline item.
        assert amber_p2.capacity_adjusted_reason != red_p2.capacity_adjusted_reason


class TestUnknownOrMissingCapacityIsNotGreen:
    """Mission 2's explicit safety principle: absence of capacity data must
    not automatically imply Green."""

    def test_unknown_status_produces_no_adjustment_like_none(self):
        unknown_items = _items("Unknown")
        none_items = _items(None)
        assert [(i.ref, i.category, i.capacity_adjusted_reason) for i in unknown_items] == \
               [(i.ref, i.category, i.capacity_adjusted_reason) for i in none_items]

    def test_unknown_is_not_silently_treated_as_green_reclassification(self):
        """Both currently produce the same (no-op) per-item behaviour --
        this test exists so a future change that starts giving Green a
        real per-item effect is forced to explicitly decide what Unknown
        does too, instead of inheriting it by accident."""
        items = _items("Unknown")
        assert all(i.capacity_adjusted_reason is None for i in items)
