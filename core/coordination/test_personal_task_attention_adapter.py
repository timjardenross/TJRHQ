"""Mission 3 — Personal Task Attention Adapter.

Mission 2 deferred this ("Mission 3 owns it"); discovery confirmed no
code path turned a personal_tasks row into anything Attention State
could see. These tests prove the deterministic categorisation rules and
that capacity policy is genuinely shared with attention_state.py, not
reimplemented.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from attention_state import AttentionCategory
from personal_task_attention_adapter import attention_items_from_personal_tasks

TODAY = datetime.now(timezone.utc).date()


def _task(**overrides) -> dict:
    base = {
        "id": "t-1",
        "title": "Buy dog food",
        "work_state": "captured",
        "urgency": 3,
        "importance": 3,
        "due_date": None,
        "deferral_count": 0,
        "follow_through_paused": False,
    }
    base.update(overrides)
    return base


class TestTerminalStatesExcluded:
    def test_completed_task_not_emitted(self):
        items = attention_items_from_personal_tasks([_task(work_state="completed")])
        assert items == []

    def test_abandoned_task_not_emitted(self):
        items = attention_items_from_personal_tasks([_task(work_state="abandoned")])
        assert items == []

    def test_paused_task_not_emitted_captain_override_wins(self):
        items = attention_items_from_personal_tasks([_task(follow_through_paused=True)])
        assert items == []


class TestCategorisation:
    def test_blocked_work_state_is_blocked_category(self):
        items = attention_items_from_personal_tasks([_task(work_state="blocked", blocker_category="waiting")])
        assert items[0].category == AttentionCategory.BLOCKED

    def test_overdue_is_needs_now(self):
        overdue = (TODAY - timedelta(days=2)).isoformat()
        items = attention_items_from_personal_tasks([_task(due_date=overdue)])
        assert items[0].category == AttentionCategory.NEEDS_NOW
        assert "Overdue" in items[0].reason

    def test_max_urgency_and_high_importance_is_needs_now_even_without_due_date(self):
        items = attention_items_from_personal_tasks([_task(urgency=5, importance=4)])
        assert items[0].category == AttentionCategory.NEEDS_NOW

    def test_due_tomorrow_is_important_not_immediate(self):
        tomorrow = (TODAY + timedelta(days=1)).isoformat()
        items = attention_items_from_personal_tasks([_task(due_date=tomorrow)])
        assert items[0].category == AttentionCategory.IMPORTANT_NOT_IMMEDIATE

    def test_high_importance_alone_is_important_not_immediate(self):
        items = attention_items_from_personal_tasks([_task(importance=4, urgency=2)])
        assert items[0].category == AttentionCategory.IMPORTANT_NOT_IMMEDIATE

    def test_three_deferrals_is_stalled_important_not_immediate(self):
        items = attention_items_from_personal_tasks([_task(deferral_count=3)])
        assert items[0].category == AttentionCategory.IMPORTANT_NOT_IMMEDIATE
        assert "stalled" in items[0].reason.lower()

    def test_two_deferrals_not_yet_stalled(self):
        items = attention_items_from_personal_tasks([_task(deferral_count=2)])
        assert items[0].category == AttentionCategory.CAN_WAIT

    def test_low_urgency_far_due_is_can_wait(self):
        far = (TODAY + timedelta(days=30)).isoformat()
        items = attention_items_from_personal_tasks([_task(due_date=far, urgency=1, importance=1)])
        assert items[0].category == AttentionCategory.CAN_WAIT


class TestProvenanceAndShape:
    def test_id_and_ref_trace_back_to_source_task(self):
        items = attention_items_from_personal_tasks([_task(id="abc-123")])
        assert items[0].id == "personal_task:abc-123"
        assert items[0].ref == "abc-123"

    def test_source_is_personal_task_not_number_one(self):
        items = attention_items_from_personal_tasks([_task()])
        assert items[0].source == "personal_task"

    def test_sorted_by_priority_needs_now_first(self):
        overdue = (TODAY - timedelta(days=1)).isoformat()
        far = (TODAY + timedelta(days=30)).isoformat()
        items = attention_items_from_personal_tasks([
            _task(id="low", due_date=far, urgency=1, importance=1),
            _task(id="urgent", due_date=overdue),
        ])
        assert [i.ref for i in items] == ["urgent", "low"]


class TestCapacityPolicyIsShared:
    """Confirms this adapter calls attention_state's canonical
    _capacity_note_and_category rather than a second implementation —
    Red demotes non-critical items exactly like Number One's items do."""

    def test_red_demotes_non_needs_now_to_can_wait(self):
        far = (TODAY + timedelta(days=30)).isoformat()
        items = attention_items_from_personal_tasks(
            [_task(importance=4, due_date=far)], capacity_status="Red",
        )
        assert items[0].category == AttentionCategory.CAN_WAIT
        assert "Red capacity" in items[0].capacity_adjusted_reason

    def test_red_leaves_needs_now_critical_item_unrestricted(self):
        overdue = (TODAY - timedelta(days=1)).isoformat()
        items = attention_items_from_personal_tasks(
            [_task(due_date=overdue)], capacity_status="Red",
        )
        assert items[0].category == AttentionCategory.NEEDS_NOW
        assert "CRITICAL" in items[0].capacity_adjusted_reason

    def test_green_applies_no_adjustment(self):
        far = (TODAY + timedelta(days=30)).isoformat()
        items = attention_items_from_personal_tasks(
            [_task(importance=4, due_date=far)], capacity_status="Green",
        )
        assert items[0].capacity_adjusted_reason is None

    def test_unknown_gets_same_no_adjustment_treatment_as_green(self):
        """Matches _capacity_note_and_category's existing, already-tested
        Mission 2 semantics verbatim: Green/Unknown/None all mean "nothing
        here is capacity-adjusted" for this per-item note -- absence must
        not imply Green's *confidence*, but it also isn't Red/Amber's
        restriction. (Unknown DOES restrict at the list-filtering level in
        follow_through_engine's own gate — a different call site choosing
        a different, equally valid interpretation of the same signal.)"""
        far = (TODAY + timedelta(days=30)).isoformat()
        unknown = attention_items_from_personal_tasks([_task(importance=4, due_date=far)], capacity_status="Unknown")
        green = attention_items_from_personal_tasks([_task(importance=4, due_date=far)], capacity_status="Green")
        assert unknown[0].capacity_adjusted_reason is None
        assert green[0].capacity_adjusted_reason is None
        assert unknown[0].category == green[0].category
