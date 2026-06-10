#!/usr/bin/env python3
"""
MSN-0060B Phase B1C: Quality Scoring Tests

Unit and integration tests for decision outcome quality scoring.

Test Coverage:
- Unit tests (10+ cases): Score calculation, reason generation, queries
- Integration tests (5+ cases): E2E scoring flow, provider analysis

Design: Minimal MVP
- Scores outcome effectiveness (1-5 scale)
- Generates scoring reasons
- Captures provider/model/route attribution
- Enables quality analysis by provider/model/route
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


class MockSupabaseClient:
    """Mock Supabase client for testing."""

    def __init__(self):
        self._table_quality = MockSupabaseTable()
        self._view_provider = MockSupabaseTable()
        self._view_model = MockSupabaseTable()
        self._view_route = MockSupabaseTable()

    def table(self, name):
        """Get table by name."""
        if name == "quality_scores":
            return self._table_quality
        elif name == "v_provider_quality":
            return self._view_provider
        elif name == "v_model_quality":
            return self._view_model
        elif name == "v_route_quality":
            return self._view_route
        return MockSupabaseTable()


# ============================================================================
# Unit Tests
# ============================================================================

class TestQualityScoringUnit:
    """Unit tests for QualityScoring service."""

    def setup_method(self):
        """Setup for each test."""
        log.info("\n" + "="*80)
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent / "slack-bot"))
            from lib.quality_scoring_service import QualityScoring, QualityScore
            self.QualityScoring = QualityScoring
            self.QualityScore = QualityScore
        except Exception as e:
            log.error(f"Failed to import QualityScoring: {e}")
            raise

    def test_1_score_id_generation(self):
        """Unit Test 1: Quality score ID generation format."""
        log.info("TEST 1: Score ID Generation — SCO-YYYYMMDD-HHMMSS format")

        scoring = self.QualityScoring()
        score_id = scoring._generate_score_id()

        # Validate format: SCO-YYYYMMDD-HHMMSS
        parts = score_id.split("-")
        assert len(parts) == 3, f"Invalid format: {score_id}"
        assert parts[0] == "SCO", f"Prefix not SCO: {parts[0]}"
        assert len(parts[1]) == 8 and parts[1].isdigit(), f"Invalid date: {parts[1]}"
        assert len(parts[2]) == 6 and parts[2].isdigit(), f"Invalid time: {parts[2]}"

        log.info(f"  ✓ Generated ID: {score_id}")
        log.info("✅ PASSED: Score ID generation validates")

    def test_2_score_calculation_implemented(self):
        """Unit Test 2: Score calculation for Implemented outcome."""
        log.info("TEST 2: Score Calculation — Implemented status")

        scoring = self.QualityScoring()

        # Implemented without modification → 5.0
        score1 = scoring._calculate_score("Implemented", "Executed as planned")
        assert score1 == 5.0, f"Expected 5.0, got {score1}"
        log.info(f"  ✓ Implemented (no mods) = {score1}")

        # Implemented with modification → 4.0
        score2 = scoring._calculate_score("Implemented", "Executed with modified approach")
        assert score2 == 4.0, f"Expected 4.0, got {score2}"
        log.info(f"  ✓ Implemented (with mods) = {score2}")

        log.info("✅ PASSED: Implemented outcome scoring correct")

    def test_3_score_calculation_modified(self):
        """Unit Test 3: Score calculation for Modified outcome."""
        log.info("TEST 3: Score Calculation — Modified status")

        scoring = self.QualityScoring()

        # Modified beneficial → 3.5
        score1 = scoring._calculate_score("Modified", "Changes were positive and improved results")
        assert score1 == 3.5, f"Expected 3.5, got {score1}"
        log.info(f"  ✓ Modified (beneficial) = {score1}")

        # Modified other → 3.0
        score2 = scoring._calculate_score("Modified", "Changed but still functional")
        assert score2 == 3.0, f"Expected 3.0, got {score2}"
        log.info(f"  ✓ Modified (other) = {score2}")

        log.info("✅ PASSED: Modified outcome scoring correct")

    def test_4_score_calculation_deferred(self):
        """Unit Test 4: Score calculation for Deferred outcome."""
        log.info("TEST 4: Score Calculation — Deferred status")

        scoring = self.QualityScoring()

        # Deferred temporary → 3.0
        score1 = scoring._calculate_score("Deferred", "Deferred short-term, will resume in Q3")
        assert score1 == 3.0, f"Expected 3.0, got {score1}"
        log.info(f"  ✓ Deferred (temporary) = {score1}")

        # Deferred indefinite → 2.0
        score2 = scoring._calculate_score("Deferred", "Postponed indefinitely due to resource constraints")
        assert score2 == 2.0, f"Expected 2.0, got {score2}"
        log.info(f"  ✓ Deferred (indefinite) = {score2}")

        log.info("✅ PASSED: Deferred outcome scoring correct")

    def test_5_score_calculation_rejected(self):
        """Unit Test 5: Score calculation for Rejected outcome."""
        log.info("TEST 5: Score Calculation — Rejected status")

        scoring = self.QualityScoring()

        score = scoring._calculate_score("Rejected", "Decision rejected by leadership")
        assert score == 1.0, f"Expected 1.0, got {score}"
        log.info(f"  ✓ Rejected = {score}")
        log.info("✅ PASSED: Rejected outcome scoring correct")

    def test_6_score_calculation_unknown(self):
        """Unit Test 6: Score calculation for Unknown outcome."""
        log.info("TEST 6: Score Calculation — Unknown status")

        scoring = self.QualityScoring()

        score = scoring._calculate_score("Unknown", "Status unclear")
        assert score is None, f"Expected None, got {score}"
        log.info(f"  ✓ Unknown = {score}")
        log.info("✅ PASSED: Unknown outcome scoring correct")

    def test_7_reason_generation(self):
        """Unit Test 7: Scoring reason generation."""
        log.info("TEST 7: Reason Generation")

        scoring = self.QualityScoring()

        reasons = {
            5.0: "Decision executed as planned with positive results",
            4.0: "Decision executed with minor modifications, achieved objectives",
            3.5: "Decision modified during implementation, modifications were beneficial",
            3.0: "Decision deferred initially but completed with acceptable results",
            2.0: "Decision was deferred and not yet completed",
            1.0: "Decision was rejected and never executed",
            None: "Outcome status unknown, pending clarification",
        }

        for score, expected_reason in reasons.items():
            reason = scoring._generate_reason(score, "test_status")
            assert reason == expected_reason, f"Score {score}: got '{reason[:40]}...'"
            log.info(f"  ✓ Score {score}: reason generated")

        log.info("✅ PASSED: Reason generation correct")

    def test_8_quality_score_creation_without_client(self):
        """Unit Test 8: Quality score creation without Supabase client."""
        log.info("TEST 8: Quality Score Creation — Without client")

        scoring = self.QualityScoring(None)
        quality_score = scoring.score_outcome(
            outcome_id="OUT-20260610-143000",
            decision_id="DEC-REC-20260610-143000",
            outcome_status="Implemented",
            implementation_notes="Executed successfully",
            provider_name="Google",
            model_name="Gemini 2.5 Flash",
            provider_route="Primary"
        )

        assert quality_score is not None, "Score should be created"
        assert quality_score.effectiveness_score == 5.0, "Score should be 5.0"
        assert quality_score.provider_name == "Google"
        log.info(f"  ✓ Created score: {quality_score.id}")
        log.info("✅ PASSED: Quality score creation without client works")

    def test_9_quality_score_persistence(self):
        """Unit Test 9: Quality score persistence to Supabase."""
        log.info("TEST 9: Quality Score Persistence")

        client = MockSupabaseClient()
        scoring = self.QualityScoring(client)

        quality_score = scoring.score_outcome(
            outcome_id="OUT-20260610-143001",
            decision_id="DEC-REC-20260610-143001",
            outcome_status="Modified",
            implementation_notes="Modified with positive changes",
            provider_name="OpenRouter",
            model_name="Mistral"
        )

        assert quality_score is not None
        assert quality_score.effectiveness_score == 3.5, f"Expected 3.5, got {quality_score.effectiveness_score}"

        # Verify persisted
        persisted = client.table("quality_scores").data.get(quality_score.id)
        assert persisted is not None, f"Score not persisted: {quality_score.id}"
        assert persisted["effectiveness_score"] == 3.5
        log.info(f"  ✓ Persisted score: {quality_score.id}")
        log.info("✅ PASSED: Quality score persisted correctly")

    def test_10_provider_attribution(self):
        """Unit Test 10: Provider attribution capture."""
        log.info("TEST 10: Provider Attribution Capture")

        scoring = self.QualityScoring()
        score = scoring.score_outcome(
            outcome_id="OUT-20260610-143000",
            decision_id="DEC-REC-20260610-143000",
            outcome_status="Implemented",
            implementation_notes="Good execution",
            provider_name="Ollama",
            model_name="Qwen 3",
            provider_route="Fallback"
        )

        assert score.provider_name == "Ollama"
        assert score.model_name == "Qwen 3"
        assert score.provider_route == "Fallback"
        log.info(f"  ✓ Provider: {score.provider_name}")
        log.info(f"  ✓ Model: {score.model_name}")
        log.info(f"  ✓ Route: {score.provider_route}")
        log.info("✅ PASSED: Provider attribution captured")


# ============================================================================
# Integration Tests
# ============================================================================

class TestQualityScoringIntegration:
    """Integration tests for end-to-end quality scoring flow."""

    def setup_method(self):
        """Setup for each test."""
        log.info("\n" + "="*80)
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent / "slack-bot"))
            from lib.quality_scoring_service import QualityScoring
            self.QualityScoring = QualityScoring
        except Exception as e:
            log.error(f"Failed to import: {e}")
            raise

    def test_11_e2e_outcome_to_score(self):
        """Integration Test 11: End-to-end outcome → score flow."""
        log.info("TEST 11: Integration — E2E Outcome → Score")

        client = MockSupabaseClient()
        scoring = self.QualityScoring(client)

        # Score an outcome
        quality_score = scoring.score_outcome(
            outcome_id="OUT-20260610-143000",
            decision_id="DEC-REC-20260610-143000",
            outcome_status="Implemented",
            implementation_notes="Executed perfectly",
            provider_name="Google",
            model_name="Gemini 2.5 Flash",
            provider_route="Primary"
        )

        assert quality_score is not None
        assert quality_score.effectiveness_score == 5.0
        assert "executed as planned" in quality_score.scoring_reason.lower()

        # Verify persisted and queryable
        persisted = client.table("quality_scores").data.get(quality_score.id)
        assert persisted is not None
        log.info(f"  ✓ Outcome scored and persisted: {quality_score.id}")
        log.info("✅ PASSED: E2E outcome → score flow complete")

    def test_12_multiple_scores_per_provider(self):
        """Integration Test 12: Multiple scores accumulate by provider."""
        log.info("TEST 12: Integration — Multiple scores by provider")

        client = MockSupabaseClient()
        scoring = self.QualityScoring(client)

        provider_name = "Google"
        scores = []

        # Record multiple outcomes for same provider
        for i in range(3):
            score = scoring.score_outcome(
                outcome_id=f"OUT-20260610-14300{i}",
                decision_id=f"DEC-REC-20260610-14300{i}",
                outcome_status="Implemented" if i % 2 == 0 else "Modified",
                implementation_notes="Test outcome",
                provider_name=provider_name,
                model_name="Gemini"
            )
            if score:
                scores.append(score)

        assert len(scores) >= 2, f"Expected 2+ scores, got {len(scores)}"
        log.info(f"  ✓ Recorded {len(scores)} scores for {provider_name}")
        log.info("✅ PASSED: Multiple scores per provider supported")

    def test_13_provider_quality_analysis(self):
        """Integration Test 13: Provider quality analysis."""
        log.info("TEST 13: Integration — Provider Quality Analysis")

        client = MockSupabaseClient()
        scoring = self.QualityScoring(client)

        # Add mock provider quality data
        client._view_provider.data = {
            "Google": {
                "provider_name": "Google",
                "scored_decisions": 5,
                "avg_score": 4.4,
                "min_score": 4.0,
                "max_score": 5.0
            },
            "OpenRouter": {
                "provider_name": "OpenRouter",
                "scored_decisions": 3,
                "avg_score": 3.5,
                "min_score": 3.0,
                "max_score": 4.0
            }
        }

        # Query provider quality
        qualities = scoring.get_provider_quality()
        assert len(qualities) >= 1, f"Expected provider quality data, got {len(qualities)}"
        log.info(f"  ✓ Retrieved quality for {len(qualities)} providers")
        log.info("✅ PASSED: Provider quality analysis works")

    def test_14_model_quality_analysis(self):
        """Integration Test 14: Model quality analysis."""
        log.info("TEST 14: Integration — Model Quality Analysis")

        client = MockSupabaseClient()
        scoring = self.QualityScoring(client)

        # Add mock model quality data
        client._view_model.data = {
            "gemini": {
                "model_name": "Gemini 2.5 Flash",
                "provider_name": "Google",
                "scored_decisions": 5,
                "avg_score": 4.4,
                "min_score": 4.0,
                "max_score": 5.0
            }
        }

        # Query model quality
        qualities = scoring.get_model_quality()
        assert len(qualities) >= 1, f"Expected model quality data, got {len(qualities)}"
        log.info(f"  ✓ Retrieved quality for {len(qualities)} models")
        log.info("✅ PASSED: Model quality analysis works")

    def test_15_route_quality_analysis(self):
        """Integration Test 15: Routing strategy quality analysis."""
        log.info("TEST 15: Integration — Route Quality Analysis")

        client = MockSupabaseClient()
        scoring = self.QualityScoring(client)

        # Add mock routing quality data
        client._view_route.data = {
            "Primary": {
                "provider_route": "Primary",
                "decisions": 10,
                "avg_score": 4.3,
                "high_quality_count": 8,
                "low_quality_count": 1
            },
            "Fallback": {
                "provider_route": "Fallback",
                "decisions": 3,
                "avg_score": 2.5,
                "high_quality_count": 0,
                "low_quality_count": 2
            }
        }

        # Query route quality
        qualities = scoring.get_route_quality()
        assert len(qualities) >= 1, f"Expected route quality data, got {len(qualities)}"
        log.info(f"  ✓ Retrieved quality for {len(qualities)} routes")
        log.info("✅ PASSED: Route quality analysis works")


# ============================================================================
# Test Runner
# ============================================================================

def run_all_tests():
    """Run all B1C quality scoring tests."""
    log.info("\n" + "="*80)
    log.info("MSN-0060B PHASE B1C: QUALITY SCORING TEST SUITE")
    log.info("="*80)

    # Unit tests
    unit_tests = TestQualityScoringUnit()
    unit_test_methods = [
        unit_tests.test_1_score_id_generation,
        unit_tests.test_2_score_calculation_implemented,
        unit_tests.test_3_score_calculation_modified,
        unit_tests.test_4_score_calculation_deferred,
        unit_tests.test_5_score_calculation_rejected,
        unit_tests.test_6_score_calculation_unknown,
        unit_tests.test_7_reason_generation,
        unit_tests.test_8_quality_score_creation_without_client,
        unit_tests.test_9_quality_score_persistence,
        unit_tests.test_10_provider_attribution,
    ]

    # Integration tests
    integration_tests = TestQualityScoringIntegration()
    integration_test_methods = [
        integration_tests.test_11_e2e_outcome_to_score,
        integration_tests.test_12_multiple_scores_per_provider,
        integration_tests.test_13_provider_quality_analysis,
        integration_tests.test_14_model_quality_analysis,
        integration_tests.test_15_route_quality_analysis,
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
        log.info("\n🟢 ALL B1C TESTS PASSED")
        log.info("Phase B1C quality scoring ready for deployment")
    else:
        log.warning(f"\n🔴 {failed} TESTS FAILED")
        log.warning("Issues must be resolved before deployment")

    log.info("="*80 + "\n")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
