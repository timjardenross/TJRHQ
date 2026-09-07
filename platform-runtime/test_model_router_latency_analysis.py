"""
Tests for analysis/model_router_latency_analysis.py.

Never calls the real Model Router — router_call is patched at the call site
(analysis.model_router_latency_analysis.router_call) in every test.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "platform-runtime"))

from analysis.model_router_latency_analysis import ModelRouterLatencyAnalyzer  # noqa: E402


class TestAnalyzeLatency(unittest.TestCase):
    def setUp(self):
        self.analyzer = ModelRouterLatencyAnalyzer()

    def test_buckets_by_the_model_label_the_call_actually_reports(self):
        # Two prompts, both happen to be served by the same reported model —
        # the only case call() actually allows, since it can't request a
        # specific model (see module docstring).
        with patch(
            "analysis.model_router_latency_analysis.router_call",
            return_value=("a response", "model-router:engineering-review"),
        ):
            results = self.analyzer.analyze_latency(prompts=["p1", "p2"], samples_per_prompt=1)
        self.assertEqual(set(results.keys()), {"model-router:engineering-review"})
        self.assertEqual(results["model-router:engineering-review"]["count"], 2)

    def test_reports_distinct_models_separately_when_observed(self):
        responses = [("r1", "model-a"), ("r2", "model-b")]
        with patch("analysis.model_router_latency_analysis.router_call", side_effect=responses):
            results = self.analyzer.analyze_latency(prompts=["p1", "p2"], samples_per_prompt=1)
        self.assertEqual(set(results.keys()), {"model-a", "model-b"})
        self.assertEqual(results["model-a"]["count"], 1)
        self.assertEqual(results["model-b"]["count"], 1)

    def test_a_failed_call_is_skipped_not_raised(self):
        with patch(
            "analysis.model_router_latency_analysis.router_call",
            side_effect=RuntimeError("Model Router not reachable"),
        ):
            results = self.analyzer.analyze_latency(prompts=["p1"], samples_per_prompt=1)
        self.assertEqual(results, {})

    def test_stats_shape_has_avg_min_max_total_count(self):
        with patch("analysis.model_router_latency_analysis.router_call", return_value=("r", "model-a")):
            results = self.analyzer.analyze_latency(prompts=["p1"], samples_per_prompt=2)
        stats = results["model-a"]
        self.assertEqual(stats["count"], 2)
        self.assertGreaterEqual(stats["max_time"], stats["min_time"])
        self.assertGreaterEqual(stats["avg_time"], 0)
        self.assertAlmostEqual(stats["avg_time"], stats["total_time"] / stats["count"])


class TestGenerateRecommendations(unittest.TestCase):
    def setUp(self):
        self.analyzer = ModelRouterLatencyAnalyzer()

    def test_empty_results_says_check_connectivity_first(self):
        recs = self.analyzer.generate_recommendations({})
        self.assertEqual(len(recs), 1)
        self.assertIn("connectivity", recs[0])

    def test_single_model_flags_that_no_comparison_was_possible(self):
        results = {"model-a": {"count": 3, "total_time": 3.0, "avg_time": 1.0, "min_time": 0.9, "max_time": 1.1}}
        recs = self.analyzer.generate_recommendations(results)
        self.assertTrue(any("same model" in r for r in recs))

    def test_names_the_slowest_model_by_average(self):
        results = {
            "fast-model": {"count": 2, "total_time": 1.0, "avg_time": 0.5, "min_time": 0.4, "max_time": 0.6},
            "slow-model": {"count": 2, "total_time": 6.0, "avg_time": 3.0, "min_time": 2.9, "max_time": 3.1},
        }
        recs = self.analyzer.generate_recommendations(results)
        self.assertTrue(any("slow-model" in r and "highest average latency" in r for r in recs))

    def test_flags_high_variance_models(self):
        results = {
            "steady-model": {"count": 2, "total_time": 2.0, "avg_time": 1.0, "min_time": 0.95, "max_time": 1.05},
            "jittery-model": {"count": 2, "total_time": 5.0, "avg_time": 2.5, "min_time": 0.5, "max_time": 4.5},
        }
        recs = self.analyzer.generate_recommendations(results)
        variance_rec = next((r for r in recs if "variance" in r), None)
        self.assertIsNotNone(variance_rec)
        self.assertIn("jittery-model", variance_rec)
        self.assertNotIn("steady-model", variance_rec)

    def test_no_variance_flag_when_a_model_has_a_single_sample(self):
        # A lone sample has no spread to measure — must not be misreported
        # as "high variance".
        results = {"model-a": {"count": 1, "total_time": 5.0, "avg_time": 5.0, "min_time": 5.0, "max_time": 5.0}}
        recs = self.analyzer.generate_recommendations(results)
        self.assertFalse(any("variance" in r for r in recs))


if __name__ == "__main__":
    unittest.main()
