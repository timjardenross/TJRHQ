"""
Sprint C Test Suite — M-20260614-SPRINT-C-INTELLIGENCE-GAP-CLOSURE

Tests for:
  WP2  — _analyse_pain_location          (G-007)
  WP4  — day_of_week_pattern             (G-012)
  WP5  — _analyse_mood_longitudinal      (G-013)
  WP6  — narrative_intelligence module   (G-014)
  WP7  — _classify_recovery_status       (G-016)
  WP8  — mission_analytics module        (G-019)
  WP9  — _analyse_physical_capacity_trend (G-020)
  WP3  — lessons_analyser module         (G-011)
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "core" / "health"))
sys.path.insert(0, str(_REPO / "core" / "knowledge"))

# ── WP2 — Pain Location ───────────────────────────────────────────────────────


class TestAnalysePainLocation(unittest.TestCase):

    def _fn(self, entries):
        from weekly_synthesis import _analyse_pain_location
        return _analyse_pain_location(entries)

    def test_empty_entries_returns_no_finding(self):
        result = self._fn([])
        self.assertIsNone(result["finding"])
        self.assertIsNone(result["most_common"])

    def test_all_unspecified_returns_no_finding(self):
        entries = [{"pain_location": ""}, {"pain_location": None}]
        result = self._fn(entries)
        self.assertIsNone(result["finding"])
        self.assertIsNone(result["most_common"])

    def test_single_location_reported(self):
        entries = [{"pain_location": "lower back"}, {"pain_location": "lower back"}]
        result = self._fn(entries)
        self.assertEqual(result["most_common"], "lower back")
        self.assertIn("lower back", result["finding"])

    def test_normalises_case(self):
        entries = [
            {"pain_location": "Low Back"},
            {"pain_location": "low back"},
            {"pain_location": "LOW BACK"},
        ]
        result = self._fn(entries)
        self.assertEqual(result["most_common"], "low back")

    def test_mixed_locations_identifies_primary(self):
        entries = [
            {"pain_location": "lower back"},
            {"pain_location": "lower back"},
            {"pain_location": "shoulder"},
        ]
        result = self._fn(entries)
        self.assertEqual(result["most_common"], "lower back")
        self.assertIn("shoulder", result["finding"])


# ── WP4 — Day-of-Week Pattern ────────────────────────────────────────────────


class TestDayOfWeekPattern(unittest.TestCase):

    def _fn(self, dated_values, higher_is_better=True, min_samples=2):
        from trend_utils import day_of_week_pattern
        return day_of_week_pattern(dated_values, higher_is_better, min_samples)

    def test_empty_returns_insufficient(self):
        result = self._fn([])
        self.assertEqual(result["status"], "insufficient_data")
        self.assertIsNone(result["finding"])

    def test_insufficient_days_returns_insufficient(self):
        # Only 1 sample per day — below min_samples=2
        result = self._fn([("2026-06-09", 5.0), ("2026-06-10", 3.0)], min_samples=2)
        self.assertEqual(result["status"], "insufficient_data")

    def test_sufficient_samples_returns_ok(self):
        # June 1 2026 is a Monday. So:
        # 2026-06-02 = Tue, 2026-06-03 = Wed, 2026-06-04 = Thu
        # 2026-06-09 = Tue, 2026-06-10 = Wed, 2026-06-11 = Thu
        dated = [
            ("2026-06-02", 5.0), ("2026-06-09", 5.5),   # Tue: avg 5.25
            ("2026-06-03", 3.0), ("2026-06-10", 2.5),   # Wed: avg 2.75 (lowest pain = best)
            ("2026-06-04", 7.0), ("2026-06-11", 7.5),   # Thu: avg 7.25 (highest pain = worst)
        ]
        result = self._fn(dated, higher_is_better=False, min_samples=2)
        self.assertEqual(result["status"], "ok")
        # Thu is worst (highest pain), Wed is best (lowest pain)
        self.assertEqual(result["worst_day"], "Thu")
        self.assertEqual(result["best_day"], "Wed")

    def test_finding_only_when_meaningful_delta(self):
        # All same value — delta < 0.5 → no finding
        dated = [
            ("2026-06-02", 5.0), ("2026-06-09", 5.0),
            ("2026-06-03", 5.0), ("2026-06-10", 5.0),
            ("2026-06-04", 5.0), ("2026-06-11", 5.0),
        ]
        result = self._fn(dated, min_samples=2)
        self.assertIsNone(result["finding"])

    def test_invalid_dates_skipped(self):
        dated = [("not-a-date", 5.0), ("2026-06-02", 3.0), ("2026-06-09", 4.0)]
        result = self._fn(dated, min_samples=2)
        # Only 2 valid Mon entries — insufficient for 3-day threshold
        self.assertEqual(result["status"], "insufficient_data")


# ── WP5 — Mood Longitudinal ──────────────────────────────────────────────────


class TestAnalyseMoodLongitudinal(unittest.TestCase):

    def _fn(self, entries, baseline_entries=None):
        from weekly_synthesis import _analyse_mood_longitudinal
        return _analyse_mood_longitudinal(entries, baseline_entries or [])

    def test_empty_entries_returns_insufficient(self):
        result = self._fn([])
        self.assertEqual(result["mood_trend_7d"], "insufficient_data")

    def test_computes_7d_trend(self):
        entries = [
            {"mood": "Low"}, {"mood": "Stable"}, {"mood": "Stable"}, {"mood": "Positive"},
        ]
        result = self._fn(entries)
        # Improving: Low(1) → Positive(3)
        self.assertEqual(result["mood_trend_7d"], "improving")

    def test_30d_trend_uses_baseline_entries(self):
        baseline = [
            {"mood": "Positive"}, {"mood": "Positive"}, {"mood": "Stable"},
            {"mood": "Stable"}, {"mood": "Low"}, {"mood": "Low"},
        ]
        result = self._fn([], baseline_entries=baseline)
        self.assertEqual(result["mood_trend_30d"], "worsening")

    def test_distribution_30d_counts_correctly(self):
        baseline = [
            {"mood": "Positive"}, {"mood": "Positive"},
            {"mood": "Stable"}, {"mood": "Low"},
        ]
        result = self._fn([], baseline_entries=baseline)
        dist = result["mood_distribution_30d"]
        self.assertEqual(dist.get("positive"), 2)
        self.assertEqual(dist.get("stable"), 1)
        self.assertEqual(dist.get("low"), 1)


# ── WP9 — Physical Capacity Trend ────────────────────────────────────────────


class TestAnalysePhysicalCapacityTrend(unittest.TestCase):

    def _fn(self, entries):
        from weekly_synthesis import _analyse_physical_capacity_trend
        return _analyse_physical_capacity_trend(entries)

    def test_empty_returns_insufficient(self):
        result = self._fn([])
        self.assertEqual(result["trajectory"], "insufficient_data")

    def test_single_entry_insufficient(self):
        result = self._fn([{"log_date": "2026-06-11", "physical_capacity": "Better"}])
        self.assertEqual(result["trajectory"], "insufficient_data")

    def test_all_worse_is_declining(self):
        entries = [
            {"log_date": "2026-06-11", "physical_capacity": "Worse"},
            {"log_date": "2026-06-12", "physical_capacity": "Worse"},
            {"log_date": "2026-06-13", "physical_capacity": "Worse"},
        ]
        result = self._fn(entries)
        self.assertEqual(result["trajectory"], "declining")

    def test_mixed_same_is_stable(self):
        entries = [
            {"log_date": "2026-06-11", "physical_capacity": "Same"},
            {"log_date": "2026-06-12", "physical_capacity": "Same"},
        ]
        result = self._fn(entries)
        self.assertEqual(result["trajectory"], "stable")

    def test_better_then_worse_is_stable_net_zero(self):
        entries = [
            {"log_date": "2026-06-11", "physical_capacity": "Better"},
            {"log_date": "2026-06-12", "physical_capacity": "Worse"},
        ]
        result = self._fn(entries)
        self.assertEqual(result["trajectory"], "stable")

    def test_streak_detection(self):
        entries = [
            {"log_date": "2026-06-10", "physical_capacity": "Better"},
            {"log_date": "2026-06-11", "physical_capacity": "Worse"},
            {"log_date": "2026-06-12", "physical_capacity": "Worse"},
            {"log_date": "2026-06-13", "physical_capacity": "Worse"},
        ]
        result = self._fn(entries)
        self.assertEqual(result["streak_direction"], "declining")
        self.assertEqual(result["streak"], 3)

    def test_distribution_counts(self):
        entries = [
            {"log_date": "2026-06-11", "physical_capacity": "Better"},
            {"log_date": "2026-06-12", "physical_capacity": "Same"},
            {"log_date": "2026-06-13", "physical_capacity": "Better"},
        ]
        result = self._fn(entries)
        self.assertEqual(result["distribution"]["better"], 2)
        self.assertEqual(result["distribution"]["same"], 1)


# ── WP7 — Recovery Monitoring ────────────────────────────────────────────────


class TestClassifyRecoveryStatus(unittest.TestCase):

    def _fn(self, pain_trend, capacity_trend, energy_modal, phys_traj, pain_avg, n):
        from weekly_synthesis import _classify_recovery_status
        return _classify_recovery_status(
            pain_trend, capacity_trend, energy_modal, phys_traj, pain_avg, n
        )

    def test_insufficient_when_n_less_than_3(self):
        result = self._fn("stable", "stable", "Moderate", "stable", 5.0, 2)
        self.assertEqual(result["status"], "Insufficient Data")
        self.assertIsNone(result["finding"])

    def test_acute_when_pain_avg_gte_7(self):
        result = self._fn("stable", "stable", "Moderate", "stable", 7.5, 5)
        self.assertEqual(result["status"], "Acute")

    def test_acute_when_capacity_worsening_and_energy_low(self):
        result = self._fn("stable", "worsening", "Low", "declining", 5.0, 5)
        self.assertEqual(result["status"], "Acute")

    def test_declining_when_pain_worsening(self):
        result = self._fn("worsening", "stable", "Moderate", "stable", 5.0, 5)
        self.assertEqual(result["status"], "Declining")

    def test_active_recovery_when_pain_improving(self):
        result = self._fn("improving", "stable", "Moderate", "improving", 4.0, 5)
        self.assertEqual(result["status"], "Active Recovery")

    def test_stable_when_no_signals(self):
        result = self._fn("stable", "stable", "Moderate", "stable", 5.0, 5)
        self.assertEqual(result["status"], "Stable")

    def test_finding_always_present_when_n_sufficient(self):
        result = self._fn("stable", "stable", "Moderate", "stable", 5.0, 3)
        self.assertIsNotNone(result["finding"])


# ── WP6 — Narrative Intelligence ─────────────────────────────────────────────


class TestNarrativeIntelligence(unittest.TestCase):

    def _make_entries(self, n=3, note="Good progress today", happened="Worked from home"):
        return [
            {"log_date": f"2026-06-{10+i:02d}", "overall_note": note, "what_happened": happened}
            for i in range(n)
        ]

    def test_insufficient_entries_returns_status(self):
        from narrative_intelligence import extract_narrative_intelligence
        result = extract_narrative_intelligence(self._make_entries(1))
        self.assertEqual(result["status"], "insufficient_data")

    def test_no_text_returns_no_text_status(self):
        from narrative_intelligence import extract_narrative_intelligence
        entries = [{"log_date": "2026-06-11"}, {"log_date": "2026-06-12"}]
        result = extract_narrative_intelligence(entries)
        self.assertIn(result["status"], ("insufficient_data", "no_text"))

    @patch("narrative_intelligence.HealthLLMProvider")
    def test_uses_llm_when_available(self, mock_cls):
        from narrative_intelligence import extract_narrative_intelligence
        import json
        mock_instance = MagicMock()
        mock_instance.generate.return_value = (
            json.dumps({
                "recurring_themes": ["remote work"],
                "constraints": ["pain"],
                "concerns": [],
                "positive_improvements": ["progress"],
                "summary": "Test summary",
            }),
            "gemini-2.5-flash",
        )
        mock_cls.return_value = mock_instance

        result = extract_narrative_intelligence(self._make_entries(3))
        self.assertEqual(result["source"], "llm")
        self.assertEqual(result["provider"], "gemini-2.5-flash")
        self.assertEqual(result["recurring_themes"], ["remote work"])

    @patch("narrative_intelligence.HealthLLMProvider")
    def test_falls_back_to_keyword_when_llm_fails(self, mock_cls):
        from narrative_intelligence import extract_narrative_intelligence
        mock_instance = MagicMock()
        mock_instance.generate.return_value = (None, None)
        mock_cls.return_value = mock_instance

        result = extract_narrative_intelligence(self._make_entries(3))
        self.assertEqual(result["source"], "keyword_fallback")
        self.assertIsNone(result["provider"])

    @patch("narrative_intelligence.HealthLLMProvider")
    def test_returns_all_required_keys(self, mock_cls):
        from narrative_intelligence import extract_narrative_intelligence
        mock_instance = MagicMock()
        mock_instance.generate.return_value = (None, None)
        mock_cls.return_value = mock_instance

        result = extract_narrative_intelligence(self._make_entries(3))
        for key in ("recurring_themes", "constraints", "concerns", "positive_improvements",
                    "summary", "source", "provider", "entries_analysed", "status"):
            self.assertIn(key, result, f"Missing key: {key}")


# ── WP8 — Mission Analytics ───────────────────────────────────────────────────


class TestMissionAnalytics(unittest.TestCase):

    def _make_missions(self, n_completed=5, n_pending=3):
        missions = []
        for i in range(n_completed):
            missions.append({
                "status": "completed",
                "title": f"Mission {i}",
                "mission_id": f"MSN-{i:04d}",
                "task_type": "Engineering",
                "created_at": f"2026-06-{1+i:02d}T08:00:00+00:00",
                "updated_at": f"2026-06-{2+i:02d}T08:00:00+00:00",  # 24h each
            })
        for i in range(n_pending):
            missions.append({
                "status": "pending",
                "title": f"Pending {i}",
                "task_type": "Engineering",
                "created_at": f"2026-06-{10+i:02d}T08:00:00+00:00",
                "updated_at": f"2026-06-{10+i:02d}T09:00:00+00:00",
            })
        return missions

    @patch("mission_analytics.supabase_get")
    @patch("mission_analytics.is_configured")
    def test_analytics_computed_for_completed_missions(self, mock_cfg, mock_get):
        from mission_analytics import analyse_missions
        mock_cfg.return_value = True
        mock_get.return_value = self._make_missions(5, 2)

        result = analyse_missions()
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["analytics_available"])
        self.assertEqual(result["completed"], 5)
        self.assertEqual(result["pending"], 2)
        self.assertAlmostEqual(result["avg_hours"], 24.0)

    @patch("mission_analytics.supabase_get")
    @patch("mission_analytics.is_configured")
    def test_insufficient_data_when_few_completed(self, mock_cfg, mock_get):
        from mission_analytics import analyse_missions
        mock_cfg.return_value = True
        mock_get.return_value = self._make_missions(n_completed=2)

        result = analyse_missions()
        self.assertEqual(result["status"], "insufficient_data")
        self.assertFalse(result["analytics_available"])

    @patch("mission_analytics.is_configured")
    def test_error_when_not_configured(self, mock_cfg):
        from mission_analytics import analyse_missions
        mock_cfg.return_value = False

        result = analyse_missions()
        self.assertEqual(result["status"], "error")

    @patch("mission_analytics.supabase_get")
    @patch("mission_analytics.is_configured")
    def test_by_task_type_grouping(self, mock_cfg, mock_get):
        from mission_analytics import analyse_missions
        mock_cfg.return_value = True
        missions = [
            {
                "status": "completed", "title": f"E{i}", "task_type": "Engineering",
                "created_at": f"2026-06-0{1+i}T08:00:00+00:00",
                "updated_at": f"2026-06-0{2+i}T08:00:00+00:00",
            }
            for i in range(4)
        ] + [
            {
                "status": "completed", "title": "G1", "task_type": "Governance",
                "created_at": "2026-06-08T08:00:00+00:00",
                "updated_at": "2026-06-10T08:00:00+00:00",  # 48h
            }
        ]
        mock_get.return_value = missions

        result = analyse_missions()
        self.assertIn("Engineering", result["by_task_type"])
        self.assertIn("Governance", result["by_task_type"])
        self.assertAlmostEqual(result["by_task_type"]["Governance"]["avg_hours"], 48.0)


# ── WP3 — Lessons Analyser ────────────────────────────────────────────────────


class TestLessonsAnalyser(unittest.TestCase):

    def test_analyse_lessons_returns_required_keys(self):
        from lessons_analyser import analyse_lessons
        result = analyse_lessons()
        for key in ("lessons", "total_lessons", "outcomes", "total_outcomes",
                    "recurring_themes", "success_patterns", "failure_patterns",
                    "reusable_patterns", "findings", "status"):
            self.assertIn(key, result, f"Missing key: {key}")

    def test_lessons_parsed_from_real_file(self):
        from lessons_analyser import analyse_lessons
        result = analyse_lessons()
        # The real Lessons-Learned.md has 8 lessons
        self.assertGreaterEqual(result["total_lessons"], 3)
        self.assertEqual(result["status"], "ok")

    def test_all_lessons_have_title(self):
        from lessons_analyser import analyse_lessons
        result = analyse_lessons()
        for l in result["lessons"]:
            self.assertTrue(l.get("title"), f"Lesson {l.get('id')} missing title")

    def test_recurring_themes_is_dict(self):
        from lessons_analyser import analyse_lessons
        result = analyse_lessons()
        self.assertIsInstance(result["recurring_themes"], dict)

    def test_reusable_patterns_non_empty(self):
        from lessons_analyser import analyse_lessons
        result = analyse_lessons()
        # The real lessons have future_guidance sections
        self.assertGreater(len(result["reusable_patterns"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
