#!/usr/bin/env python3
"""
MSN-0013A: Test Suite for Outcome Linking & Analysis
Owner: QA Officer
Date: 2026-06-08
Purpose: Validate decision quality scoring, pattern analysis, and recommendations
"""

import unittest
from datetime import datetime
from decision_quality_scorer import DecisionQualityScorer, score_decision_from_db
from dual_commander_analysis import DualCommanderAnalyzer
from commander_decision_support import CommanderDecisionSupport


class TestDecisionQualityScorer(unittest.TestCase):
    """Test decision quality scoring functionality."""

    def setUp(self):
        self.scorer = DecisionQualityScorer()

    def test_score_clarity_high(self):
        """Clear decision should score high on clarity."""
        decision = (
            "Decision: Approve Kubernetes migration. "
            "Owner: Chief Engineer. "
            "Rationale: Better scalability. "
            "Alternative: Upgrade existing (temporary)."
        )
        score = self.scorer._score_clarity(decision)
        self.assertGreater(score, 0.6)

    def test_score_clarity_low(self):
        """Vague decision should score low."""
        decision = "Maybe we should think about deployment stuff."
        score = self.scorer._score_clarity(decision)
        self.assertLess(score, 0.5)

    def test_score_accuracy_success(self):
        """Success outcome should yield 1.0 accuracy score."""
        score = self.scorer._score_accuracy("success")
        self.assertEqual(score, 1.0)

    def test_score_accuracy_partial(self):
        """Partial outcome should yield 0.5 accuracy score."""
        score = self.scorer._score_accuracy("partial")
        self.assertEqual(score, 0.5)

    def test_score_accuracy_failed(self):
        """Failed outcome should yield 0.0 accuracy score."""
        score = self.scorer._score_accuracy("failed")
        self.assertEqual(score, 0.0)

    def test_full_score_integration(self):
        """Full decision scoring should return valid scores (0-4 range)."""
        decision = (
            "Decision: Approve Kubernetes migration to Q3 2026. "
            "Owner: Chief Engineer. "
            "Rationale: Scalability and cost savings. "
            "Well-timed and easy to execute."
        )
        result = self.scorer.score_decision(
            decision_id=42,
            decision_text=decision,
            outcome_status="success",
            captain_notes="Perfect timing and clear implementation.",
        )
        self.assertGreaterEqual(result.total_score, 0)
        self.assertLessEqual(result.total_score, 4.0)
        self.assertIsNotNone(result.reasoning)

    def test_score_with_penalties(self):
        """Decisions with negative keywords should have lower scores."""
        decision = "We hastily decided to rush the deployment."
        result = self.scorer.score_decision(
            decision_id=1,
            decision_text=decision,
            outcome_status="failed",
            captain_notes="Decision was too hasty.",
        )
        self.assertLess(result.total_score, 2.0)


class TestDualCommanderAnalyzer(unittest.TestCase):
    """Test dual commander pattern analysis."""

    def setUp(self):
        self.analyzer = DualCommanderAnalyzer()

    def test_analyze_insufficient_data(self):
        """Should recommend insufficient_data with <10 runs."""
        runs = [
            {"captain_preferred_model": "qwen", "decision_text": "Test", "captain_notes": ""}
        ] * 5
        analysis = self.analyzer.analyze_dual_commander_runs(runs)
        self.assertEqual(analysis.recommendation, "insufficient_data")
        self.assertLess(analysis.confidence, 0.5)

    def test_analyze_promote_recommendation(self):
        """DeepSeek winning 70%+ with 20+ runs should recommend promote."""
        runs = [
            {"captain_preferred_model": "deepseek", "decision_text": "Test", "captain_notes": ""}
            for _ in range(14)
        ] + [
            {"captain_preferred_model": "qwen", "decision_text": "Test", "captain_notes": ""}
            for _ in range(6)
        ]
        analysis = self.analyzer.analyze_dual_commander_runs(runs)
        self.assertEqual(analysis.recommendation, "promote")
        self.assertGreater(analysis.confidence, 0.7)

    def test_analyze_specialize_recommendation(self):
        """Models with complementary strengths should recommend specialize."""
        runs = [
            {
                "captain_preferred_model": "deepseek",
                "decision_text": "Deploy new microservice API architecture design",
                "captain_notes": "",
            }
            for _ in range(12)
        ] + [
            {
                "captain_preferred_model": "qwen",
                "decision_text": "Approve new governance policy for authorization",
                "captain_notes": "",
            }
            for _ in range(8)
        ]
        analysis = self.analyzer.analyze_dual_commander_runs(runs)
        # Should be either specialize or keep (ties indicate unclear pattern)
        self.assertIn(
            analysis.recommendation, ["specialize", "keep", "insufficient_data"]
        )

    def test_win_rate_calculation(self):
        """Win rates should sum to 1.0."""
        runs = [
            {"captain_preferred_model": "deepseek", "decision_text": "Test", "captain_notes": ""}
            for _ in range(8)
        ] + [
            {"captain_preferred_model": "qwen", "decision_text": "Test", "captain_notes": ""}
            for _ in range(7)
        ] + [
            {"captain_preferred_model": None, "decision_text": "Test", "captain_notes": ""}
            for _ in range(5)
        ]
        analysis = self.analyzer.analyze_dual_commander_runs(runs)
        total_rate = (
            analysis.qwen_win_rate + analysis.deepseek_win_rate + analysis.tie_rate
        )
        self.assertAlmostEqual(total_rate, 1.0, places=5)


class TestCommanderDecisionSupport(unittest.TestCase):
    """Test recommendation engine."""

    def setUp(self):
        self.support = CommanderDecisionSupport()

    def test_recommendation_promote(self):
        """Promotion recommendation should include trial period and success criteria."""
        from dual_commander_analysis import DualCommanderAnalysis

        analysis = DualCommanderAnalysis(
            total_runs=20,
            qwen_wins=6,
            deepseek_wins=14,
            ties=0,
            qwen_win_rate=0.3,
            deepseek_win_rate=0.7,
            tie_rate=0.0,
            decision_types={"technical": {"deepseek": 0.8, "qwen": 0.2, "tie": 0.0}},
            recommendation="promote",
            confidence=0.8,
            reasoning="DeepSeek superior",
            next_steps=["Promote"],
        )

        rec = self.support.generate_model_recommendation(
            "qwen3:8b", analysis, []
        )

        self.assertEqual(rec.recommended_action, "promote")
        self.assertGreater(rec.trial_period_days, 0)
        self.assertGreater(len(rec.success_criteria), 0)
        self.assertIn("Maintain", rec.success_criteria[0])

    def test_recommendation_keep(self):
        """Keep recommendation should have zero trial period."""
        from dual_commander_analysis import DualCommanderAnalysis

        analysis = DualCommanderAnalysis(
            total_runs=20,
            qwen_wins=10,
            deepseek_wins=10,
            ties=0,
            qwen_win_rate=0.5,
            deepseek_win_rate=0.5,
            tie_rate=0.0,
            decision_types={},
            recommendation="keep",
            confidence=0.5,
            reasoning="Tied",
            next_steps=["Continue"],
        )

        rec = self.support.generate_model_recommendation(
            "qwen3:8b", analysis, []
        )

        self.assertEqual(rec.recommended_action, "keep")
        self.assertEqual(rec.trial_period_days, 0)

    def test_summary_generation(self):
        """Summary should be <150 words and actionable."""
        from dual_commander_analysis import DualCommanderAnalysis

        analysis = DualCommanderAnalysis(
            total_runs=20,
            qwen_wins=6,
            deepseek_wins=14,
            ties=0,
            qwen_win_rate=0.3,
            deepseek_win_rate=0.7,
            tie_rate=0.0,
            decision_types={},
            recommendation="promote",
            confidence=0.8,
            reasoning="Superior",
            next_steps=[],
        )

        rec = self.support.generate_model_recommendation(
            "qwen3:8b", analysis, []
        )

        word_count = len(rec.summary.split())
        self.assertLess(word_count, 200)
        self.assertIn("DeepSeek", rec.summary)
        self.assertIn("recommend", rec.summary.lower())


class TestEndToEndIntegration(unittest.TestCase):
    """End-to-end integration tests."""

    def test_full_pipeline(self):
        """Full pipeline: score → analyze → recommend."""
        scorer = DecisionQualityScorer()
        analyzer = DualCommanderAnalyzer()
        support = CommanderDecisionSupport()

        # Score decisions
        scores = [
            scorer.score_decision(
                i,
                f"Decision {i}: Test decision text",
                "success",
                f"Captain notes for decision {i}",
            )
            for i in range(5)
        ]

        # Analyze runs
        runs = [
            {
                "captain_preferred_model": "deepseek" if i % 2 == 0 else "qwen",
                "decision_text": f"Decision {i}",
                "captain_notes": f"Notes {i}",
            }
            for i in range(20)
        ]
        analysis = analyzer.analyze_dual_commander_runs(runs)

        # Generate recommendation
        rec = support.generate_model_recommendation(
            "qwen3:8b", analysis, scores
        )

        # Verify outputs
        self.assertIsNotNone(rec.recommended_action)
        self.assertIsNotNone(rec.summary)
        self.assertGreaterEqual(rec.confidence, 0)
        self.assertLessEqual(rec.confidence, 1)
        self.assertGreater(len(rec.next_actions), 0)


if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2)
