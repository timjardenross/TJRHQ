"""
Tests for scripts/self_improvement/calibration.py — HQ Evolution
calibration scoring (Fatebook-style predicted-fit-vs-actual-outcome).

Same bare-sibling-import convention as test_hq_evolution.py (this directory
runs with its own directory as cwd/sys.path[0], not a `scripts.self_
improvement.X` package import). Every test points OpportunityStore at a
temp directory — none of these may write into the committed
data/self-improvement tree.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SELF_IMPROVEMENT_DIR = REPO_ROOT / "scripts" / "self_improvement"
sys.path.insert(0, str(SELF_IMPROVEMENT_DIR))

import calibration
from opportunity_store import OpportunityStore


def _make_opportunity(store, *, fit, relevance_score, outcome_result, **extra):
    opp = store.create_new(
        title=extra.pop("title", f"candidate for {fit}/{outcome_result}"),
        change_class="capability",
        discovery_source="internal",
        fit=fit,
        relevance_score=relevance_score,
        lifecycle_state="learned",
        **extra,
    )
    if outcome_result is not None:
        store.update(opp.opportunity_id, outcome={"outcome_result": outcome_result})
    return opp


class CalibrationTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = OpportunityStore(Path(self.tmpdir))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestScoredOpportunities(CalibrationTestCase):
    def test_only_resolved_outcomes_counted(self):
        _make_opportunity(self.store, fit="strong", relevance_score=0.9, outcome_result="improved")
        _make_opportunity(self.store, fit="weak", relevance_score=0.2, outcome_result=None)  # unresolved
        scored = calibration._scored_opportunities(self.store)
        self.assertEqual(len(scored), 1)

    def test_not_yet_ready_excluded(self):
        """An open observation window is not a resolved verdict — must never
        silently count as a data point either way."""
        _make_opportunity(self.store, fit="strong", relevance_score=0.9, outcome_result="not_yet_ready")
        scored = calibration._scored_opportunities(self.store)
        self.assertEqual(len(scored), 0)

    def test_outcome_scores_mapped_correctly(self):
        _make_opportunity(self.store, fit="strong", relevance_score=0.9, outcome_result="improved")
        _make_opportunity(self.store, fit="moderate", relevance_score=0.5, outcome_result="no_material_change")
        _make_opportunity(self.store, fit="weak", relevance_score=0.1, outcome_result="regressed")
        scored = sorted(s for s, _ in calibration._scored_opportunities(self.store))
        self.assertEqual(scored, [0.0, 0.5, 1.0])

    def test_rejected_opportunity_never_scored(self):
        """No outcome_result exists for something never implemented —
        must not be silently treated as a failure."""
        self.store.create_new(
            title="rejected candidate", change_class="capability", discovery_source="internal",
            fit="weak", relevance_score=0.1, lifecycle_state="rejected",
        )
        scored = calibration._scored_opportunities(self.store)
        self.assertEqual(len(scored), 0)


class TestFitAlignment(CalibrationTestCase):
    def test_insufficient_data_reported_honestly(self):
        _make_opportunity(self.store, fit="strong", relevance_score=0.9, outcome_result="improved")
        result = calibration.fit_alignment(self.store)
        self.assertIsNone(result["aligned"])
        self.assertFalse(result["sufficient"])

    def test_well_calibrated_case(self):
        for _ in range(3):
            _make_opportunity(self.store, fit="strong", relevance_score=0.9, outcome_result="improved")
        for _ in range(3):
            _make_opportunity(self.store, fit="weak", relevance_score=0.1, outcome_result="regressed")
        result = calibration.fit_alignment(self.store)
        self.assertTrue(result["aligned"])
        self.assertEqual(result["by_band"]["strong"]["success_rate"], 1.0)
        self.assertEqual(result["by_band"]["weak"]["success_rate"], 0.0)

    def test_miscalibrated_case(self):
        """Weak-fit candidates outperforming strong-fit ones — must be
        flagged as miscalibrated, not silently reported as fine."""
        for _ in range(3):
            _make_opportunity(self.store, fit="strong", relevance_score=0.9, outcome_result="regressed")
        for _ in range(3):
            _make_opportunity(self.store, fit="weak", relevance_score=0.1, outcome_result="improved")
        result = calibration.fit_alignment(self.store)
        self.assertFalse(result["aligned"])

    def test_unknown_fit_value_excluded_from_bands(self):
        _make_opportunity(self.store, fit=None, relevance_score=0.5, outcome_result="improved")
        result = calibration.fit_alignment(self.store)
        self.assertEqual(result["samples"], 0)


class TestRelevanceScoreCalibration(CalibrationTestCase):
    def test_no_data_reported_honestly(self):
        result = calibration.relevance_score_calibration(self.store)
        self.assertEqual(result["samples"], 0)
        self.assertIsNone(result["brier_score"])

    def test_perfect_calibration_gives_zero_brier(self):
        _make_opportunity(self.store, fit="strong", relevance_score=1.0, outcome_result="improved")
        _make_opportunity(self.store, fit="weak", relevance_score=0.0, outcome_result="regressed")
        result = calibration.relevance_score_calibration(self.store)
        self.assertEqual(result["brier_score"], 0.0)

    def test_worst_case_calibration_gives_high_brier(self):
        """Predicted 1.0, actual failure (and vice versa) — the Brier score
        must reflect maximally wrong predictions, not average them away."""
        _make_opportunity(self.store, fit="strong", relevance_score=1.0, outcome_result="regressed")
        _make_opportunity(self.store, fit="weak", relevance_score=0.0, outcome_result="improved")
        result = calibration.relevance_score_calibration(self.store)
        self.assertEqual(result["brier_score"], 1.0)

    def test_missing_relevance_score_excluded_not_treated_as_zero(self):
        _make_opportunity(self.store, fit="strong", relevance_score=None, outcome_result="improved")
        result = calibration.relevance_score_calibration(self.store)
        self.assertEqual(result["samples"], 0)

    def test_buckets_cover_full_range(self):
        _make_opportunity(self.store, fit="weak", relevance_score=0.1, outcome_result="regressed")
        _make_opportunity(self.store, fit="moderate", relevance_score=0.5, outcome_result="no_material_change")
        _make_opportunity(self.store, fit="strong", relevance_score=0.95, outcome_result="improved")
        result = calibration.relevance_score_calibration(self.store, n_buckets=3)
        self.assertEqual(len(result["buckets"]), 3)
        # A score of exactly 1.0 must land in the last bucket, not be dropped.
        _make_opportunity(self.store, fit="strong", relevance_score=1.0, outcome_result="improved")
        result = calibration.relevance_score_calibration(self.store, n_buckets=3)
        self.assertEqual(result["buckets"][-1]["samples"], 2)


class TestCalibrationReport(CalibrationTestCase):
    def test_report_shape_with_no_data(self):
        report = calibration.calibration_report(self.store)
        self.assertEqual(report["total_resolved_opportunities"], 0)
        self.assertFalse(report["sufficient_data"])
        self.assertIn("fit_alignment", report)
        self.assertIn("relevance_score_calibration", report)

    def test_report_with_data_is_sufficient(self):
        for _ in range(3):
            _make_opportunity(self.store, fit="strong", relevance_score=0.9, outcome_result="improved")
        report = calibration.calibration_report(self.store)
        self.assertEqual(report["total_resolved_opportunities"], 3)
        self.assertTrue(report["sufficient_data"])
        self.assertEqual(report["overall_success_rate"], 1.0)


class TestToMarkdown(CalibrationTestCase):
    def test_renders_without_error_on_empty_store(self):
        report = calibration.calibration_report(self.store)
        md = calibration.to_markdown(report)
        self.assertIn("HQ Evolution Calibration", md)
        self.assertIn("provisional", md)

    def test_renders_bands_and_brier_score_with_data(self):
        for _ in range(3):
            _make_opportunity(self.store, fit="strong", relevance_score=0.9, outcome_result="improved")
        for _ in range(3):
            _make_opportunity(self.store, fit="weak", relevance_score=0.1, outcome_result="regressed")
        report = calibration.calibration_report(self.store)
        md = calibration.to_markdown(report)
        self.assertIn("Brier score", md)
        self.assertIn("strong:", md)
        self.assertIn("weak:", md)


if __name__ == "__main__":
    unittest.main()
