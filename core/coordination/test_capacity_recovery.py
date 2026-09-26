"""Mission 2 (Capacity & Attention Engine) §15 — Recovery From Suppression
(explicitly flagged a CRITICAL safety requirement): anything hidden/
demoted because of reduced capacity must have a reliable return path. The
Captain must be able to trust that a capacity-suppressed item does not
simply disappear forever.

These tests prove the guarantee is structural, not just observed: nothing
in attention_state.py persists a suppression decision anywhere (no cache,
no DB write, no in-place mutation of the mission data). attention_
items_from_brief() is a pure function of (brief, capacity_status) — the
exact same mission data, re-passed with a different capacity_status,
produces the un-suppressed classification with zero extra state to
reconcile. Recovery isn't a feature that had to be built; it's a
consequence of the function being pure. If this ever stops being true
(e.g. someone adds caching keyed on mission_id, or starts writing a
"deferred_until" field back onto the mission), these tests will catch it.

Also serves as this module's Mission 2 §14 (Capacity Transitions) evidence:
see test_transitions_are_correct_by_construction below.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from attention_state import AttentionCategory, attention_items_from_brief
from number_one import CoordinationConfig, NumberOne

# A P1 active mission -- IMPORTANT_NOT_IMMEDIATE base category, gets
# demoted to CAN_WAIT under Red (per attention_state.py's
# _capacity_note_and_category: non-P0 items are demoted with a
# "DEFERRED -- Red capacity: P0 only today" reason).
FIXTURE_MISSIONS = [
    {
        "mission_id": "MSN-REC-01", "title": "Reduced-priority research track",
        "status": "Active", "priority": "P1", "updated_at": "2026-09-19T00:00:00",
        "blockers": [], "assigned_role": "researcher", "next_action": "Draft outline",
    },
    {
        "mission_id": "MSN-REC-02", "title": "Critical live incident",
        "status": "Active", "priority": "P0", "updated_at": "2026-09-19T00:00:00",
        "blockers": [], "assigned_role": "engineer", "next_action": "Ship hotfix",
    },
]


def _find(items, ref):
    matches = [i for i in items if i.ref == ref and i.id.startswith("number_one:priority:")]
    assert len(matches) == 1, f"expected exactly one priority item for {ref}, got {matches}"
    return matches[0]


def _build_brief():
    return NumberOne(CoordinationConfig()).get_daily_brief(FIXTURE_MISSIONS)


class TestSuppressedItemReturnsWhenCapacityRecovers:
    def test_red_demotes_p1_item_with_a_capacity_reason(self):
        items = attention_items_from_brief(_build_brief(), capacity_status="Red")
        item = _find(items, "MSN-REC-01")
        assert item.category == AttentionCategory.CAN_WAIT
        assert item.capacity_adjusted_reason == "DEFERRED — Red capacity: P0 only today"

    def test_green_on_the_identical_fixture_returns_it_uncapped(self):
        """Same mission data, only capacity_status differs -- the item
        returns to its non-adjusted category with no capacity reason."""
        items = attention_items_from_brief(_build_brief(), capacity_status="Green")
        item = _find(items, "MSN-REC-01")
        assert item.category == AttentionCategory.IMPORTANT_NOT_IMMEDIATE
        assert item.capacity_adjusted_reason is None

    def test_no_capacity_status_at_all_also_returns_it_uncapped(self):
        """Backward-compat / Unknown path: absence of a capacity_status
        arg must not leave a stale demotion in effect."""
        items = attention_items_from_brief(_build_brief())
        item = _find(items, "MSN-REC-01")
        assert item.category == AttentionCategory.IMPORTANT_NOT_IMMEDIATE
        assert item.capacity_adjusted_reason is None

    def test_p0_item_is_never_demoted_even_under_red(self):
        items = attention_items_from_brief(_build_brief(), capacity_status="Red")
        item = _find(items, "MSN-REC-02")
        assert item.category == AttentionCategory.NEEDS_NOW
        assert item.capacity_adjusted_reason == "CRITICAL — proceed regardless of capacity"


class TestNoStatefulSuppression:
    def test_input_mission_dicts_are_not_mutated_by_a_red_pass(self):
        """The structural half of the recovery guarantee: if Red demotion
        wrote anything back onto the mission dict itself (a cache, a flag),
        a later Green read of the SAME dict could disagree with a fresh
        read depending on dict identity/mutation order -- proving it
        doesn't happen closes that risk."""
        before = copy.deepcopy(FIXTURE_MISSIONS)
        brief = _build_brief()
        attention_items_from_brief(brief, capacity_status="Red")
        assert FIXTURE_MISSIONS == before

    def test_calling_red_then_green_on_the_same_brief_object_is_order_independent(self):
        """Re-run in the other order too -- proves there's no hidden
        instance state on the brief or its WorkQueueItems that a prior
        capacity_status call could leave behind for the next one."""
        brief = _build_brief()
        red_first = attention_items_from_brief(brief, capacity_status="Red")
        green_after = attention_items_from_brief(brief, capacity_status="Green")
        green_first_fresh = attention_items_from_brief(_build_brief(), capacity_status="Green")

        red_item = _find(red_first, "MSN-REC-01")
        assert red_item.category == AttentionCategory.CAN_WAIT

        green_item = _find(green_after, "MSN-REC-01")
        fresh_item = _find(green_first_fresh, "MSN-REC-01")
        assert green_item.category == fresh_item.category == AttentionCategory.IMPORTANT_NOT_IMMEDIATE
        assert green_item.capacity_adjusted_reason == fresh_item.capacity_adjusted_reason is None


class TestTransitionsAreCorrectByConstruction:
    """Mission 2 §14 (Capacity Transitions) evidence for this module:
    attention_items_from_brief() takes capacity_status as a plain argument
    and holds no module-level cache, no memoization decorator, and no
    per-mission persisted state (confirmed by reading the source: the only
    state is the `items` list built fresh inside each call). A transition
    (Red -> Amber -> Green) is therefore not a special code path to build
    -- it is simply the next call receiving a different argument. These
    tests exercise the specific sequence Red -> Amber -> Green -> Red and
    confirm every step produces the classification that a fresh
    from-scratch call with that same capacity_status would."""

    def test_full_transition_sequence_matches_fresh_calls_at_every_step(self):
        brief = _build_brief()
        sequence = ["Red", "Amber", "Green", "Red"]
        expected_category = {
            "Red": AttentionCategory.CAN_WAIT,
            "Amber": AttentionCategory.IMPORTANT_NOT_IMMEDIATE,
            "Green": AttentionCategory.IMPORTANT_NOT_IMMEDIATE,
        }
        for status in sequence:
            observed = _find(attention_items_from_brief(brief, capacity_status=status), "MSN-REC-01")
            fresh = _find(attention_items_from_brief(_build_brief(), capacity_status=status), "MSN-REC-01")
            assert observed.category == fresh.category == expected_category[status]
            assert observed.capacity_adjusted_reason == fresh.capacity_adjusted_reason
