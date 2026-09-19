"""Mission 1 (USS-TJR-MSN-1) fix: the Settings page's Follow-Through section
(lcars-portal/src/app/settings/_components/FollowThroughSection.tsx) persists
`reminderStyle` / `increaseAsDeadlineApproaches` / `checkBackOnWaitingItems`
to user_settings, but intelligence/adhd/follow_through_engine.py — the live
engine — never read any of it; it only read QUIET_HOURS_START/END and
FOLLOW_THROUGH_MAX_PER_DAY env vars, which the settings UI has no field for
at all. Verifies each Settings-page toggle now actually changes engine
behaviour, with the documented precedence: per-task DB field > Settings
default > hardcoded default.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

import intelligence.adhd.follow_through_engine as fte

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


class TestReminderStyleSetsDefaultMode:
    def test_explicit_task_mode_always_wins_over_setting(self):
        task = {"follow_through_mode": "persistent", "due_date": None}
        with mock.patch.object(fte, "follow_through_reminder_style", return_value="once"):
            _next_dt, _tone, eligible = fte.compute_initial_schedule(task, NOW)
        assert eligible is True  # persistent path taken, not gentle/once

    def test_setting_supplies_default_when_task_has_no_mode(self):
        task = {"follow_through_mode": None, "due_date": None}
        with mock.patch.object(fte, "follow_through_reminder_style", return_value="persistent"):
            next_dt, _tone, _eligible = fte.compute_initial_schedule(task, NOW)
        # persistent mode: now + 3 days, per compute_initial_schedule's own branch.
        assert next_dt == NOW + timedelta(days=3)

    def test_hardcoded_normal_default_when_setting_unreachable(self):
        task = {"follow_through_mode": None, "due_date": None}
        with mock.patch.object(fte, "follow_through_reminder_style", return_value=None):
            next_dt, _tone, _eligible = fte.compute_initial_schedule(task, NOW)
        # normal mode with no due date: now + 2 days.
        assert next_dt == NOW + timedelta(days=2)


class TestCheckBackOnWaitingItemsToggle:
    def _raw_task(self, mode):
        return {
            "id": "t1",
            "follow_through_mode": mode,
            "due_date": None,
            "next_review_at": None,
            "deferral_count": 0,
        }

    def test_waiting_task_excluded_when_setting_is_false(self):
        rows = [self._raw_task("waiting")]
        with mock.patch.object(fte, "follow_through_check_back_on_waiting_items", return_value=False):
            eligible = fte._assemble_eligible_candidates(rows, NOW)
        assert eligible == []

    def test_waiting_task_included_when_setting_is_true(self):
        rows = [self._raw_task("waiting")]
        with mock.patch.object(fte, "follow_through_check_back_on_waiting_items", return_value=True):
            eligible = fte._assemble_eligible_candidates(rows, NOW)
        assert len(eligible) == 1

    def test_waiting_task_included_when_setting_unreachable(self):
        """None (unset/unreachable) must default to today's live behaviour
        (always check back), never to silently suppressing waiting items."""
        rows = [self._raw_task("waiting")]
        with mock.patch.object(fte, "follow_through_check_back_on_waiting_items", return_value=None):
            eligible = fte._assemble_eligible_candidates(rows, NOW)
        assert len(eligible) == 1

    def test_non_waiting_tasks_unaffected_by_the_toggle(self):
        rows = [self._raw_task("gentle")]
        with mock.patch.object(fte, "follow_through_check_back_on_waiting_items", return_value=False):
            eligible = fte._assemble_eligible_candidates(rows, NOW)
        assert len(eligible) == 1


class TestIncreaseAsDeadlineApproachesToggle:
    def test_escalating_tone_flattened_when_setting_is_false(self):
        with mock.patch.object(fte, "follow_through_increase_as_deadline_approaches", return_value=False):
            assert fte._tone_for_candidate({"deferral_count": 0}, "warn") == "neutral"
            assert fte._tone_for_candidate({"deferral_count": 0}, "crit") == "neutral"

    def test_escalating_tone_kept_when_setting_is_true(self):
        with mock.patch.object(fte, "follow_through_increase_as_deadline_approaches", return_value=True):
            assert fte._tone_for_candidate({"deferral_count": 0}, "warn") == "warn"
            assert fte._tone_for_candidate({"deferral_count": 0}, "crit") == "crit"

    def test_escalating_tone_kept_when_setting_unreachable(self):
        with mock.patch.object(fte, "follow_through_increase_as_deadline_approaches", return_value=None):
            assert fte._tone_for_candidate({"deferral_count": 0}, "warn") == "warn"

    def test_repeated_deferral_still_forces_crit_regardless_of_setting(self):
        """The repeated-deferral escalation is a different signal from the
        deadline ladder's own tone -- the toggle must not suppress it."""
        with mock.patch.object(fte, "follow_through_increase_as_deadline_approaches", return_value=False):
            assert fte._tone_for_candidate({"deferral_count": 3}, "neutral") == "crit"
