"""Tests for core/health/capacity_score.py — WP-5.

Covers:
- sleep_quality deduction (new in WP-5)
- AMBER/RED/GREEN threshold classification
- AMBER workload_constraint maps to 'modified' (documented as behaviour in health_check.py)

Run: python3 -m pytest core/health/test_capacity_score.py -v
  or: python3 core/health/test_capacity_score.py
"""

from __future__ import annotations
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from capacity_score import compute_capacity_score, CAPACITY_THRESHOLDS, WEIGHTS


class TestSleepQualityDeduction(unittest.TestCase):
    """WP-5: sleep_quality was added as a capacity factor."""

    _BASE = {
        "pain_score": 0,
        "energy": "High",
        "sleep_hours": 7.0,
        "mood": "Positive",
        "physical_capacity": "Same",
    }

    def _score_with_quality(self, quality: str | None) -> int:
        entry = {**self._BASE, "sleep_quality": quality}
        score, _ = compute_capacity_score(entry)
        return score

    def test_no_sleep_quality_deducts_nothing(self):
        base_score, _ = compute_capacity_score(self._BASE)
        score_none = self._score_with_quality(None)
        self.assertEqual(base_score, score_none)

    def test_poor_sleep_quality_deducts(self):
        score_good = self._score_with_quality("Good")
        score_poor = self._score_with_quality("Poor")
        expected_deduction = WEIGHTS["sleep_quality_poor"]
        self.assertEqual(score_good - expected_deduction, score_poor)

    def test_fair_sleep_quality_deducts(self):
        score_good = self._score_with_quality("Good")
        score_fair = self._score_with_quality("Fair")
        expected_deduction = WEIGHTS["sleep_quality_fair"]
        self.assertEqual(score_good - expected_deduction, score_fair)

    def test_good_sleep_quality_deducts_nothing(self):
        score_good = self._score_with_quality("Good")
        score_none = self._score_with_quality(None)
        self.assertEqual(score_good, score_none)

    def test_excellent_sleep_quality_deducts_nothing(self):
        score_excellent = self._score_with_quality("Excellent")
        score_none = self._score_with_quality(None)
        self.assertEqual(score_excellent, score_none)

    def test_sleep_quality_case_insensitive(self):
        """Case normalisation — DB stores Title Case, health_check.py sends lowercase."""
        score_titlecase = self._score_with_quality("Poor")
        score_lowercase = self._score_with_quality("poor")
        self.assertEqual(score_titlecase, score_lowercase)

    def test_unknown_sleep_quality_deducts_nothing(self):
        score_unknown = self._score_with_quality("unknown_value")
        score_none = self._score_with_quality(None)
        self.assertEqual(score_unknown, score_none)


class TestCapacityThresholds(unittest.TestCase):

    def test_green_threshold(self):
        # Pain=0, energy=High, 7h sleep, good mood → should be Green
        entry = {
            "pain_score": 0,
            "energy": "High",
            "sleep_hours": 7.0,
            "sleep_quality": "Good",
            "mood": "Positive",
            "physical_capacity": "Same",
        }
        score, status = compute_capacity_score(entry)
        self.assertGreaterEqual(score, CAPACITY_THRESHOLDS["Green"])
        self.assertEqual(status, "Green")

    def test_red_threshold(self):
        # Max pain, low energy, poor sleep → Red
        entry = {
            "pain_score": 10,
            "energy": "Low",
            "sleep_hours": 4.0,
            "sleep_quality": "Poor",
            "mood": "Low",
            "physical_capacity": "Worse",
        }
        score, status = compute_capacity_score(entry)
        self.assertLess(score, CAPACITY_THRESHOLDS["Amber"])
        self.assertEqual(status, "Red")

    def test_amber_range(self):
        # Moderate conditions → Amber
        entry = {
            "pain_score": 5,
            "energy": "Moderate",
            "sleep_hours": 6.5,
            "sleep_quality": "Fair",
            "mood": "Stable",
            "physical_capacity": "Same",
        }
        score, status = compute_capacity_score(entry)
        self.assertGreaterEqual(score, CAPACITY_THRESHOLDS["Amber"])
        self.assertLess(score, CAPACITY_THRESHOLDS["Green"])
        self.assertEqual(status, "Amber")

    def test_empty_entry_returns_unknown(self):
        score, status = compute_capacity_score({})
        self.assertIsNone(score)
        self.assertEqual(status, "Unknown")

    def test_none_entry_returns_unknown(self):
        score, status = compute_capacity_score(None)
        self.assertIsNone(score)
        self.assertEqual(status, "Unknown")

    def test_score_clamped_to_zero(self):
        # Worst possible — score should not go below 0
        entry = {
            "pain_score": 10,
            "energy": "Low",
            "sleep_hours": 3.0,
            "sleep_quality": "Poor",
            "mood": "Low",
            "physical_capacity": "Worse",
        }
        score, _ = compute_capacity_score(entry)
        self.assertGreaterEqual(score, 0)

    def test_score_clamped_to_100(self):
        # Best possible — score should not exceed 100
        entry = {
            "pain_score": 0,
            "energy": "High",
            "sleep_hours": 9.0,
            "sleep_quality": "Excellent",
            "mood": "Positive",
            "physical_capacity": "Better",
        }
        score, _ = compute_capacity_score(entry)
        self.assertLessEqual(score, 100)


class TestWorkloadConstraintMapping(unittest.TestCase):
    """WP-5: health_check.py maps capacity status to workload_constraint.
    Tests replicate the mapping logic to document the expected behaviour."""

    def _map(self, status: str) -> str:
        return (
            "reduced"  if status == "RED"   else
            "normal"   if status == "GREEN" else
            "modified"   # AMBER → modified
        )

    def test_red_maps_to_reduced(self):
        self.assertEqual(self._map("RED"), "reduced")

    def test_green_maps_to_normal(self):
        self.assertEqual(self._map("GREEN"), "normal")

    def test_amber_maps_to_modified(self):
        """AMBER previously collapsed to 'normal' — WP-5 preserves the three-tier signal."""
        self.assertEqual(self._map("AMBER"), "modified")

    def test_all_three_values_distinct(self):
        values = {self._map("RED"), self._map("AMBER"), self._map("GREEN")}
        self.assertEqual(len(values), 3, "All three workload_constraint values must be distinct")


if __name__ == "__main__":
    unittest.main(verbosity=2)
