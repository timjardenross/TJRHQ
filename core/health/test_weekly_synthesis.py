"""
Tests for Sprint A weekly synthesis additions.

Covers:
  - 30-day baseline calculation and comparison
  - CPAP compliance and next-day energy analysis
  - Sleep quality vs sleep hours finding
  - Intention-delivery gap detection
  - Wins extraction
  - Status distribution analysis
  - Deterministic findings list construction
  - LLM narrative parsing (valid / invalid / missing keys)
  - Combined narrative fallback when LLM fails
  - run_synthesis graceful degradation with sparse data

Run: python3 -m pytest core/health/test_weekly_synthesis.py -v
  or: python3 core/health/test_weekly_synthesis.py
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from weekly_synthesis import (
    MIN_DAYS_FOR_BASELINE,
    _baseline_mean,
    _classify_vs_baseline,
    _compute_baselines,
    _analyse_cpap,
    _analyse_sleep_quality,
    _analyse_intention_delivery,
    _extract_wins,
    _analyse_statuses,
    _build_deterministic_findings,
    _build_combined_narrative,
)
from health_llm import parse_llm_narrative


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry(
    log_date: str,
    pain_score: Optional[float] = None,
    sleep_hours: Optional[float] = None,
    sleep_quality: Optional[str] = None,
    energy: Optional[str] = None,
    mood: Optional[str] = None,
    cpap_status=None,
    tomorrows_priority: str = "",
    what_happened: str = "",
    wins: str = "",
    work_status: str = "",
    personal_status: str = "",
    physical_capacity: str = "Same",
) -> Dict[str, Any]:
    return {
        "log_date": log_date,
        "pain_score": pain_score,
        "sleep_hours": sleep_hours,
        "sleep_quality": sleep_quality,
        "energy": energy,
        "mood": mood,
        "cpap_status": cpap_status,
        "tomorrows_priority": tomorrows_priority,
        "what_happened": what_happened,
        "wins": wins,
        "work_status": work_status,
        "personal_status": personal_status,
        "physical_capacity": physical_capacity,
    }


def _make_entries(n: int, start_date: str = "2026-06-01", **kwargs) -> List[Dict[str, Any]]:
    """Generate n consecutive entries starting from start_date."""
    d = date.fromisoformat(start_date)
    return [_entry((d + timedelta(days=i)).isoformat(), **kwargs) for i in range(n)]


# ---------------------------------------------------------------------------
# 30-day baseline tests
# ---------------------------------------------------------------------------

class TestBaselineMean(unittest.TestCase):

    def test_returns_none_below_min_days(self):
        entries = [_entry(f"2026-06-{i:02d}", pain_score=5.0) for i in range(1, MIN_DAYS_FOR_BASELINE)]
        result = _baseline_mean(entries, "pain_score")
        self.assertIsNone(result)

    def test_computes_mean_at_min_days(self):
        entries = [_entry(f"2026-06-{i:02d}", pain_score=float(i)) for i in range(1, MIN_DAYS_FOR_BASELINE + 1)]
        result = _baseline_mean(entries, "pain_score")
        self.assertIsNotNone(result)
        expected = sum(range(1, MIN_DAYS_FOR_BASELINE + 1)) / MIN_DAYS_FOR_BASELINE
        self.assertAlmostEqual(result, expected, places=1)

    def test_ignores_none_values(self):
        entries = [
            _entry("2026-06-01", pain_score=4.0),
            _entry("2026-06-02", pain_score=None),  # should be skipped
            _entry("2026-06-03", pain_score=6.0),
        ]
        # Only 2 non-null entries — below MIN_DAYS_FOR_BASELINE
        result = _baseline_mean(entries, "pain_score")
        self.assertIsNone(result)

    def test_applies_encode_fn(self):
        from trend_utils import encode_energy
        entries = [_entry(f"2026-06-{i:02d}", energy="Moderate") for i in range(1, MIN_DAYS_FOR_BASELINE + 1)]
        result = _baseline_mean(entries, "energy", encode_fn=encode_energy)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 2.0)  # "Moderate" encodes to 2.0


class TestClassifyVsBaseline(unittest.TestCase):

    def test_above_baseline_higher_is_worse(self):
        # Pain: higher is worse, current above baseline → below_baseline (bad)
        result = _classify_vs_baseline(6.0, 4.0, higher_is_better=False)
        self.assertEqual(result, "below_baseline")

    def test_below_baseline_higher_is_worse(self):
        # Pain: lower current than baseline → above_baseline (better)
        result = _classify_vs_baseline(3.0, 5.0, higher_is_better=False)
        self.assertEqual(result, "above_baseline")

    def test_aligned_within_threshold(self):
        result = _classify_vs_baseline(5.0, 5.0, higher_is_better=False)
        self.assertEqual(result, "aligned")

    def test_above_baseline_higher_is_better(self):
        # Sleep: higher is better, current above baseline
        result = _classify_vs_baseline(8.0, 6.0, higher_is_better=True)
        self.assertEqual(result, "above_baseline")

    def test_insufficient_data_when_none(self):
        self.assertEqual(_classify_vs_baseline(None, 5.0, True), "insufficient_data")
        self.assertEqual(_classify_vs_baseline(5.0, None, True), "insufficient_data")
        self.assertEqual(_classify_vs_baseline(None, None, True), "insufficient_data")


# ---------------------------------------------------------------------------
# CPAP analysis tests
# ---------------------------------------------------------------------------

class TestAnalyseCpap(unittest.TestCase):

    def test_no_cpap_data_returns_none_finding(self):
        entries = _make_entries(5, pain_score=5.0)
        result = _analyse_cpap(entries)
        self.assertIsNone(result["compliance_rate"])
        self.assertIsNone(result["finding"])

    def test_full_compliance_rate(self):
        d = date(2026, 6, 1)
        entries = [_entry((d + timedelta(days=i)).isoformat(), cpap_status="yes") for i in range(5)]
        result = _analyse_cpap(entries)
        self.assertEqual(result["compliance_rate"], 1.0)
        self.assertEqual(result["compliance_n"], 5)
        self.assertEqual(result["compliance_total"], 5)

    def test_zero_compliance_rate(self):
        d = date(2026, 6, 1)
        entries = [_entry((d + timedelta(days=i)).isoformat(), cpap_status="no") for i in range(4)]
        result = _analyse_cpap(entries)
        self.assertEqual(result["compliance_rate"], 0.0)

    def test_next_day_energy_lag(self):
        # Night 0: CPAP=yes, Night 1: next day energy=High
        # Night 2: CPAP=no, Night 3: next day energy=Low
        entries = [
            _entry("2026-06-01", cpap_status="yes"),
            _entry("2026-06-02", energy="High"),
            _entry("2026-06-03", cpap_status="no"),
            _entry("2026-06-04", energy="Low"),
        ]
        result = _analyse_cpap(entries)
        self.assertEqual(result["next_day_energy_with_cpap"], "High")
        self.assertEqual(result["next_day_energy_without_cpap"], "Low")

    def test_boolean_cpap_status(self):
        entries = [
            _entry("2026-06-01", cpap_status=True),
            _entry("2026-06-02", cpap_status=False),
            _entry("2026-06-03", cpap_status=True),
        ]
        result = _analyse_cpap(entries)
        self.assertEqual(result["compliance_n"], 2)

    def test_non_consecutive_dates_not_paired(self):
        # Gap of 2 days — next_day_energy should not be attributed
        entries = [
            _entry("2026-06-01", cpap_status="yes"),
            _entry("2026-06-03", energy="High"),  # gap — not consecutive
        ]
        result = _analyse_cpap(entries)
        # No consecutive pair found, so with_cpap modal should be None
        self.assertIsNone(result["next_day_energy_with_cpap"])


# ---------------------------------------------------------------------------
# Sleep quality analysis tests
# ---------------------------------------------------------------------------

class TestAnalyseSleepQuality(unittest.TestCase):

    def test_detects_long_but_poor_nights(self):
        entries = [
            _entry("2026-06-01", sleep_hours=8.0, sleep_quality="poor"),
            _entry("2026-06-02", sleep_hours=7.5, sleep_quality="poor"),
            _entry("2026-06-03", sleep_hours=8.0, sleep_quality="good"),
        ]
        result = _analyse_sleep_quality(entries)
        self.assertEqual(len(result["nights_long_but_poor_quality"]), 2)
        self.assertIn("2026-06-01", result["nights_long_but_poor_quality"])
        self.assertIsNotNone(result["finding"])
        self.assertIn("gap", result["finding"].lower())

    def test_no_quality_data_no_finding(self):
        entries = _make_entries(3, sleep_hours=7.0)
        result = _analyse_sleep_quality(entries)
        self.assertIsNone(result["finding"])
        self.assertEqual(result["nights_long_but_poor_quality"], [])

    def test_good_sleep_quality_positive_finding(self):
        entries = [
            _entry(f"2026-06-{i:02d}", sleep_hours=7.0, sleep_quality="good")
            for i in range(1, 5)
        ]
        result = _analyse_sleep_quality(entries)
        self.assertIsNotNone(result["finding"])
        self.assertIn("Good", result["finding"])

    def test_quality_distribution_computed(self):
        entries = [
            _entry("2026-06-01", sleep_quality="poor"),
            _entry("2026-06-02", sleep_quality="good"),
            _entry("2026-06-03", sleep_quality="good"),
        ]
        result = _analyse_sleep_quality(entries)
        self.assertEqual(result["quality_distribution"]["good"], 2)
        self.assertEqual(result["quality_distribution"]["poor"], 1)


# ---------------------------------------------------------------------------
# Intention-delivery tests
# ---------------------------------------------------------------------------

class TestAnalyseIntentionDelivery(unittest.TestCase):

    def test_no_intentions_returns_zero(self):
        entries = _make_entries(4)
        result = _analyse_intention_delivery(entries)
        self.assertEqual(result["days_with_intention"], 0)
        self.assertIsNone(result["finding"])

    def test_intention_with_next_day_entry(self):
        entries = [
            _entry("2026-06-01", tomorrows_priority="Complete WP-3 scheduler"),
            _entry("2026-06-02", what_happened="Worked on WP-3 and made good progress"),
        ]
        result = _analyse_intention_delivery(entries)
        self.assertEqual(result["days_with_intention"], 1)
        self.assertEqual(result["days_with_next_entry"], 1)
        self.assertEqual(len(result["pairs"]), 1)
        self.assertIsNotNone(result["pairs"][0]["delivered"])

    def test_intention_without_next_day_entry(self):
        entries = [
            _entry("2026-06-01", tomorrows_priority="Review missions"),
            # No June 2 entry
        ]
        result = _analyse_intention_delivery(entries)
        self.assertEqual(result["days_with_intention"], 1)
        self.assertEqual(result["days_with_next_entry"], 0)

    def test_non_consecutive_dates_not_counted_as_next(self):
        entries = [
            _entry("2026-06-01", tomorrows_priority="Do something"),
            _entry("2026-06-03", what_happened="Did things"),  # gap — not next day
        ]
        result = _analyse_intention_delivery(entries)
        self.assertEqual(result["days_with_next_entry"], 0)

    def test_multiple_pairs(self):
        entries = [
            _entry("2026-06-01", tomorrows_priority="Task A"),
            _entry("2026-06-02", what_happened="Completed A"),
            _entry("2026-06-03", tomorrows_priority="Task B"),
            _entry("2026-06-04", what_happened="Completed B"),
        ]
        result = _analyse_intention_delivery(entries)
        self.assertEqual(result["days_with_intention"], 2)
        self.assertEqual(result["days_with_next_entry"], 2)


# ---------------------------------------------------------------------------
# Wins extraction tests
# ---------------------------------------------------------------------------

class TestExtractWins(unittest.TestCase):

    def test_empty_wins(self):
        entries = _make_entries(5)
        result = _extract_wins(entries)
        self.assertEqual(result, [])

    def test_returns_up_to_n(self):
        entries = [
            _entry(f"2026-06-{i:02d}", wins=f"Win {i}")
            for i in range(1, 6)
        ]
        result = _extract_wins(entries, n=3)
        self.assertEqual(len(result), 3)

    def test_chronological_order(self):
        entries = [
            _entry("2026-06-01", wins="First win"),
            _entry("2026-06-02", wins="Second win"),
        ]
        result = _extract_wins(entries, n=3)
        self.assertEqual(len(result), 2)
        self.assertIn("2026-06-01", result[0])
        self.assertIn("2026-06-02", result[1])

    def test_skips_empty_wins(self):
        entries = [
            _entry("2026-06-01", wins=""),
            _entry("2026-06-02", wins="Real win"),
            _entry("2026-06-03", wins="   "),  # whitespace only
        ]
        result = _extract_wins(entries)
        self.assertEqual(len(result), 1)
        self.assertIn("Real win", result[0])


# ---------------------------------------------------------------------------
# Status distribution tests
# ---------------------------------------------------------------------------

class TestAnalyseStatuses(unittest.TestCase):

    def test_no_statuses_returns_empty(self):
        entries = _make_entries(3)
        result = _analyse_statuses(entries)
        self.assertEqual(result["work_status_dist"], {})
        self.assertEqual(result["personal_status_dist"], {})

    def test_counts_work_status(self):
        entries = [
            _entry("2026-06-01", work_status="Green"),
            _entry("2026-06-02", work_status="Amber"),
            _entry("2026-06-03", work_status="Green"),
        ]
        result = _analyse_statuses(entries)
        self.assertEqual(result["work_status_dist"]["Green"], 2)
        self.assertEqual(result["work_status_dist"]["Amber"], 1)

    def test_counts_personal_status(self):
        entries = [
            _entry("2026-06-01", personal_status="Amber"),
            _entry("2026-06-02", personal_status="Red"),
        ]
        result = _analyse_statuses(entries)
        self.assertEqual(result["personal_status_dist"]["Amber"], 1)
        self.assertEqual(result["personal_status_dist"]["Red"], 1)


# ---------------------------------------------------------------------------
# Deterministic findings builder tests
# ---------------------------------------------------------------------------

class TestBuildDeterministicFindings(unittest.TestCase):

    def _default_args(self):
        return dict(
            cpap={"finding": None},
            sleep_quality={"finding": None},
            intention={"finding": None},
            baseline_comparison={"pain": "insufficient_data"},
            pain_avg=None,
            baseline_30d={"pain_avg": None, "n_days": 0},
        )

    def test_empty_findings_when_nothing_to_report(self):
        result = _build_deterministic_findings(**self._default_args())
        self.assertEqual(result, [])

    def test_includes_cpap_finding(self):
        args = self._default_args()
        args["cpap"] = {"finding": "CPAP compliance: 5/7 nights."}
        result = _build_deterministic_findings(**args)
        self.assertIn("CPAP compliance: 5/7 nights.", result)

    def test_includes_sleep_quality_finding(self):
        args = self._default_args()
        args["sleep_quality"] = {"finding": "Sleep quality gap detected."}
        result = _build_deterministic_findings(**args)
        self.assertIn("Sleep quality gap detected.", result)

    def test_includes_intention_finding(self):
        args = self._default_args()
        args["intention"] = {"finding": "Intentions set 3 day(s)."}
        result = _build_deterministic_findings(**args)
        self.assertIn("Intentions set 3 day(s).", result)

    def test_pain_above_baseline_finding(self):
        args = self._default_args()
        args["pain_avg"] = 6.0
        args["baseline_30d"] = {"pain_avg": 4.0, "n_days": 20}
        args["baseline_comparison"] = {"pain": "above_baseline"}
        result = _build_deterministic_findings(**args)
        self.assertTrue(any("PAIN ABOVE BASELINE" in f for f in result))

    def test_pain_below_baseline_finding(self):
        args = self._default_args()
        args["pain_avg"] = 3.0
        args["baseline_30d"] = {"pain_avg": 5.0, "n_days": 20}
        args["baseline_comparison"] = {"pain": "below_baseline"}
        result = _build_deterministic_findings(**args)
        self.assertTrue(any("PAIN BELOW BASELINE" in f for f in result))


# ---------------------------------------------------------------------------
# LLM narrative parsing tests
# ---------------------------------------------------------------------------

class TestParseLlmNarrative(unittest.TestCase):

    _VALID_JSON = (
        '{"situation": "A good week.", '
        '"patterns_noticed": ["Pattern A", "Pattern B"], '
        '"what_it_means": "Things are improving.", '
        '"recommended_focus": ["Focus on sleep", "Monitor pain"], '
        '"watch_items": ["Watch pain on Tuesday"]}'
    )

    def test_valid_json_parsed(self):
        result = parse_llm_narrative(self._VALID_JSON)
        self.assertIsNotNone(result)
        self.assertEqual(result["situation"], "A good week.")
        self.assertIsInstance(result["patterns_noticed"], list)
        self.assertEqual(len(result["recommended_focus"]), 2)

    def test_json_inside_markdown_fence(self):
        wrapped = f"```json\n{self._VALID_JSON}\n```"
        result = parse_llm_narrative(wrapped)
        self.assertIsNotNone(result)

    def test_missing_key_returns_none(self):
        incomplete = '{"situation": "A week.", "patterns_noticed": [], "what_it_means": "OK."}'
        result = parse_llm_narrative(incomplete)
        self.assertIsNone(result)

    def test_empty_string_returns_none(self):
        self.assertIsNone(parse_llm_narrative(""))
        self.assertIsNone(parse_llm_narrative(None))

    def test_invalid_json_returns_none(self):
        self.assertIsNone(parse_llm_narrative("not json at all"))

    def test_json_array_returns_none(self):
        self.assertIsNone(parse_llm_narrative('["situation", "patterns_noticed"]'))


# ---------------------------------------------------------------------------
# Combined narrative builder tests
# ---------------------------------------------------------------------------

class TestBuildCombinedNarrative(unittest.TestCase):

    _BASE_ARGS = dict(
        week_start="2026-06-07",
        n=5,
        auto_status="Amber",
        pain_avg=5.0,
        pain_trend="stable",
        sleep_avg=7.5,
        sleep_trend="improving",
        energy_modal="Moderate",
        mood_modal="Stable",
        capacity_avg=65.0,
        risk_flags=[],
        positive_flags=[],
        decisions=[],
        baseline_30d={"pain_avg": None, "sleep_avg": None, "capacity_avg": None, "n_days": 5},
        baseline_comparison={"pain": "insufficient_data", "sleep": "insufficient_data",
                              "capacity": "insufficient_data"},
        deterministic_findings=[],
        wins=[],
        llm_narrative=None,
    )

    def test_contains_week_start(self):
        result = _build_combined_narrative(**self._BASE_ARGS)
        self.assertIn("2026-06-07", result)

    def test_fallback_assessment_when_no_llm(self):
        result = _build_combined_narrative(**self._BASE_ARGS)
        self.assertIn("### Assessment", result)
        self.assertIn("monitor next week", result)

    def test_llm_situation_replaces_metrics_list(self):
        args = {**self._BASE_ARGS, "llm_narrative": {
            "situation": "A carefully observed week.",
            "patterns_noticed": ["CPAP gap"],
            "what_it_means": "Sleep quality is the main constraint.",
            "recommended_focus": ["Prioritise CPAP compliance"],
            "watch_items": ["Tuesday pain"],
        }}
        result = _build_combined_narrative(**args)
        self.assertIn("A carefully observed week.", result)
        self.assertIn("### Patterns Noticed", result)
        self.assertIn("CPAP gap", result)
        self.assertIn("### Intelligence Assessment", result)
        self.assertIn("Sleep quality is the main constraint.", result)
        self.assertIn("### Watch Next 7 Days", result)

    def test_baseline_section_shown_when_sufficient(self):
        args = {**self._BASE_ARGS, "baseline_30d": {
            "pain_avg": 4.0, "sleep_avg": 7.0, "capacity_avg": 70.0, "n_days": 20,
        }, "baseline_comparison": {"pain": "above_baseline", "sleep": "aligned", "capacity": "aligned"}}
        result = _build_combined_narrative(**args)
        self.assertIn("30-Day Baseline Comparison", result)
        self.assertIn("above baseline", result)

    def test_baseline_section_hidden_when_insufficient(self):
        result = _build_combined_narrative(**self._BASE_ARGS)
        self.assertNotIn("30-Day Baseline Comparison", result)

    def test_risk_flags_shown(self):
        args = {**self._BASE_ARGS, "risk_flags": ["HIGH_PAIN_STREAK: 3 consecutive days"]}
        result = _build_combined_narrative(**args)
        self.assertIn("Risk Indicators", result)
        self.assertIn("HIGH_PAIN_STREAK", result)

    def test_wins_shown(self):
        args = {**self._BASE_ARGS, "wins": ["[2026-06-07] Completed WP-3"]}
        result = _build_combined_narrative(**args)
        self.assertIn("Wins This Week", result)
        self.assertIn("Completed WP-3", result)


# ---------------------------------------------------------------------------
# run_synthesis integration test (mocked Supabase + LLM)
# ---------------------------------------------------------------------------

class TestRunSynthesisIntegration(unittest.TestCase):

    def _make_full_entries(self, n: int = 5) -> List[Dict[str, Any]]:
        d = date(2026, 6, 7)
        return [
            _entry(
                log_date=(d + timedelta(days=i)).isoformat(),
                pain_score=5.0 + i * 0.1,
                sleep_hours=7.5,
                sleep_quality="fair",
                energy="Moderate",
                mood="Stable",
                cpap_status="yes" if i % 2 == 0 else "no",
                tomorrows_priority=f"Task {i}" if i < 3 else "",
                what_happened=f"Did task {i-1}" if i > 0 else "",
                wins=f"Win {i}" if i % 2 == 0 else "",
                work_status="Amber",
                personal_status="Green",
                physical_capacity="Same",
            )
            for i in range(n)
        ]

    @patch("weekly_synthesis.is_configured", return_value=True)
    @patch("weekly_synthesis._fetch_week_entries")
    @patch("weekly_synthesis._fetch_baseline_entries")
    @patch("weekly_synthesis.supabase_upsert")
    @patch("weekly_synthesis.HealthLLMProvider")
    def test_synthesis_returns_required_keys(
        self, mock_llm_cls, mock_upsert, mock_baseline, mock_week, mock_configured
    ):
        mock_week.return_value = self._make_full_entries(5)
        mock_baseline.return_value = self._make_full_entries(5)  # reuse for baseline
        mock_upsert.return_value = None
        # LLM returns None — test deterministic fallback path
        mock_instance = MagicMock()
        mock_instance.generate.return_value = (None, None)
        mock_llm_cls.return_value = mock_instance

        from weekly_synthesis import run_synthesis
        result = run_synthesis(update_health_summary=False)

        # Core keys always present
        required = {
            "period_start", "period_end", "insight_type", "days_logged",
            "pain_avg", "sleep_avg", "capacity_avg", "auto_health_status",
            "narrative_summary", "synthesis_version",
            # Sprint A keys
            "baseline_30d", "baseline_comparison", "deterministic_findings",
            "wins_this_week", "intention_delivery",
            "llm_narrative", "llm_provider", "narrative_available",
        }
        for key in required:
            self.assertIn(key, result, f"Missing key: {key}")

    @patch("weekly_synthesis.is_configured", return_value=True)
    @patch("weekly_synthesis._fetch_week_entries")
    @patch("weekly_synthesis._fetch_baseline_entries")
    @patch("weekly_synthesis.supabase_upsert")
    @patch("weekly_synthesis.HealthLLMProvider")
    def test_llm_narrative_included_when_available(
        self, mock_llm_cls, mock_upsert, mock_baseline, mock_week, mock_configured
    ):
        mock_week.return_value = self._make_full_entries(5)
        mock_baseline.return_value = self._make_full_entries(5)
        mock_upsert.return_value = None

        valid_llm_json = (
            '{"situation": "A stable week.", '
            '"patterns_noticed": ["CPAP pattern"], '
            '"what_it_means": "Recovery is on track.", '
            '"recommended_focus": ["Improve CPAP compliance"], '
            '"watch_items": ["Monitor Tuesday pain"]}'
        )
        mock_instance = MagicMock()
        mock_instance.generate.return_value = (valid_llm_json, "gemini-2.5-flash")
        mock_llm_cls.return_value = mock_instance

        from weekly_synthesis import run_synthesis
        result = run_synthesis(update_health_summary=False)

        self.assertTrue(result["narrative_available"])
        self.assertEqual(result["llm_provider"], "gemini-2.5-flash")
        self.assertIsNotNone(result["llm_narrative"])
        self.assertIn("A stable week.", result["narrative_summary"])

    @patch("weekly_synthesis.is_configured", return_value=True)
    @patch("weekly_synthesis._fetch_week_entries")
    @patch("weekly_synthesis._fetch_baseline_entries")
    @patch("weekly_synthesis.supabase_upsert")
    def test_sparse_data_returns_insufficient_message(
        self, mock_upsert, mock_baseline, mock_week, mock_configured
    ):
        mock_week.return_value = [self._make_full_entries(1)[0]]  # only 1 entry
        mock_baseline.return_value = []

        from weekly_synthesis import run_synthesis
        result = run_synthesis(update_health_summary=False)

        self.assertEqual(result["days_logged"], 1)
        self.assertEqual(result["auto_health_status"], "Unknown")
        self.assertIn("Insufficient data", result["narrative_summary"])
        self.assertFalse(result["narrative_available"])

    @patch("weekly_synthesis.is_configured", return_value=True)
    @patch("weekly_synthesis._fetch_week_entries")
    @patch("weekly_synthesis._fetch_baseline_entries")
    @patch("weekly_synthesis.supabase_upsert")
    @patch("weekly_synthesis.HealthLLMProvider")
    def test_synthesis_version_is_2(
        self, mock_llm_cls, mock_upsert, mock_baseline, mock_week, mock_configured
    ):
        mock_week.return_value = self._make_full_entries(5)
        mock_baseline.return_value = []
        mock_upsert.return_value = None
        mock_instance = MagicMock()
        mock_instance.generate.return_value = (None, None)
        mock_llm_cls.return_value = mock_instance

        from weekly_synthesis import run_synthesis
        result = run_synthesis(update_health_summary=False)

        self.assertIn(result["synthesis_version"], ("2.0", "3.0"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
