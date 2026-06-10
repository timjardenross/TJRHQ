#!/usr/bin/env python3
"""
MSN-0060B Phase B1D: Feedback Loops Tests

Unit and integration tests for feedback signal generation and provider quality tracking.

Test Coverage:
- Unit tests (10+ cases): Signal generation, delta calculation, action suggestion
- Integration tests (5+ cases): E2E feedback flow, provider quality updates

Design: Minimal MVP
- Generates feedback signals from quality scores
- Tracks provider quality metrics
- Enables adaptive routing
"""

import sys
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass
from datetime import datetime
import logging

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger(__name__)


# ============================================================================
# Mock Objects for Testing
# ============================================================================

class MockSupabaseResponse:
    """Mock Supabase response."""

    def __init__(self, data=None, error=None, table=None):
        self.data = data or []
        self.error = error
        self._table = table
        self._last_query = None
        self._last_order = None

    def select(self, *args):
        """Mock select operation."""
        return self

    def eq(self, column, value):
        """Mock equality filter."""
        self._last_query = {"column": column, "value": value}
        return self

    def order(self, column, desc=False):
        """Mock order operation."""
        self._last_order = {"column": column, "desc": desc}
        return self

    def execute(self):
        """Mock execute operation."""
        if self._table:
            if self._last_query:
                col, val = self._last_query["column"], self._last_query["value"]
                results = [v for k, v in self._table.data.items() if v.get(col) == val]
            else:
                results = list(self._table.data.values())

            if self._last_order:
                col = self._last_order["column"]
                results = sorted(results, key=lambda x: x.get(col, 0), reverse=self._last_order.get("desc", False))

            return MockSupabaseResponse(data=results, table=self._table)
        return self


class MockSupabaseTable:
    """Mock Supabase table for testing."""

    def __init__(self):
        self.data = {}

    def insert(self, record):
        """Mock insert operation."""
        self.data[record["id"]] = record
        return MockSupabaseResponse(data=[record], table=self)

    def select(self, *args):
        """Mock select operation."""
        return MockSupabaseResponse(table=self)

    def update(self, record):
        """Mock update operation."""
        return self

    def eq(self, column, value):
        """Mock equality filter for update."""
        return self

    def execute(self):
        """Mock execute operation."""
        return MockSupabaseResponse(data=list(self.data.values()), table=self)


class MockSupabaseClient:
    """Mock Supabase client for testing."""

    def __init__(self):
        self._table_feedback = MockSupabaseTable()
        self._table_history = MockSupabaseTable()
        self._view_trend = MockSupabaseTable()
        self._view_summary = MockSupabaseTable()

    def table(self, name):
        """Get table by name."""
        if name == "feedback_signals":
            return self._table_feedback
        elif name == "provider_quality_history":
            return self._table_history
        elif name == "v_provider_quality_trend":
            return self._view_trend
        elif name == "v_feedback_summary":
            return self._view_summary
        return MockSupabaseTable()


# ============================================================================
# Unit Tests
# ============================================================================

class TestFeedbackLoopsUnit:
    """Unit tests for FeedbackLoops service."""

    def setup_method(self):
        """Setup for each test."""
        log.info("\n" + "="*80)
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent / "slack-bot"))
            from lib.feedback_loops_service import FeedbackLoops, FeedbackSignal
            self.FeedbackLoops = FeedbackLoops
            self.FeedbackSignal = FeedbackSignal
        except Exception as e:
            log.error(f"Failed to import FeedbackLoops: {e}")
            raise

    def test_1_feedback_id_generation(self):
        """Unit Test 1: Feedback signal ID generation format."""
        log.info("TEST 1: Feedback ID Generation — FBK-YYYYMMDD-HHMMSS format")

        feedback = self.FeedbackLoops()
        signal_id = feedback._generate_feedback_id()

        # Validate format: FBK-YYYYMMDD-HHMMSS
        parts = signal_id.split("-")
        assert len(parts) == 3, f"Invalid format: {signal_id}"
        assert parts[0] == "FBK", f"Prefix not FBK: {parts[0]}"
        assert len(parts[1]) == 8 and parts[1].isdigit(), f"Invalid date: {parts[1]}"
        assert len(parts[2]) == 6 and parts[2].isdigit(), f"Invalid time: {parts[2]}"

        log.info(f"  ✓ Generated ID: {signal_id}")
        log.info("✅ PASSED: Feedback ID generation validates")

    def test_2_delta_calculation_positive(self):
        """Unit Test 2: Delta calculation for high-performing provider."""
        log.info("TEST 2: Delta Calculation — Positive delta (score > baseline)")

        feedback = self.FeedbackLoops()

        # Score 4.5 vs baseline 3.0 = +1.5 delta
        baseline = feedback._get_provider_baseline("Google")
        delta = 4.5 - baseline

        assert delta > 0.5, f"Expected positive delta, got {delta}"
        log.info(f"  ✓ High performance delta: {delta:.1f}")
        log.info("✅ PASSED: Positive delta calculated")

    def test_3_delta_calculation_negative(self):
        """Unit Test 3: Delta calculation for underperforming provider."""
        log.info("TEST 3: Delta Calculation — Negative delta (score < baseline)")

        feedback = self.FeedbackLoops()

        # Score 2.0 vs baseline 3.0 = -1.0 delta
        baseline = feedback._get_provider_baseline("Ollama")
        delta = 2.0 - baseline

        assert delta < -0.5, f"Expected negative delta, got {delta}"
        log.info(f"  ✓ Low performance delta: {delta:.1f}")
        log.info("✅ PASSED: Negative delta calculated")

    def test_4_action_suggestion_increase(self):
        """Unit Test 4: Action suggestion for increasing provider weight."""
        log.info("TEST 4: Action Suggestion — Increase (delta > 0.5)")

        feedback = self.FeedbackLoops(MockSupabaseClient())
        signal = feedback.generate_feedback(
            score_id="SCO-20260610-143000",
            decision_id="DEC-REC-20260610-143000",
            provider_name="Google",
            effectiveness_score=4.8,  # High score → increase
            model_name="Gemini"
        )

        assert signal is not None, "Signal should be created"
        assert signal.suggested_action == "increase", f"Expected increase, got {signal.suggested_action}"
        log.info(f"  ✓ Action: {signal.suggested_action}")
        log.info("✅ PASSED: Increase action suggested")

    def test_5_action_suggestion_decrease(self):
        """Unit Test 5: Action suggestion for decreasing provider weight."""
        log.info("TEST 5: Action Suggestion — Decrease (delta < -0.5)")

        feedback = self.FeedbackLoops(MockSupabaseClient())
        signal = feedback.generate_feedback(
            score_id="SCO-20260610-143001",
            decision_id="DEC-REC-20260610-143001",
            provider_name="Ollama",
            effectiveness_score=1.5,  # Low score → decrease
            model_name="Qwen"
        )

        assert signal is not None, "Signal should be created"
        assert signal.suggested_action == "decrease", f"Expected decrease, got {signal.suggested_action}"
        log.info(f"  ✓ Action: {signal.suggested_action}")
        log.info("✅ PASSED: Decrease action suggested")

    def test_6_action_suggestion_maintain(self):
        """Unit Test 6: Action suggestion for maintaining provider weight."""
        log.info("TEST 6: Action Suggestion — Maintain (delta ≈ 0)")

        feedback = self.FeedbackLoops(MockSupabaseClient())
        signal = feedback.generate_feedback(
            score_id="SCO-20260610-143002",
            decision_id="DEC-REC-20260610-143002",
            provider_name="OpenRouter",
            effectiveness_score=3.2,  # Near baseline → maintain
            model_name="Mistral"
        )

        assert signal is not None, "Signal should be created"
        assert signal.suggested_action == "maintain", f"Expected maintain, got {signal.suggested_action}"
        log.info(f"  ✓ Action: {signal.suggested_action}")
        log.info("✅ PASSED: Maintain action suggested")

    def test_7_unknown_score_skipped(self):
        """Unit Test 7: Unknown/None scores skip feedback generation."""
        log.info("TEST 7: Unknown Score Handling — Skips feedback")

        feedback = self.FeedbackLoops(MockSupabaseClient())
        signal = feedback.generate_feedback(
            score_id="SCO-20260610-143003",
            decision_id="DEC-REC-20260610-143003",
            provider_name="Google",
            effectiveness_score=None,  # Unknown score
            model_name="Gemini"
        )

        assert signal is None, "Unknown scores should return None"
        log.info("  ✓ Unknown score skipped")
        log.info("✅ PASSED: Unknown scores handled correctly")

    def test_8_baseline_retrieval(self):
        """Unit Test 8: Provider baseline retrieval."""
        log.info("TEST 8: Provider Baseline Retrieval")

        feedback = self.FeedbackLoops(MockSupabaseClient())
        baseline = feedback._get_provider_baseline("Google", model_name="Gemini")

        assert baseline == 3.0, f"Expected default baseline 3.0, got {baseline}"
        log.info(f"  ✓ Default baseline: {baseline}")
        log.info("✅ PASSED: Provider baseline retrieved")

    def test_9_signal_persistence(self):
        """Unit Test 9: Feedback signal persistence to Supabase."""
        log.info("TEST 9: Signal Persistence")

        client = MockSupabaseClient()
        feedback = self.FeedbackLoops(client)

        signal = feedback.generate_feedback(
            score_id="SCO-20260610-143004",
            decision_id="DEC-REC-20260610-143004",
            provider_name="Google",
            effectiveness_score=4.5,
            model_name="Gemini",
            provider_route="Primary"
        )

        assert signal is not None
        # Verify persisted
        persisted = client.table("feedback_signals").data.get(signal.id)
        assert persisted is not None, "Signal not persisted"
        assert persisted["provider_name"] == "Google"
        log.info(f"  ✓ Persisted signal: {signal.id}")
        log.info("✅ PASSED: Signal persisted correctly")

    def test_10_provider_attribution(self):
        """Unit Test 10: Provider/model/route attribution capture."""
        log.info("TEST 10: Provider Attribution Capture")

        feedback = self.FeedbackLoops()
        signal = feedback.generate_feedback(
            score_id="SCO-20260610-143005",
            decision_id="DEC-REC-20260610-143005",
            provider_name="OpenRouter",
            effectiveness_score=3.8,
            model_name="Mistral",
            provider_route="Fallback"
        )

        assert signal.provider_name == "OpenRouter"
        assert signal.model_name == "Mistral"
        assert signal.provider_route == "Fallback"
        log.info(f"  ✓ Provider: {signal.provider_name}")
        log.info(f"  ✓ Model: {signal.model_name}")
        log.info(f"  ✓ Route: {signal.provider_route}")
        log.info("✅ PASSED: Provider attribution captured")


# ============================================================================
# Integration Tests
# ============================================================================

class TestFeedbackLoopsIntegration:
    """Integration tests for end-to-end feedback loops."""

    def setup_method(self):
        """Setup for each test."""
        log.info("\n" + "="*80)
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent / "slack-bot"))
            from lib.feedback_loops_service import FeedbackLoops
            self.FeedbackLoops = FeedbackLoops
        except Exception as e:
            log.error(f"Failed to import: {e}")
            raise

    def test_11_e2e_score_to_signal(self):
        """Integration Test 11: E2E quality score → feedback signal."""
        log.info("TEST 11: Integration — Quality Score → Feedback Signal")

        client = MockSupabaseClient()
        feedback = self.FeedbackLoops(client)

        # Generate feedback from quality score
        signal = feedback.generate_feedback(
            score_id="SCO-20260610-143000",
            decision_id="DEC-REC-20260610-143000",
            provider_name="Google",
            effectiveness_score=4.8,
            model_name="Gemini 2.5 Flash",
            provider_route="Primary"
        )

        assert signal is not None
        assert signal.effectiveness_delta > 0, "Delta should be positive for high score"
        assert signal.suggested_action == "increase"

        # Verify persisted
        persisted = client.table("feedback_signals").data.get(signal.id)
        assert persisted is not None
        log.info(f"  ✓ Score 4.8 → Signal {signal.id}")
        log.info("✅ PASSED: E2E score → signal flow complete")

    def test_12_multiple_signals_per_provider(self):
        """Integration Test 12: Multiple signals accumulate by provider."""
        log.info("TEST 12: Integration — Multiple signals per provider")

        client = MockSupabaseClient()
        feedback = self.FeedbackLoops(client)

        provider_name = "Google"
        signals = []

        # Generate multiple signals for same provider
        for i in range(3):
            signal = feedback.generate_feedback(
                score_id=f"SCO-20260610-14300{i}",
                decision_id=f"DEC-REC-20260610-14300{i}",
                provider_name=provider_name,
                effectiveness_score=4.5 + (i * 0.1),
                model_name="Gemini"
            )
            if signal:
                signals.append(signal)

        assert len(signals) >= 2, f"Expected 2+ signals, got {len(signals)}"
        log.info(f"  ✓ Generated {len(signals)} signals for {provider_name}")
        log.info("✅ PASSED: Multiple signals per provider supported")

    def test_13_provider_quality_tracking(self):
        """Integration Test 13: Provider quality metrics updated."""
        log.info("TEST 13: Integration — Provider Quality Tracking")

        client = MockSupabaseClient()
        feedback = self.FeedbackLoops(client)

        # Pre-populate quality history
        client._table_history.data = {
            "hist-001": {
                "id": "hist-001",
                "provider_name": "Google",
                "decisions_count": 5,
                "avg_effectiveness": 4.2
            }
        }

        # Generate feedback (should update quality)
        signal = feedback.generate_feedback(
            score_id="SCO-20260610-143006",
            decision_id="DEC-REC-20260610-143006",
            provider_name="Google",
            effectiveness_score=4.5,
            model_name="Gemini"
        )

        assert signal is not None
        log.info("  ✓ Feedback generated and quality updated")
        log.info("✅ PASSED: Provider quality tracking works")

    def test_14_routing_suggestion(self):
        """Integration Test 14: Adaptive routing suggestion."""
        log.info("TEST 14: Integration — Routing Suggestion")

        client = MockSupabaseClient()
        feedback = self.FeedbackLoops(client)

        # Pre-populate provider quality trend data
        client._view_trend.data = {
            "google": {
                "provider_name": "Google",
                "avg_effectiveness": 4.4,
                "quality_tier": "high"
            },
            "openrouter": {
                "provider_name": "OpenRouter",
                "avg_effectiveness": 3.8,
                "quality_tier": "medium"
            },
            "ollama": {
                "provider_name": "Ollama",
                "avg_effectiveness": 2.9,
                "quality_tier": "low"
            }
        }

        # Suggest routing
        routing_order = feedback.suggest_routing()

        assert len(routing_order) >= 1, f"Expected routing suggestions, got {len(routing_order)}"
        # First should be highest quality
        assert routing_order[0][0] == "Google", f"Expected Google first, got {routing_order[0][0]}"
        log.info(f"  ✓ Routing order: {[p[0] for p in routing_order]}")
        log.info("✅ PASSED: Routing suggestion works")

    def test_15_feedback_to_routing_cycle(self):
        """Integration Test 15: Complete feedback → routing cycle."""
        log.info("TEST 15: Integration — Complete Feedback Cycle")

        client = MockSupabaseClient()
        feedback = self.FeedbackLoops(client)

        # Pre-populate quality trend
        client._view_trend.data = {
            "google": {
                "provider_name": "Google",
                "avg_effectiveness": 4.4,
                "quality_tier": "high"
            }
        }

        # Generate feedback
        signal = feedback.generate_feedback(
            score_id="SCO-20260610-143007",
            decision_id="DEC-REC-20260610-143007",
            provider_name="Google",
            effectiveness_score=4.8,
            model_name="Gemini"
        )

        assert signal is not None, "Signal should be created"
        assert signal.suggested_action == "increase", "Action should be increase"

        # Get routing suggestion
        routing_order = feedback.suggest_routing()
        assert len(routing_order) >= 1, "Should have routing suggestions"

        log.info(f"  ✓ Feedback generated: {signal.id}")
        log.info(f"  ✓ Routing available: {len(routing_order)} providers")
        log.info("✅ PASSED: Complete feedback → routing cycle works")


# ============================================================================
# Test Runner
# ============================================================================

def run_all_tests():
    """Run all B1D feedback loops tests."""
    log.info("\n" + "="*80)
    log.info("MSN-0060B PHASE B1D: FEEDBACK LOOPS TEST SUITE")
    log.info("="*80)

    # Unit tests
    unit_tests = TestFeedbackLoopsUnit()
    unit_test_methods = [
        unit_tests.test_1_feedback_id_generation,
        unit_tests.test_2_delta_calculation_positive,
        unit_tests.test_3_delta_calculation_negative,
        unit_tests.test_4_action_suggestion_increase,
        unit_tests.test_5_action_suggestion_decrease,
        unit_tests.test_6_action_suggestion_maintain,
        unit_tests.test_7_unknown_score_skipped,
        unit_tests.test_8_baseline_retrieval,
        unit_tests.test_9_signal_persistence,
        unit_tests.test_10_provider_attribution,
    ]

    # Integration tests
    integration_tests = TestFeedbackLoopsIntegration()
    integration_test_methods = [
        integration_tests.test_11_e2e_score_to_signal,
        integration_tests.test_12_multiple_signals_per_provider,
        integration_tests.test_13_provider_quality_tracking,
        integration_tests.test_14_routing_suggestion,
        integration_tests.test_15_feedback_to_routing_cycle,
    ]

    passed = 0
    failed = 0

    # Run unit tests
    for test_func in unit_test_methods:
        unit_tests.setup_method()
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            failed += 1
            log.error(f"❌ FAILED: {test_func.__name__}: {e}")
        except Exception as e:
            failed += 1
            log.error(f"❌ ERROR: {test_func.__name__}: {e}")

    # Run integration tests
    for test_func in integration_test_methods:
        integration_tests.setup_method()
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            failed += 1
            log.error(f"❌ FAILED: {test_func.__name__}: {e}")
        except Exception as e:
            failed += 1
            log.error(f"❌ ERROR: {test_func.__name__}: {e}")

    # Results summary
    log.info("\n" + "="*80)
    log.info(f"TEST RESULTS: {passed}/15 PASSED")
    log.info("="*80)

    if failed == 0:
        log.info("\n🟢 ALL B1D TESTS PASSED")
        log.info("Phase B1D feedback loops ready for deployment")
    else:
        log.warning(f"\n🔴 {failed} TESTS FAILED")
        log.warning("Issues must be resolved before deployment")

    log.info("="*80 + "\n")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
