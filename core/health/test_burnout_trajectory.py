"""Tests for core/health/burnout_trajectory.py — TJR Human Systems Workbench
V3 Mission 1 Part B (see TJR_Human_Systems_Workbench_V3_Mission_and_Change_
Proposal.md).

Covers the V3 doc §32 testing requirements this module is directly
responsible for: insufficient-data handling (Rule F / Scenario 5),
burnout-aware posture guardrails (Rule A / Scenario 1), recovery-trajectory
classification (improving/deteriorating), functional-accessibility trend
elevating concern despite stable capacity (Rule C / Scenario 3), and legacy
records with missing V3 fields never crashing the engine.

Run: python3 -m pytest core/health/test_burnout_trajectory.py -v
  or: python3 core/health/test_burnout_trajectory.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from burnout_trajectory import compute_burnout_trajectory


def _capacity_row(day: int, capacity_state: str, **kw) -> dict:
    """A quick check-in row. `day` only controls chronological ordering
    (zero-padded so string-sort == chronological sort, matching
    _sort_key()'s captured_at-string comparison)."""
    row = {
        "checkin_type": "capacity",
        "log_date": f"2026-08-{day:02d}",
        "captured_at": f"2026-08-{day:02d}T09:00:00+10:00",
        "capacity_state": capacity_state,
    }
    row.update(kw)
    return row


def _evening_row(day: int, capacity_debt: str) -> dict:
    return {
        "checkin_type": "evening",
        "log_date": f"2026-08-{day:02d}",
        "captured_at": f"2026-08-{day:02d}T21:00:00+10:00",
        "capacity_debt": capacity_debt,
    }


class TestInsufficientData(unittest.TestCase):
    """Rule F / Scenario 5 — fewer than MIN_CHECKINS_FOR_TRAJECTORY relevant
    check-ins must never produce a confident trajectory claim."""

    def test_few_checkins_yield_insufficient_data(self):
        checkins = [_capacity_row(d, "red") for d in range(1, 4)]  # 3 rows
        profile = compute_burnout_trajectory(checkins, window_days=21, today_posture="ENGAGE")
        self.assertEqual(profile["system_trajectory"], "insufficient_data")
        self.assertEqual(profile["trajectory_confidence"], "low")
        self.assertIsNone(profile["current_recovery_stage"])
        self.assertEqual(profile["relevant_checkin_count"], 3)

    def test_insufficient_data_falls_back_to_todays_posture(self):
        checkins = [_capacity_row(d, "green") for d in range(1, 3)]  # 2 rows
        profile = compute_burnout_trajectory(checkins, window_days=21, today_posture="PROTECT")
        self.assertEqual(profile["system_trajectory"], "insufficient_data")
        self.assertEqual(profile["strategic_posture"], "protect")

    def test_insufficient_data_no_today_posture_defaults_steady(self):
        profile = compute_burnout_trajectory([], window_days=21, today_posture=None)
        self.assertEqual(profile["system_trajectory"], "insufficient_data")
        self.assertEqual(profile["strategic_posture"], "steady")
        self.assertEqual(profile["relevant_checkin_count"], 0)


class TestScenario1GreenDayDuringSustainedStrain(unittest.TestCase):
    """V3 doc §31 Scenario 1 / Rule A — today's capacity improving must not
    flip strategic posture to ENGAGE while sustained strain is high."""

    def test_sustained_high_strain_caps_posture_below_engage(self):
        # 9 of 10 check-ins orange/red (90%, clears the doc's own worked
        # example threshold of >=60%), 2 evening capacity_debt='yes'.
        checkins = (
            [_capacity_row(d, "orange") for d in range(1, 8)]
            + [_capacity_row(8, "red")]
            + [_capacity_row(9, "red")]
            + [_capacity_row(10, "green")]  # today — a good day
            + [_evening_row(3, "yes"), _evening_row(6, "yes")]
        )
        profile = compute_burnout_trajectory(checkins, window_days=21, today_posture="ENGAGE")
        self.assertEqual(profile["system_trajectory"], "sustained_high_strain")
        self.assertNotEqual(profile["strategic_posture"], "engage")
        self.assertIn(profile["strategic_posture"], ("protect", "recover", "stabilise"))
        # Rule G — message stays plain-language, no fabricated percentage.
        self.assertNotIn("%", profile["strategic_posture_message"])
        self.assertNotIn("score", profile["strategic_posture_message"].lower())

    def test_burnout_like_depletion_caps_posture_at_recover(self):
        # Severe: mostly red, corroborated by high compensation load.
        checkins = (
            [_capacity_row(d, "red", compensation_load="extreme") for d in range(1, 7)]
            + [_capacity_row(7, "orange", compensation_load="high")]
            + [_capacity_row(8, "orange", compensation_load="high")]
            + [_evening_row(2, "yes"), _evening_row(4, "yes"), _evening_row(6, "yes")]
        )
        profile = compute_burnout_trajectory(checkins, window_days=21, today_posture="ENGAGE")
        self.assertEqual(profile["system_trajectory"], "burnout_like_depletion")
        self.assertEqual(profile["strategic_posture"], "recover")
        self.assertEqual(profile["current_recovery_stage"], "recover")


class TestRecoveryTrajectory(unittest.TestCase):
    def test_clear_improving_window_can_reach_rebuilding(self):
        # Earlier half (5 rows) clearly strained; later half (6 rows) clean
        # — whole-window orange/red rate stays under the accumulating_strain
        # floor (0.4) so the improving-trend branch is reached, not masked
        # by the whole-window aggregate.
        checkins = (
            [_capacity_row(d, "orange") for d in (1, 2, 3)]
            + [_capacity_row(4, "green"), _capacity_row(5, "green")]
            + [_capacity_row(d, "green") for d in range(6, 12)]
        )
        profile = compute_burnout_trajectory(checkins, window_days=21, today_posture="ENGAGE")
        self.assertEqual(profile["recovery_trajectory"], "improving")
        self.assertIn(profile["system_trajectory"], ("rebuilding", "recovery_signals_emerging"))
        # Rebuild is only reachable when today's own posture corroborates —
        # this test uses ENGAGE, so 'rebuild' or a more cautious posture
        # (never a jump straight past it to nothing at all) is acceptable.
        self.assertIn(profile["strategic_posture"], ("rebuild", "re_engage", "stabilise"))

    def test_clear_deteriorating_window_elevates_concern(self):
        # Earlier half clean, later half clearly strained.
        checkins = (
            [_capacity_row(d, "green") for d in range(1, 6)]
            + [_capacity_row(d, "orange") for d in (6, 7, 8, 9)]
            + [_capacity_row(10, "green"), _capacity_row(11, "green")]
        )
        profile = compute_burnout_trajectory(checkins, window_days=21, today_posture="STEADY")
        self.assertEqual(profile["recovery_trajectory"], "deteriorating")
        self.assertNotEqual(profile["system_trajectory"], "stable")
        self.assertNotEqual(profile["strategic_posture"], "engage")


class TestFunctionalAccessibilityRuleC(unittest.TestCase):
    """Scenario 3 — capacity stable/acceptable but executive function and
    tolerance are worsening: must not be reported as 'stable'."""

    def test_worsening_ef_and_tolerance_elevates_despite_stable_capacity(self):
        checkins = [
            _capacity_row(1, "green", executive_function="good", stimulation_state="balanced"),
            _capacity_row(2, "green", executive_function="good", stimulation_state="balanced"),
            _capacity_row(3, "green", executive_function="strained", stimulation_state="balanced"),
            _capacity_row(4, "green", executive_function="difficult", stimulation_state="high"),
            _capacity_row(5, "green", executive_function="very_difficult", stimulation_state="high"),
            _capacity_row(6, "green", executive_function="very_difficult", stimulation_state="low"),
        ]
        profile = compute_burnout_trajectory(checkins, window_days=21, today_posture="ENGAGE")
        self.assertNotEqual(profile["system_trajectory"], "stable")
        self.assertEqual(profile["contributing_signals"]["ef_worsening"], True)


class TestLegacyRowsWithMissingFields(unittest.TestCase):
    """V3 doc §32 — existing V01/V02 data (rows predating 0152/0153) must
    remain readable; missing/null new fields must never crash the engine."""

    def test_bare_legacy_rows_do_not_crash(self):
        checkins = [
            {"checkin_type": "capacity", "capacity_state": "green"},
            {"checkin_type": "capacity", "capacity_state": "green"},
            {"checkin_type": "capacity", "capacity_state": "orange"},
            {"checkin_type": "capacity", "capacity_state": "green"},
            {"checkin_type": "capacity", "capacity_state": "green"},
        ]
        profile = compute_burnout_trajectory(checkins, window_days=21, today_posture=None)
        self.assertIn(profile["system_trajectory"], (
            "stable", "accumulating_strain", "sustained_high_strain", "burnout_like_depletion",
        ))
        self.assertIn(profile["trajectory_confidence"], ("low", "moderate", "high"))
        self.assertIsInstance(profile["contributing_signals"], dict)

    def test_completely_empty_window(self):
        profile = compute_burnout_trajectory([], window_days=21, today_posture="UNKNOWN")
        self.assertEqual(profile["system_trajectory"], "insufficient_data")
        self.assertEqual(profile["relevant_checkin_count"], 0)


if __name__ == "__main__":
    unittest.main()
