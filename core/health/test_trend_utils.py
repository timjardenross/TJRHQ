"""Tests for core/health/trend_utils.py — WP-4.

Verifies the canonical trend computation used by weekly_synthesis,
health_context_adapter, and health_synthesis.

Run: python3 -m pytest core/health/test_trend_utils.py -v
  or: python3 core/health/test_trend_utils.py
"""

from __future__ import annotations
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from trend_utils import (
    compute_trend,
    compute_pain_trend,
    compute_sleep_trend,
    compute_capacity_trend,
    compute_energy_trend,
    encode_energy,
    encode_mood,
    TREND_DELTA_THRESHOLD,
    MIN_DAYS_FOR_TREND,
)


class TestComputeTrend(unittest.TestCase):

    # ── Insufficient data ─────────────────────────────────────────────────

    def test_fewer_than_min_days_returns_insufficient(self):
        self.assertEqual(compute_trend([1.0, 2.0, 3.0]), "insufficient_data")

    def test_exactly_min_days_computes(self):
        # 4 ascending values — second half higher → worsening for pain (higher_is_better=False)
        result = compute_trend([1.0, 2.0, 3.0, 4.0], higher_is_better=False)
        self.assertIn(result, ("worsening", "stable"))

    # ── Stable ────────────────────────────────────────────────────────────

    def test_stable_within_threshold(self):
        # delta < TREND_DELTA_THRESHOLD → stable
        values = [5.0, 5.1, 4.9, 5.0, 5.1, 4.9, 5.0]
        self.assertEqual(compute_trend(values), "stable")

    def test_stable_exactly_at_threshold(self):
        # delta exactly TREND_DELTA_THRESHOLD → stable (abs < threshold is the condition)
        half = TREND_DELTA_THRESHOLD
        values = [0.0, 0.0, 0.0, 0.0, half, half, half, half]
        result = compute_trend(values)
        self.assertIn(result, ("stable", "worsening"))  # boundary — accept either

    # ── Improving / worsening (higher_is_better=False, default) ──────────

    def test_pain_improving_decreasing_values(self):
        values = [8.0, 7.5, 7.0, 6.0, 5.0, 4.5, 4.0]
        self.assertEqual(compute_trend(values, higher_is_better=False), "improving")

    def test_pain_worsening_increasing_values(self):
        values = [3.0, 3.5, 4.0, 5.0, 6.0, 7.0, 8.0]
        self.assertEqual(compute_trend(values, higher_is_better=False), "worsening")

    # ── Improving / worsening (higher_is_better=True) ────────────────────

    def test_sleep_improving_increasing_values(self):
        values = [4.0, 4.5, 5.0, 6.0, 7.0, 7.5, 8.0]
        self.assertEqual(compute_trend(values, higher_is_better=True), "improving")

    def test_sleep_worsening_decreasing_values(self):
        values = [8.0, 7.5, 7.0, 6.0, 5.0, 4.5, 4.0]
        self.assertEqual(compute_trend(values, higher_is_better=True), "worsening")


class TestDomainHelpers(unittest.TestCase):

    def test_pain_trend_decreasing_is_improving(self):
        values = [8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0]
        self.assertEqual(compute_pain_trend(values), "improving")

    def test_sleep_trend_increasing_is_improving(self):
        values = [4.0, 5.0, 6.0, 7.0, 7.5, 8.0, 8.0]
        self.assertEqual(compute_sleep_trend(values), "improving")

    def test_capacity_trend_increasing_is_improving(self):
        values = [40.0, 45.0, 50.0, 60.0, 65.0, 70.0, 75.0]
        self.assertEqual(compute_capacity_trend(values), "improving")

    def test_energy_trend_increasing_ordinal_is_improving(self):
        # Low=1, Moderate=2, High=3
        values = [1.0, 1.0, 2.0, 2.0, 3.0, 3.0, 3.0]
        self.assertEqual(compute_energy_trend(values), "improving")

    def test_pain_trend_insufficient_data(self):
        self.assertEqual(compute_pain_trend([5.0, 6.0]), "insufficient_data")


class TestEncoders(unittest.TestCase):

    def test_encode_energy_case_insensitive(self):
        self.assertEqual(encode_energy("low"), 1.0)
        self.assertEqual(encode_energy("Low"), 1.0)
        self.assertEqual(encode_energy("moderate"), 2.0)
        self.assertEqual(encode_energy("Moderate"), 2.0)
        self.assertEqual(encode_energy("high"), 3.0)
        self.assertEqual(encode_energy("High"), 3.0)

    def test_encode_energy_unknown_defaults_to_moderate(self):
        self.assertEqual(encode_energy("unknown"), 2.0)

    def test_encode_mood_case_insensitive(self):
        self.assertEqual(encode_mood("low"), 1.0)
        self.assertEqual(encode_mood("stable"), 2.0)
        self.assertEqual(encode_mood("positive"), 3.0)
        self.assertEqual(encode_mood("Positive"), 3.0)

    def test_encode_mood_unknown_defaults_to_stable(self):
        self.assertEqual(encode_mood("unknown"), 2.0)


class TestConsistencyWithPriorImplementations(unittest.TestCase):
    """Verify compute_trend gives the same result as each prior inline implementation
    for representative inputs. This guards against regression during WP-4 migration."""

    def _weekly_synthesis_old(self, values):
        """Original weekly_synthesis._numeric_trend logic (delta threshold 0.4)."""
        if len(values) < 4:
            return "insufficient_data"
        mid = len(values) // 2
        first_half = sum(values[:mid]) / mid
        second_half = sum(values[mid:]) / (len(values) - mid)
        delta = second_half - first_half
        if abs(delta) < 0.4:
            return "stable"
        return "worsening" if delta > 0 else "improving"

    def test_consistent_with_weekly_synthesis_for_pain(self):
        test_cases = [
            [8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0],  # clear improving
            [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0],  # clear worsening
            [5.0, 5.1, 4.9, 5.0, 5.1, 4.9, 5.0],  # stable
        ]
        for values in test_cases:
            old = self._weekly_synthesis_old(values)
            new = compute_pain_trend(values)
            # For pain: old returns 'improving' when delta < 0; new does the same
            self.assertEqual(old, new, f"Mismatch for {values}: old={old}, new={new}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
