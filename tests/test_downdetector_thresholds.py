"""
Unit tests for intelligence/ingestion/downdetector_thresholds.py — the
LLM-learned per-source Downdetector report-count threshold (Captain
decision 2, replacing the flat _REPORT_COUNT_FLOOR=150 constant).

Covers, all against synthetic data (no live Supabase or real LLM call
required, no 30-day wait):
- Cold-start: insufficient history -> sector bootstrap default, logged as such
- Sufficient history -> LLM recommendation adopted when it passes the sanity guard
- Sanity guard rejects an obviously-wrong LLM output (0, and an absurdly high
  number) -> falls back to the bootstrap default
- All-providers-unavailable -> falls back to the bootstrap default
- summarize_history()'s quiet/spike split and percentile math
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.ingestion.downdetector_thresholds import (
    HistorySummary,
    ThresholdResult,
    bootstrap_default,
    recompute_threshold_for_source,
    sanity_check,
    summarize_history,
)


def _obs(day: str, status: str, count):
    """Synthetic downdetector_baseline_history row."""
    return {"observed_at": f"{day}T06:00:00+00:00", "status": status, "report_count": count}


def _quiet_history(num_days: int, count: int = 3, sector_day_start: int = 1) -> list[dict]:
    return [
        _obs(f"2026-07-{sector_day_start + i:02d}" if sector_day_start + i <= 31
             else f"2026-08-{sector_day_start + i - 31:02d}", "no_problems", count)
        for i in range(num_days)
    ]


class TestBootstrapDefaults(unittest.TestCase):
    def test_telecom_keeps_evidence_grounded_150(self):
        self.assertEqual(bootstrap_default("telecom"), 150)

    def test_banking_and_government_lower_than_telecom(self):
        self.assertLess(bootstrap_default("banking"), bootstrap_default("telecom"))
        self.assertLess(bootstrap_default("government"), bootstrap_default("telecom"))

    def test_unknown_sector_falls_back_to_other(self):
        self.assertEqual(bootstrap_default("nonsense"), bootstrap_default("other"))


class TestSummarizeHistory(unittest.TestCase):
    def test_quiet_and_spike_split(self):
        observations = [
            _obs("2026-07-01", "no_problems", 2),
            _obs("2026-07-02", "possible_problems", 5),
            _obs("2026-07-03", "problems", 260),   # real spike
            _obs("2026-07-04", "no_problems", 4),
        ]
        summary = summarize_history(observations)
        self.assertEqual(summary.distinct_days, 4)
        self.assertEqual(summary.quiet_count, 3)  # no_problems + possible_problems
        self.assertEqual(summary.quiet_max, 5)
        self.assertEqual(summary.spike_max, 260)
        self.assertEqual(len(summary.spike_events), 1)

    def test_no_observations_is_all_none(self):
        summary = summarize_history([])
        self.assertEqual(summary.distinct_days, 0)
        self.assertIsNone(summary.quiet_max)
        self.assertIsNone(summary.spike_max)

    def test_null_report_count_excluded_from_distribution(self):
        # The prose-fallback parse path (page shape changed) logs status
        # with report_count=None — must never be fabricated into the
        # distribution.
        observations = [_obs("2026-07-01", "no_problems", None)]
        summary = summarize_history(observations)
        self.assertEqual(summary.quiet_count, 0)
        self.assertIsNone(summary.quiet_max)

    def test_distinct_days_counts_calendar_days_not_rows(self):
        # A tiered-cadence source can log many rows in one day — history
        # sufficiency must be measured in real days, not raw row count.
        observations = [_obs("2026-07-01", "no_problems", n) for n in (2, 3, 4, 5, 6, 7)]
        summary = summarize_history(observations)
        self.assertEqual(summary.distinct_days, 1)


class TestSanityGuard(unittest.TestCase):
    def setUp(self):
        self.summary = HistorySummary(
            distinct_days=25, quiet_count=25, quiet_min=1, quiet_max=5,
            quiet_mean=3.0, quiet_p95=5, spike_events=[], spike_max=None,
        )

    def test_rejects_zero(self):
        passed, reason = sanity_check(0, self.summary, bootstrap=30)
        self.assertFalse(passed)
        self.assertIn("positive integer", reason)

    def test_rejects_negative(self):
        passed, reason = sanity_check(-10, self.summary, bootstrap=30)
        self.assertFalse(passed)

    def test_rejects_none(self):
        passed, reason = sanity_check(None, self.summary, bootstrap=30)
        self.assertFalse(passed)

    def test_rejects_at_or_below_quiet_max(self):
        passed, reason = sanity_check(5, self.summary, bootstrap=30)
        self.assertFalse(passed)
        self.assertIn("quiet-day count", reason)

    def test_rejects_absurdly_high_with_no_spike_history(self):
        # No real spike ever observed -> cap is 20x max(quiet_max, bootstrap).
        # quiet_max=5, bootstrap=30 -> cap = 600. 100000 must be rejected.
        passed, reason = sanity_check(100000, self.summary, bootstrap=30)
        self.assertFalse(passed)
        self.assertIn("sanity cap", reason)

    def test_accepts_reasonable_value_above_quiet_max(self):
        passed, reason = sanity_check(40, self.summary, bootstrap=30)
        self.assertTrue(passed)

    def test_rejects_above_spike_derived_cap(self):
        summary = HistorySummary(
            distinct_days=25, quiet_count=25, quiet_min=1, quiet_max=5,
            quiet_mean=3.0, quiet_p95=5,
            spike_events=[{"observed_at": "2026-07-07T00:00:00Z", "report_count": 300}],
            spike_max=300,
        )
        # Cap = 300 * 3 = 900
        self.assertTrue(sanity_check(500, summary, bootstrap=30)[0])
        self.assertFalse(sanity_check(1000, summary, bootstrap=30)[0])


class TestRecomputeThresholdForSource(unittest.TestCase):
    def test_cold_start_insufficient_history_uses_bootstrap(self):
        observations = _quiet_history(5)  # well under _MIN_HISTORY_DAYS
        result = recompute_threshold_for_source("Downdetector AU — NAB", "banking", observations)
        self.assertEqual(result.threshold_source, "bootstrap_default_insufficient_history")
        self.assertEqual(result.threshold_value, bootstrap_default("banking"))
        self.assertEqual(result.history_days_used, 5)

    def test_empty_history_uses_bootstrap(self):
        result = recompute_threshold_for_source("Downdetector AU — NAB", "banking", [])
        self.assertEqual(result.threshold_source, "bootstrap_default_insufficient_history")
        self.assertEqual(result.threshold_value, bootstrap_default("banking"))

    def test_sufficient_history_llm_recommendation_adopted(self):
        observations = _quiet_history(25, count=3)
        with mock.patch(
            "intelligence.ingestion.downdetector_thresholds._call_threshold_llm",
            return_value=(40, "gemini-2.5-flash", "40 sits well above the quiet baseline of 3."),
        ):
            result = recompute_threshold_for_source("Downdetector AU — NAB", "banking", observations)
        self.assertEqual(result.threshold_source, "llm_learned")
        self.assertEqual(result.threshold_value, 40)
        self.assertEqual(result.llm_provider, "gemini-2.5-flash")
        self.assertEqual(result.history_days_used, 25)

    def test_sufficient_history_llm_bad_output_rejected_falls_back(self):
        observations = _quiet_history(25, count=3)
        # LLM recommends 0 — obviously wrong, must be rejected by the sanity guard.
        with mock.patch(
            "intelligence.ingestion.downdetector_thresholds._call_threshold_llm",
            return_value=(0, "mistral-small", "zero"),
        ):
            result = recompute_threshold_for_source("Downdetector AU — NAB", "banking", observations)
        self.assertEqual(result.threshold_source, "bootstrap_default_after_llm_reject")
        self.assertEqual(result.threshold_value, bootstrap_default("banking"))
        self.assertIn("rejected by sanity guard", result.reasoning)

    def test_sufficient_history_llm_absurd_output_rejected_falls_back(self):
        observations = _quiet_history(25, count=3)
        with mock.patch(
            "intelligence.ingestion.downdetector_thresholds._call_threshold_llm",
            return_value=(999999, "ollama", "very high"),
        ):
            result = recompute_threshold_for_source("Downdetector AU — NAB", "banking", observations)
        self.assertEqual(result.threshold_source, "bootstrap_default_after_llm_reject")
        self.assertEqual(result.threshold_value, bootstrap_default("banking"))

    def test_all_providers_unavailable_falls_back(self):
        observations = _quiet_history(25, count=3)
        with mock.patch(
            "intelligence.ingestion.downdetector_thresholds._call_threshold_llm",
            return_value=(None, None, None),
        ):
            result = recompute_threshold_for_source("Downdetector AU — NAB", "banking", observations)
        self.assertEqual(result.threshold_source, "bootstrap_default_llm_unavailable")
        self.assertEqual(result.threshold_value, bootstrap_default("banking"))

    def test_never_raises_even_on_malformed_observations(self):
        # A production observation list could in principle have odd shapes;
        # recompute must never crash the nightly job over one source.
        try:
            recompute_threshold_for_source("X", "other", [{"observed_at": "bad", "status": "no_problems"}])
        except Exception as exc:  # pragma: no cover
            self.fail(f"recompute_threshold_for_source raised: {exc}")


if __name__ == "__main__":
    unittest.main()
