"""Tests for health_synthesis.py — weekly synthesis and /health-brief command."""

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

sys.path.insert(0, str(Path(__file__).parent))

from commands.health_synthesis import (
    DailyLogStats,
    EventStats,
    SynthesisResult,
    _daily_status,
    _pain_trend,
    _rule_based_summary,
    compute_event_stats,
    compute_log_stats,
    handle_health_brief,
    run_weekly_synthesis,
)


# ── Status calculation (mirrors health_check.py) ──────────────────────────────

class TestDailyStatus(unittest.TestCase):
    def test_all_good_is_green(self):
        self.assertEqual(_daily_status({"pain_score": 2, "energy": "high", "mood": "positive", "sleep_quality": "good"}), "GREEN")

    def test_pain_7_is_red_alone(self):
        self.assertEqual(_daily_status({"pain_score": 7}), "RED")

    def test_pain_4_is_amber(self):
        self.assertEqual(_daily_status({"pain_score": 4}), "AMBER")

    def test_pain_3_is_green(self):
        self.assertEqual(_daily_status({"pain_score": 3}), "GREEN")

    def test_low_energy_adds_1(self):
        self.assertEqual(_daily_status({"energy": "low"}), "AMBER")

    def test_low_mood_adds_1(self):
        self.assertEqual(_daily_status({"mood": "low"}), "AMBER")

    def test_poor_sleep_adds_1(self):
        self.assertEqual(_daily_status({"sleep_quality": "poor"}), "AMBER")

    def test_two_soft_signals_is_red(self):
        self.assertEqual(_daily_status({"energy": "low", "mood": "low"}), "RED")

    def test_no_data_is_green(self):
        self.assertEqual(_daily_status({}), "GREEN")


# ── Pain trend calculation ─────────────────────────────────────────────────────

class TestPainTrend(unittest.TestCase):
    def test_unknown_with_single_score(self):
        self.assertEqual(_pain_trend([5.0]), "unknown")

    def test_stable_with_equal_scores(self):
        self.assertEqual(_pain_trend([4.0, 4.0, 4.0, 4.0]), "stable")

    def test_improving_when_scores_drop(self):
        self.assertEqual(_pain_trend([8.0, 7.0, 5.0, 4.0]), "improving")

    def test_worsening_when_scores_rise(self):
        self.assertEqual(_pain_trend([3.0, 4.0, 6.0, 7.0]), "worsening")

    def test_two_scores_improving(self):
        # compute_pain_trend requires ≥4 samples; fewer returns "unknown"
        self.assertEqual(_pain_trend([7.0, 4.0]), "unknown")

    def test_two_scores_stable(self):
        # compute_pain_trend requires ≥4 samples; fewer returns "unknown"
        self.assertEqual(_pain_trend([4.0, 4.3]), "unknown")


# ── Aggregate computation ─────────────────────────────────────────────────────

class TestComputeLogStats(unittest.TestCase):
    def _make_logs(self):
        return [
            {"log_date": "2026-06-06", "pain_score": 8, "energy": "low",  "mood": "low",      "sleep_quality": "poor",      "sleep_hours": 5.0, "cpap_hours": 4.0, "sitting_tolerance_minutes": 20, "workload_constraint": "reduced", "work_location": "home"},
            {"log_date": "2026-06-07", "pain_score": 6, "energy": "moderate", "mood": "stable", "sleep_quality": "fair",    "sleep_hours": 6.5, "cpap_hours": 5.5, "sitting_tolerance_minutes": 30, "workload_constraint": "reduced", "work_location": "home"},
            {"log_date": "2026-06-08", "pain_score": 4, "energy": "moderate", "mood": "stable", "sleep_quality": "good",    "sleep_hours": 7.0, "cpap_hours": 6.0, "sitting_tolerance_minutes": 45, "workload_constraint": "normal",  "work_location": "home"},
            {"log_date": "2026-06-09", "pain_score": 3, "energy": "high",     "mood": "positive","sleep_quality": "good",   "sleep_hours": 7.5, "cpap_hours": 6.5, "sitting_tolerance_minutes": 60, "workload_constraint": "normal",  "work_location": "home"},
            {"log_date": "2026-06-10", "pain_score": 2, "energy": "high",     "mood": "positive","sleep_quality": "good",   "sleep_hours": 8.0, "cpap_hours": 6.5, "sitting_tolerance_minutes": 70, "workload_constraint": "normal",  "work_location": "home"},
        ]

    def test_count(self):
        self.assertEqual(compute_log_stats(self._make_logs()).count, 5)

    def test_avg_pain_correct(self):
        ls = compute_log_stats(self._make_logs())
        expected = round((8 + 6 + 4 + 3 + 2) / 5, 1)
        self.assertEqual(ls.avg_pain, expected)

    def test_pain_trend_improving(self):
        ls = compute_log_stats(self._make_logs())
        self.assertEqual(ls.pain_trend, "improving")

    def test_status_counts(self):
        ls = compute_log_stats(self._make_logs())
        # row 0: pain=8 → RED (score=2); row 1: pain=6 → AMBER (score=1);
        # row 2: pain=4 → AMBER (score=1); rows 3-4: GREEN (score=0)
        self.assertEqual(ls.red_days, 1)
        self.assertEqual(ls.amber_days, 2)
        self.assertEqual(ls.green_days, 2)

    def test_empty_logs(self):
        ls = compute_log_stats([])
        self.assertEqual(ls.count, 0)
        self.assertIsNone(ls.avg_pain)
        self.assertEqual(ls.pain_trend, "unknown")

    def test_avg_sleep_hours(self):
        ls = compute_log_stats(self._make_logs())
        expected = round((5.0 + 6.5 + 7.0 + 7.5 + 8.0) / 5, 1)
        self.assertEqual(ls.avg_sleep_hours, expected)

    def test_avg_cpap_hours(self):
        ls = compute_log_stats(self._make_logs())
        self.assertIsNotNone(ls.avg_cpap_hours)

    def test_avg_sitting_tolerance(self):
        ls = compute_log_stats(self._make_logs())
        expected = round((20 + 30 + 45 + 60 + 70) / 5)
        self.assertEqual(ls.avg_sitting_tolerance, expected)

    def test_energy_distribution(self):
        ls = compute_log_stats(self._make_logs())
        self.assertIn("low", ls.energy_distribution)
        self.assertIn("high", ls.energy_distribution)


class TestComputeEventStats(unittest.TestCase):
    def test_empty(self):
        es = compute_event_stats([])
        self.assertEqual(es.count, 0)
        self.assertEqual(es.follow_up_count, 0)

    def test_follow_up_count(self):
        events = [
            {"event_type": "appointment", "title": "GP", "follow_up_required": True},
            {"event_type": "imaging_ordered", "title": "MRI", "follow_up_required": False},
            {"event_type": "referral", "title": "Physio", "follow_up_required": True},
        ]
        es = compute_event_stats(events)
        self.assertEqual(es.count, 3)
        self.assertEqual(es.follow_up_count, 2)

    def test_event_types_collected(self):
        events = [
            {"event_type": "appointment", "title": "A"},
            {"event_type": "procedure", "title": "B"},
        ]
        es = compute_event_stats(events)
        self.assertIn("appointment", es.event_types)
        self.assertIn("procedure", es.event_types)


# ── Rule-based summary ────────────────────────────────────────────────────────

class TestRuleBasedSummary(unittest.TestCase):
    def test_no_logs_message(self):
        ls = DailyLogStats(count=0)
        es = EventStats(count=0)
        summary = _rule_based_summary(ls, es, "2026-06-06", "2026-06-12")
        self.assertIn("No daily check-ins", summary)

    def test_summary_contains_safety_footer(self):
        ls = DailyLogStats(count=3, green_days=2, amber_days=1)
        es = EventStats()
        summary = _rule_based_summary(ls, es, "2026-06-06", "2026-06-12")
        self.assertIn("Advisory only", summary)

    def test_pain_included_when_present(self):
        ls = DailyLogStats(count=3, avg_pain=5.0, pain_trend="improving")
        es = EventStats()
        summary = _rule_based_summary(ls, es, "2026-06-06", "2026-06-12")
        self.assertIn("5.0", summary)

    def test_event_count_shown(self):
        ls = DailyLogStats(count=3, green_days=3)
        es = EventStats(count=2, follow_up_count=1, event_types=["appointment", "referral"])
        summary = _rule_based_summary(ls, es, "2026-06-06", "2026-06-12")
        self.assertIn("2 event(s)", summary)


# ── Privacy: supporting_data must not include clinical fields ─────────────────

class TestPrivacyBoundary(unittest.TestCase):
    def test_run_weekly_synthesis_supporting_data_no_clinical_fields(self):
        logs = [{"log_date": "2026-06-12", "pain_score": 4, "energy": "moderate"}]
        events = []

        with patch("commands.health_synthesis._fetch_daily_logs", return_value=logs), \
             patch("commands.health_synthesis._fetch_health_events", return_value=events), \
             patch("commands.health_synthesis._supabase_upsert") as mock_upsert, \
             patch("commands.health_synthesis._write_health_summary_md", return_value=True):

            saved_payload = {}

            def capture_upsert(table, payload, conflict_col):
                saved_payload.update(payload)
                return {"id": "test-id"}

            mock_upsert.side_effect = capture_upsert
            result = run_weekly_synthesis(period_days=1)

        self.assertTrue(result.ok)
        supporting = saved_payload.get("supporting_data", {})

        # No diagnosis, medication names, clinical notes, imaging results
        for prohibited in ("diagnosis", "medication_name", "clinical_notes", "imaging_result",
                           "blood_pressure", "heart_rate", "prescription"):
            self.assertNotIn(prohibited, supporting, f"Prohibited field in supporting_data: {prohibited}")

    def test_summary_text_does_not_contain_raw_row_data(self):
        logs = [{"log_date": "2026-06-12", "pain_score": 7, "notes": "SECRET_CLINICAL_NOTE_DO_NOT_EXPOSE"}]
        events = []

        with patch("commands.health_synthesis._fetch_daily_logs", return_value=logs), \
             patch("commands.health_synthesis._fetch_health_events", return_value=events), \
             patch("commands.health_synthesis._supabase_upsert", return_value={"id": "x"}), \
             patch("commands.health_synthesis._write_health_summary_md", return_value=True):

            result = run_weekly_synthesis(period_days=1)

        # The raw note should never appear in the output summary
        self.assertNotIn("SECRET_CLINICAL_NOTE_DO_NOT_EXPOSE", result.summary)


# ── Supabase failure handling ─────────────────────────────────────────────────

class TestSynthesisFailureHandling(unittest.TestCase):
    def test_returns_error_result_on_fetch_failure(self):
        with patch("commands.health_synthesis._fetch_daily_logs", side_effect=RuntimeError("DB down")):
            result = run_weekly_synthesis(period_days=7)
        self.assertFalse(result.ok)
        self.assertIn("DB down", result.error)

    def test_returns_error_result_on_upsert_failure(self):
        with patch("commands.health_synthesis._fetch_daily_logs", return_value=[]), \
             patch("commands.health_synthesis._fetch_health_events", return_value=[]), \
             patch("commands.health_synthesis._supabase_upsert", side_effect=RuntimeError("upsert fail")):

            result = run_weekly_synthesis(period_days=7)

        self.assertFalse(result.ok)
        self.assertIn("upsert fail", result.error)

    def test_handle_health_brief_sends_error_dm_on_failure(self):
        mock_client = MagicMock()

        with patch("commands.health_synthesis.run_weekly_synthesis",
                   return_value=SynthesisResult(ok=False, period_start="2026-06-06", period_end="2026-06-12", error="DB down")):
            handle_health_brief("U123", mock_client)

        mock_client.chat_postMessage.assert_called_once()
        call_text = str(mock_client.chat_postMessage.call_args)
        self.assertIn("U123", call_text)

    def test_handle_health_brief_sends_brief_on_success(self):
        mock_client = MagicMock()

        with patch("commands.health_synthesis.run_weekly_synthesis",
                   return_value=SynthesisResult(
                       ok=True,
                       period_start="2026-06-06",
                       period_end="2026-06-12",
                       summary="Good week overall.",
                       insight_id="abc-123",
                       health_summary_md_updated=True,
                   )):
            handle_health_brief("U456", mock_client)

        mock_client.chat_postMessage.assert_called_once()
        call_text = str(mock_client.chat_postMessage.call_args)
        self.assertIn("U456", call_text)


# ── Health-Summary.md write ───────────────────────────────────────────────────

class TestHealthSummaryMdWrite(unittest.TestCase):
    def test_write_called_on_success(self):
        logs = [{"log_date": "2026-06-12", "pain_score": 3}]

        with patch("commands.health_synthesis._fetch_daily_logs", return_value=logs), \
             patch("commands.health_synthesis._fetch_health_events", return_value=[]), \
             patch("commands.health_synthesis._supabase_upsert", return_value={"id": "x"}), \
             patch("commands.health_synthesis._write_health_summary_md", return_value=True) as mock_write:

            result = run_weekly_synthesis(period_days=1)

        mock_write.assert_called_once()
        self.assertTrue(result.health_summary_md_updated)

    def test_md_write_failure_does_not_break_synthesis(self):
        """If Health-Summary.md write fails, synthesis still returns ok=True."""
        logs = [{"log_date": "2026-06-12", "pain_score": 3}]

        with patch("commands.health_synthesis._fetch_daily_logs", return_value=logs), \
             patch("commands.health_synthesis._fetch_health_events", return_value=[]), \
             patch("commands.health_synthesis._supabase_upsert", return_value={"id": "x"}), \
             patch("commands.health_synthesis._write_health_summary_md", return_value=False):

            result = run_weekly_synthesis(period_days=1)

        self.assertTrue(result.ok)
        self.assertFalse(result.health_summary_md_updated)


# ── LLM fallback ──────────────────────────────────────────────────────────────

class TestLLMFallback(unittest.TestCase):
    def test_rule_based_used_when_llm_unavailable(self):
        logs = [{"log_date": "2026-06-12", "pain_score": 3, "energy": "high"}]

        with patch("commands.health_synthesis._fetch_daily_logs", return_value=logs), \
             patch("commands.health_synthesis._fetch_health_events", return_value=[]), \
             patch("commands.health_synthesis._supabase_upsert", return_value={"id": "x"}), \
             patch("commands.health_synthesis._write_health_summary_md", return_value=True), \
             patch("commands.health_synthesis._generate_summary",
                   return_value=("Rule-based summary text.", "rule-based")) as mock_gen:

            result = run_weekly_synthesis(period_days=1)

        self.assertTrue(result.ok)
        self.assertEqual(result.summary, "Rule-based summary text.")

    def test_generated_by_saved_to_payload(self):
        logs = [{"log_date": "2026-06-12", "pain_score": 3}]
        saved_payload = {}

        def capture_upsert(table, payload, conflict_col):
            saved_payload.update(payload)
            return {"id": "y"}

        with patch("commands.health_synthesis._fetch_daily_logs", return_value=logs), \
             patch("commands.health_synthesis._fetch_health_events", return_value=[]), \
             patch("commands.health_synthesis._supabase_upsert", side_effect=capture_upsert), \
             patch("commands.health_synthesis._write_health_summary_md", return_value=True), \
             patch("commands.health_synthesis._generate_summary",
                   return_value=("Summary.", "rule-based")):

            run_weekly_synthesis(period_days=1)

        self.assertEqual(saved_payload.get("generated_by"), "rule-based")


if __name__ == "__main__":
    unittest.main()
