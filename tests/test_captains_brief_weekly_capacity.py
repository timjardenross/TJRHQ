"""Capability-portfolio data-quality fix (2026-09-13): _get_weekly_capacity()
silently rendered "No capacity logs or recovery pulses this week" every
single week once captains_log_entries (frozen 2026-06-28) and
recovery_pulses (frozen 2026-08-21) both stopped being written to — a real
data gap indistinguishable from a genuinely quiet week, called out as an
open gap in the function's own prior comment. Verifies the new
capacity_checkins fallback tier closes it, and that the existing
log/pulse-source behavior is unchanged.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

import intelligence.captains_brief as cb


def _sb_get_by_table(responses: dict[str, list]):
    """Fake _sb_get that dispatches on the table name (first positional arg)
    the same way _get_weekly_capacity calls it for each fallback tier."""
    def fake(table, *args, **kwargs):
        return responses.get(table, [])
    return fake


class TestGetWeeklyCapacity:
    def test_falls_through_to_checkins_when_log_and_pulse_both_empty(self):
        """The exact real-world case this fix closes: both frozen sources
        return nothing, capacity_checkins has real rows."""
        checkins = [{"log_date": "2026-09-10", "capacity_state": "green"}]
        with mock.patch.object(cb, "_sb_get", side_effect=_sb_get_by_table({
            "captains_log_entries": [],
            "recovery_pulses": [],
            "capacity_checkins": checkins,
        })):
            result = cb._get_weekly_capacity(days=7)
        assert result == {"source": "checkin", "entries": checkins}

    def test_log_entries_still_take_priority(self):
        """Existing log-source behavior must be unchanged — checkins are a
        fallback, not a replacement, so a week with real log entries never
        even reaches the new tier."""
        log_entries = [{"log_date": "2026-09-10", "captain_capacity_rating": "Green"}]
        with mock.patch.object(cb, "_sb_get", side_effect=_sb_get_by_table({
            "captains_log_entries": log_entries,
            "capacity_checkins": [{"log_date": "2026-09-10", "capacity_state": "red"}],
        })) as mock_get:
            result = cb._get_weekly_capacity(days=7)
        assert result == {"source": "log", "entries": log_entries}
        # capacity_checkins must never even be queried once an earlier tier wins
        queried_tables = [call.args[0] for call in mock_get.call_args_list]
        assert "capacity_checkins" not in queried_tables

    def test_pulse_still_takes_priority_over_checkins(self):
        pulses = [{"log_date": "2026-09-10", "pulse_type": "morning"}]
        with mock.patch.object(cb, "_sb_get", side_effect=_sb_get_by_table({
            "captains_log_entries": [],
            "recovery_pulses": pulses,
            "capacity_checkins": [{"log_date": "2026-09-10", "capacity_state": "red"}],
        })):
            result = cb._get_weekly_capacity(days=7)
        assert result == {"source": "pulse", "entries": pulses}

    def test_none_when_every_source_is_genuinely_empty(self):
        """A real zero-check-in week is still possible and must still be
        reported honestly as 'none' — not papered over."""
        with mock.patch.object(cb, "_sb_get", side_effect=_sb_get_by_table({})):
            result = cb._get_weekly_capacity(days=7)
        assert result == {"source": "none", "entries": []}

    def test_queries_capacity_checkins_filtered_to_capacity_type(self):
        """Only checkin_type='capacity' rows count toward the weekly
        capacity trend — 'evening' reflections are a different signal."""
        with mock.patch.object(cb, "_sb_get", side_effect=_sb_get_by_table({})) as mock_get:
            cb._get_weekly_capacity(days=7)
        checkin_call = next(c for c in mock_get.call_args_list if c.args[0] == "capacity_checkins")
        assert "checkin_type=eq.capacity" in checkin_call.args[1]


class TestFormatWeeklyCapacityBlockCheckinSource:
    def test_renders_state_counts_and_trend(self):
        entries = [
            {"log_date": "2026-09-09", "capacity_state": "green"},
            {"log_date": "2026-09-09", "capacity_state": "green"},  # two check-ins same day (allowed, never overwritten)
            {"log_date": "2026-09-10", "capacity_state": "red"},
        ]
        lines = cb._format_weekly_capacity_block({"source": "checkin", "entries": entries}, days=7)
        header = lines[0]
        assert "3 check-in" in header
        assert "2 day" in header  # 2 distinct log_date values, from 3 check-in rows
        assert "Green" in lines[1] and "Red" in lines[1]

    def test_none_source_message_reflects_all_three_sources(self):
        lines = cb._format_weekly_capacity_block({"source": "none", "entries": []}, days=7)
        assert "check-ins" in lines[1] and "logs" in lines[1] and "recovery pulses" in lines[1]

    def test_unknown_state_falls_back_gracefully(self):
        entries = [{"log_date": "2026-09-10", "capacity_state": None}]
        lines = cb._format_weekly_capacity_block({"source": "checkin", "entries": entries}, days=7)
        assert "Unknown" in lines[1]
