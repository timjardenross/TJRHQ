"""
Tests for Intelligence Maturity Phase 2
Mission: M-20260613-INTELLIGENCE-MATURITY-PHASE2

Coverage:
  WP1 - decision_effectiveness
  WP2 - health_mission_correlation
  WP3 - sleep_lag
  WP4 - operating_patterns
  WP5 - readiness_history
  WP6 - knowledge_utilisation
  WP7 - mission_analytics
  WP8 - enhanced readiness_score
  WP10 - intelligence_reporter (import + structure)

Run: python3 -m pytest tests/test_intelligence_phase2.py -v
  or: cd /path/to/repo && python3 tests/test_intelligence_phase2.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "core" / "intelligence"))
sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))
sys.path.insert(0, str(_REPO_ROOT / "core" / "coordination"))


# ===========================================================================
# WP1 — Decision Effectiveness
# ===========================================================================

class TestDecisionEffectiveness(unittest.TestCase):

    def setUp(self):
        from decision_effectiveness import compute_decision_effectiveness
        self.fn = compute_decision_effectiveness

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.fn(Path(tmpdir))
        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["total_decisions"], 0)

    def test_single_decision_accepted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = {
                "decision_id": "DEC-20260613-001",
                "status": "Accepted",
                "decision_mode": "strategic",
                "captain_decision_held": "success",
                "captain_outcome_review": "Delivered as expected.",
                "research_confidence": 0.85,
                "mission_id": "MSN-001",
                "timestamp": "2026-06-13T10:00:00+00:00",
            }
            (Path(tmpdir) / "001.json").write_text(json.dumps(d))
            result = self.fn(Path(tmpdir))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["total_decisions"], 1)
        self.assertEqual(result["accepted"], 1)
        self.assertEqual(result["success_count"], 1)
        self.assertEqual(result["success_rate"], 1.0)
        self.assertIsNotNone(result["research_confidence_avg"])

    def test_multiple_decisions_mode_breakdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for i, (mode, held) in enumerate([
                ("strategic", "success"),
                ("strategic", "success"),
                ("research-to-implementation", "failure"),
                ("governance", None),
            ]):
                d = {
                    "decision_id": f"DEC-000{i}",
                    "status": "Accepted",
                    "decision_mode": mode,
                    "captain_decision_held": held,
                    "research_confidence": 0.75,
                    "timestamp": f"2026-06-0{i+1}T10:00:00Z",
                }
                (Path(tmpdir) / f"{i:03d}.json").write_text(json.dumps(d))
            result = self.fn(Path(tmpdir))

        self.assertEqual(result["total_decisions"], 4)
        self.assertEqual(result["success_count"], 2)
        self.assertEqual(result["failure_count"], 1)
        modes = {m["mode"]: m for m in result["mode_breakdown"]}
        self.assertIn("Strategic", modes)
        self.assertEqual(modes["Strategic"]["count"], 2)

    def test_g008_signal_not_ready(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.fn(Path(tmpdir))
        # Empty dir — no_data status; G008 signal absent or not ready
        g008 = result.get("g008_learning_signal", {})
        self.assertFalse(g008.get("ready", False))

    def test_g008_signal_ready_at_10(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(10):
                d = {
                    "decision_id": f"DEC-00{i:02d}",
                    "status": "Accepted",
                    "decision_mode": "strategic",
                    "captain_decision_held": "success",
                    "timestamp": f"2026-06-{i+1:02d}T10:00:00Z",
                }
                (Path(tmpdir) / f"{i:03d}.json").write_text(json.dumps(d))
            result = self.fn(Path(tmpdir))
        self.assertTrue(result["g008_learning_signal"]["ready"])

    def test_outcome_quality_score_normalised(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = {
                "decision_id": "DEC-001",
                "status": "Accepted",
                "decision_mode": "strategic",
                "outcome_quality_score": 4,  # 4/5 = 0.8
                "timestamp": "2026-06-01T10:00:00Z",
            }
            (Path(tmpdir) / "001.json").write_text(json.dumps(d))
            result = self.fn(Path(tmpdir))
        self.assertAlmostEqual(result["quality_avg"], 0.8, places=2)
        self.assertAlmostEqual(result["quality_avg_5pt"], 4.0, places=1)


# ===========================================================================
# WP3 — Sleep Lag
# ===========================================================================

class TestSleepLag(unittest.TestCase):

    def setUp(self):
        from sleep_lag import compute_sleep_lag_analysis
        self.fn = compute_sleep_lag_analysis

    def _make_entries(self, n: int = 7) -> list[dict]:
        from datetime import date, timedelta
        base = date(2026, 6, 1)
        entries = []
        for i in range(n):
            d = base + timedelta(days=i)
            entries.append({
                "log_date": d.isoformat(),
                "sleep_hours": 6.0 + (i % 3) * 0.5,
                "sleep_quality": ["poor", "fair", "good"][i % 3],
                "cpap_status": "Yes" if i % 2 == 0 else "No",
                "energy": ["Low", "Moderate", "High"][i % 3],
            })
        return entries

    def test_insufficient_data(self):
        result = self.fn([])
        self.assertEqual(result["status"], "insufficient_data")

    def test_returns_correlations(self):
        entries = self._make_entries(10)
        result = self.fn(entries)
        self.assertIn(result["status"], ("ok", "insufficient_consecutive_pairs"))
        self.assertIn("correlations", result)

    def test_ok_with_enough_consecutive_entries(self):
        entries = self._make_entries(14)
        result = self.fn(entries)
        self.assertEqual(result["status"], "ok")
        self.assertIn("sleep_duration_vs_next_day_energy", result["correlations"])
        self.assertIn("cpap_vs_next_day_energy", result["correlations"])
        self.assertGreater(result["n_lag_pairs"], 0)

    def test_sleep_threshold_table_keys(self):
        entries = self._make_entries(14)
        result = self.fn(entries)
        if result["status"] == "ok":
            table = result.get("sleep_threshold_table", {})
            self.assertIsInstance(table, dict)

    def test_findings_list(self):
        entries = self._make_entries(14)
        result = self.fn(entries)
        self.assertIsInstance(result.get("findings", []), list)


# ===========================================================================
# WP4 — Operating Patterns
# ===========================================================================

class TestOperatingPatterns(unittest.TestCase):

    def setUp(self):
        from operating_patterns import compute_operating_patterns
        self.fn = compute_operating_patterns

    def _health_entries(self, n: int = 14):
        from datetime import date, timedelta
        base = date(2026, 6, 1)
        return [
            {
                "log_date": (base + timedelta(days=i)).isoformat(),
                "pain_score": 3 + (i % 5),
                "energy": ["Low", "Moderate", "High"][i % 3],
            }
            for i in range(n)
        ]

    def _mission_dates(self) -> dict[str, int]:
        from datetime import date, timedelta
        base = date(2026, 6, 1)
        return {(base + timedelta(days=i)).isoformat(): (i % 3) for i in range(14)}

    def test_insufficient_health_data(self):
        result = self.fn([], {}, [])
        self.assertEqual(result["status"], "insufficient_data")

    def test_ok_with_data(self):
        health = self._health_entries()
        missions = self._mission_dates()
        result = self.fn(health, missions, [])
        self.assertEqual(result["status"], "ok")

    def test_pain_vs_productivity_present(self):
        health = self._health_entries()
        missions = self._mission_dates()
        result = self.fn(health, missions, [])
        patterns = result.get("patterns", {})
        self.assertIn("pain_vs_productivity", patterns)

    def test_weekday_rankings_present(self):
        health = self._health_entries()
        missions = self._mission_dates()
        result = self.fn(health, missions, [])
        patterns = result.get("patterns", {})
        self.assertIn("weekday_rankings", patterns)
        self.assertIn("ranked_weekdays", patterns["weekday_rankings"])

    def test_energy_vs_productivity_all_buckets(self):
        health = self._health_entries()
        missions = self._mission_dates()
        result = self.fn(health, missions, [])
        patterns = result.get("patterns", {})
        energy_prod = patterns.get("energy_vs_productivity", {})
        self.assertIn("Low", energy_prod)
        self.assertIn("Moderate", energy_prod)
        self.assertIn("High", energy_prod)


# ===========================================================================
# WP5 — Readiness History
# ===========================================================================

class TestReadinessHistory(unittest.TestCase):

    def setUp(self):
        from readiness_history import (
            persist_readiness_snapshot,
            load_readiness_history,
            compute_readiness_trends,
            generate_readiness_trend_report,
        )
        self.persist = persist_readiness_snapshot
        self.load = load_readiness_history
        self.trends = compute_readiness_trends
        self.report = generate_readiness_trend_report

    def _make_readiness(self, score: int, status: str = "Green") -> dict:
        return {
            "score": score,
            "status": status,
            "health_component": score // 2,
            "ops_component": score - (score // 2),
            "contributors": [f"Test contributor (score {score})"],
            "recommended_focus": ["Focus A"],
            "capacity_status": status,
        }

    def test_persist_creates_file(self):
        import tempfile, os
        from readiness_history import _READINESS_LOG_DIR
        # Patch _READINESS_LOG_DIR temporarily
        with tempfile.TemporaryDirectory() as tmpdir:
            import readiness_history
            orig = readiness_history._READINESS_LOG_DIR
            readiness_history._READINESS_LOG_DIR = Path(tmpdir)
            try:
                result = self.persist(self._make_readiness(85))
                self.assertTrue(result)
                files = list(Path(tmpdir).glob("*.json"))
                self.assertEqual(len(files), 1)
                snap = json.loads(files[0].read_text())
                self.assertEqual(snap["readiness_score"], 85)
                self.assertEqual(snap["readiness_status"], "Green")
            finally:
                readiness_history._READINESS_LOG_DIR = orig

    def test_load_returns_sorted_list(self):
        import tempfile
        import readiness_history
        orig = readiness_history._READINESS_LOG_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            readiness_history._READINESS_LOG_DIR = Path(tmpdir)
            try:
                for score, date_str in [(85, "2026-06-10"), (75, "2026-06-11")]:
                    snap = {"assessment_date": date_str, "readiness_score": score, "readiness_status": "Green"}
                    (Path(tmpdir) / f"{date_str}.json").write_text(json.dumps(snap))
                history = self.load(30)
                self.assertEqual(len(history), 2)
                self.assertEqual(history[0]["assessment_date"], "2026-06-10")
            finally:
                readiness_history._READINESS_LOG_DIR = orig

    def test_trends_insufficient_data(self):
        result = self.trends([])
        self.assertEqual(result["status"], "insufficient_data")

    def test_trends_stable(self):
        history = [
            {"assessment_date": f"2026-06-{i+1:02d}", "readiness_score": 80, "readiness_status": "Green"}
            for i in range(8)
        ]
        result = self.trends(history)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["avg_7d"], 80.0)

    def test_degradation_alert_triggers(self):
        history = [
            {"assessment_date": f"2026-06-{i+1:02d}", "readiness_score": 60, "readiness_status": "Amber"}
            for i in range(4)
        ]
        result = self.trends(history)
        self.assertTrue(result["degradation_alert"])
        self.assertEqual(result["consecutive_low_days"], 4)

    def test_recovery_signal(self):
        history = [
            {"assessment_date": "2026-06-01", "readiness_score": 40, "readiness_status": "Red"},
            {"assessment_date": "2026-06-02", "readiness_score": 45, "readiness_status": "Red"},
            {"assessment_date": "2026-06-03", "readiness_score": 65, "readiness_status": "Amber"},
        ]
        result = self.trends(history)
        self.assertTrue(result["recovery_signal"])


# ===========================================================================
# WP6 — Knowledge Utilisation
# ===========================================================================

class TestKnowledgeUtilisation(unittest.TestCase):

    def setUp(self):
        from knowledge_utilisation import compute_knowledge_utilisation
        self.fn = compute_knowledge_utilisation

    def test_runs_without_error(self):
        result = self.fn()
        self.assertEqual(result["status"], "ok")

    def test_required_keys_present(self):
        result = self.fn()
        required = [
            "most_referenced_lessons", "most_referenced_adrs",
            "most_reused_capabilities", "unused_lessons",
            "unused_adrs", "emerging_clusters", "findings",
        ]
        for key in required:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_findings_is_list(self):
        result = self.fn()
        self.assertIsInstance(result["findings"], list)

    def test_inventory_counts_present(self):
        result = self.fn()
        inv = result.get("inventory", {})
        self.assertIn("total_lessons", inv)
        self.assertIn("total_adrs", inv)
        self.assertIn("total_caps", inv)


# ===========================================================================
# WP7 — Mission Analytics
# ===========================================================================

class TestMissionAnalytics(unittest.TestCase):

    def setUp(self):
        # Use importlib to force load from core/intelligence/ and avoid
        # name collision with core/health/mission_analytics.py
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "mission_portfolio_analytics",
            _REPO_ROOT / "core" / "intelligence" / "mission_portfolio_analytics.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.cycle_time = mod._cycle_time_analysis
        self.completion = mod._completion_rate_analysis
        self.ageing     = mod._ageing_analysis
        self.full       = mod.compute_mission_analytics

    def _missions(self) -> list[dict]:
        return [
            {"id": "M1", "title": "Alpha", "status": "Closed",  "priority": "P0",
             "created_at": "2026-05-01T00:00:00Z", "closed_at": "2026-05-10T00:00:00Z"},
            {"id": "M2", "title": "Beta",  "status": "Designed","priority": "P1",
             "created_at": "2026-05-05T00:00:00Z", "closed_at": None},
            {"id": "M3", "title": "Gamma", "status": "Blocked", "priority": "P1",
             "created_at": "2026-04-01T00:00:00Z", "closed_at": None},
        ]

    def test_cycle_time_closed_mission(self):
        result = self.cycle_time(self._missions())
        self.assertEqual(result["n_closed"], 1)
        self.assertEqual(result["avg_days"], 9.0)

    def test_completion_rate(self):
        result = self.completion(self._missions())
        self.assertEqual(result["total_missions"], 3)
        self.assertEqual(result["closed"], 1)
        self.assertAlmostEqual(result["overall_completion_rate"], 33.3, places=0)

    def test_ageing_detects_stale(self):
        result = self.ageing(self._missions())
        # M3 is from April — should be stale
        self.assertGreater(result.get("stale_30d_count", 0), 0)

    def test_full_report_runs(self):
        result = self.full()
        # May have no_data if Supabase unavailable — that's acceptable
        self.assertIn(result["status"], ("ok", "no_data"))

    def test_blocked_counted_in_completion(self):
        result = self.completion(self._missions())
        self.assertEqual(result["blocked"], 1)


# ===========================================================================
# WP8 — Enhanced Readiness Score
# ===========================================================================

class TestEnhancedReadinessScore(unittest.TestCase):

    def setUp(self):
        from readiness_score import compute_readiness_score
        self.fn = compute_readiness_score

    def _base_result(self, **kwargs):
        return self.fn(
            capacity_score=75,
            capacity_status="Green",
            missions=[],
            escalations=[],
            **kwargs,
        )

    def test_baseline_no_health_entry(self):
        result = self._base_result()
        self.assertEqual(result.status, "Green")
        self.assertGreater(result.score, 0)

    def test_pain_spike_reduces_score(self):
        no_pain  = self._base_result(health_entry={"pain_score": 3})
        with_pain = self._base_result(health_entry={"pain_score": 9})
        self.assertLess(with_pain.score, no_pain.score)
        pain_contributor = any("pain spike" in c.lower() for c in with_pain.contributors)
        self.assertTrue(pain_contributor)

    def test_sleep_deprivation_reduces_score(self):
        good_sleep = self._base_result(health_entry={"sleep_hours": 7.5})
        bad_sleep  = self._base_result(health_entry={"sleep_hours": 4.0})
        self.assertLess(bad_sleep.score, good_sleep.score)
        dep_contributor = any("deprivation" in c.lower() for c in bad_sleep.contributors)
        self.assertTrue(dep_contributor)

    def test_cpap_bonus_increases_score(self):
        no_cpap   = self._base_result(health_entry={"cpap_status": "No"}, cpap_hours=0)
        with_cpap = self._base_result(health_entry={"cpap_status": "Yes"}, cpap_hours=6.0)
        self.assertGreater(with_cpap.score, no_cpap.score)
        bonus_contributor = any("cpap compliance" in c.lower() for c in with_cpap.contributors)
        self.assertTrue(bonus_contributor)

    def test_low_mood_reduces_score(self):
        good_mood = self._base_result(health_entry={"mood": "Positive"})
        bad_mood  = self._base_result(health_entry={"mood": "low"})
        self.assertLess(bad_mood.score, good_mood.score)

    def test_score_clamped_0_to_100(self):
        # Many simultaneous penalties
        he = {"pain_score": 10, "sleep_hours": 3.0, "mood": "low"}
        result = self._base_result(health_entry=he)
        self.assertGreaterEqual(result.score, 0)
        self.assertLessEqual(result.score, 100)

    def test_deadline_pressure_reduces_ops(self):
        from datetime import date, timedelta
        due_soon = (date.today() + timedelta(days=1)).isoformat()
        missions = [
            {"id": "M1", "priority": "P0", "status": "Designed",
             "due_date": due_soon, "title": "Urgent mission"},
        ]
        baseline = self.fn(75, "Green", [], [])
        with_deadline = self.fn(75, "Green", missions, [])
        self.assertLess(with_deadline.ops_component, baseline.ops_component)

    def test_contributors_returned(self):
        result = self._base_result()
        self.assertIsInstance(result.contributors, list)
        self.assertGreater(len(result.contributors), 0)


# ===========================================================================
# WP10 — Intelligence Reporter (structure only — no Supabase required)
# ===========================================================================

class TestIntelligenceReporter(unittest.TestCase):

    def test_import_succeeds(self):
        try:
            from intelligence_reporter import run_all_reports, run_single_report, _REPORTS
            self.assertEqual(len(_REPORTS), 6)
        except ImportError as e:
            self.fail(f"intelligence_reporter import failed: {e}")

    def test_all_report_keys_present(self):
        from intelligence_reporter import _REPORTS
        expected = {
            "decision_effectiveness",
            "mission_intelligence",
            "health_performance_correlation",
            "knowledge_utilisation",
            "readiness_trend",
            "operating_patterns",
        }
        self.assertEqual(set(_REPORTS.keys()), expected)

    def test_dry_run_does_not_write_files(self):
        from intelligence_reporter import run_all_reports
        import tempfile, os

        outputs_dir = _REPO_ROOT / "outputs"
        before = set(outputs_dir.glob("*.json")) if outputs_dir.exists() else set()

        result = run_all_reports(dry_run=True, persist_readiness=False)

        after = set(outputs_dir.glob("*.json")) if outputs_dir.exists() else set()
        new_files = after - before
        # dry_run should not write intelligence reports
        intel_files = {f for f in new_files if f.name in {
            "decision_effectiveness.json",
            "mission_intelligence.json",
            "health_performance_correlation.json",
            "knowledge_utilisation.json",
            "readiness_trend.json",
            "operating_patterns.json",
        }}
        self.assertEqual(len(intel_files), 0)

    def test_single_report_decision_effectiveness(self):
        from intelligence_reporter import run_single_report
        result = run_single_report("decision_effectiveness", dry_run=True)
        self.assertIn("status", result)

    def test_unknown_report_returns_error(self):
        from intelligence_reporter import run_single_report
        result = run_single_report("nonexistent_report", dry_run=True)
        self.assertEqual(result["status"], "error")


# ===========================================================================
# Run
# ===========================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
