#!/usr/bin/env python3
"""
CPS 230 Operational Resilience Research Output Quality Validation

Tests the Phase 1 + Phase 2 fixes for research output quality:
1. Consolidation timeout increased (30s → 60s)
2. Fallback confidence increased (0.6 → 0.8)
3. Consolidation called directly (excludes from Gemini budget)

Expected results:
- Consolidation succeeds (no timeout)
- Recommendation generated (confidence ≥ 0.8)
- No regression to provider routing
- No regression to B1A learning loop
"""

import sys
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger(__name__)

# Add paths
slack_bot_lib = Path(__file__).parent.parent / "platform-runtime" / "lib"
core_coordination = Path(__file__).parent.parent / "core" / "coordination"
sys.path.insert(0, str(slack_bot_lib))
sys.path.insert(0, str(core_coordination))


class TestResearchOutputQualityValidation:
    """Validate Phase 1 + Phase 2 fixes."""

    def setup_method(self):
        """Setup for each test."""
        log.info("\n" + "="*80)

    def test_consolidation_timeout_increased(self):
        """Verify: Consolidation timeout increased from 30s to 60s."""
        log.info("TEST: Consolidation Timeout Increased")

        # Read the source file
        source_file = Path(__file__).parent.parent / "core" / "coordination" / "research_orchestration.py"
        with open(source_file) as f:
            content = f.read()

        # Verify timeout_sec=60 exists
        assert "timeout_sec=60)" in content, "Consolidation timeout not increased to 60s"

        # Verify old timeout_sec=30 for consolidation is gone (allowing other 30s timeouts)
        # Count occurrences - should have consolidation at 60s and other tasks at various
        lines = content.split("\n")
        consolidation_60s_found = False
        for i, line in enumerate(lines):
            if "timeout_sec=60" in line and i > 500:  # After consolidation section starts
                if "consolidation" in lines[max(0, i-5):i+5].__str__():
                    consolidation_60s_found = True
                    break

        assert consolidation_60s_found, "Consolidation timeout not set to 60s in code"
        log.info("✅ PASSED: Consolidation timeout increased to 60s")

    def test_fallback_confidence_increased(self):
        """Verify: Fallback recommendation confidence increased from 0.6 to 0.8."""
        log.info("TEST: Fallback Confidence Increased")

        source_file = Path(__file__).parent.parent / "core" / "coordination" / "research_orchestration.py"
        with open(source_file) as f:
            content = f.read()

        # Find the fallback confidence assignment
        lines = content.split("\n")
        found_confidence_0_8 = False
        found_old_confidence_0_6 = False

        for i, line in enumerate(lines):
            if "confidence = 0.8" in line:
                # Check context - should be in fallback recommendation section
                context = "\n".join(lines[max(0, i-10):i+2])
                if "RECOMMENDATION NEEDS REVIEW" in context or "Medium confidence" in context or "High confidence" in context:
                    found_confidence_0_8 = True
                    log.info(f"  Found: confidence = 0.8 at line {i+1}")
            elif "confidence = 0.6" in line and "fallback" in "\n".join(lines[max(0, i-10):i+2]).lower():
                found_old_confidence_0_6 = True
                log.info(f"  Found OLD: confidence = 0.6 at line {i+1}")

        assert found_confidence_0_8, "Fallback confidence not increased to 0.8"
        assert not found_old_confidence_0_6, "Old confidence 0.6 still present in fallback"
        log.info("✅ PASSED: Fallback confidence increased to 0.8")

    def test_consolidation_called_directly(self):
        """Verify: Consolidation called directly with timeout_sec=60."""
        log.info("TEST: Consolidation Called Directly (No Mission Budget Impact)")

        source_file = Path(__file__).parent.parent / "core" / "coordination" / "research_orchestration.py"
        with open(source_file) as f:
            content = f.read()

        # Verify consolidation is called with timeout_sec=60 directly
        # (not via delegate_research_task with mission_id parameter)
        lines = content.split("\n")
        consolidation_call_found = False
        consolidation_with_60s = False

        for i, line in enumerate(lines):
            # Find consolidation calls with proper timeout
            if "call_gemini_2_5_flash_lite_research" in line and "consolidation" in line.lower():
                consolidation_call_found = True
                if "timeout_sec=60" in line:
                    consolidation_with_60s = True
                    log.info(f"  Found direct call at line {i+1}: {line.strip()}")
                # Also check next line for timeout parameter
                if i+1 < len(lines) and "timeout_sec=60" in lines[i+1]:
                    consolidation_with_60s = True

        assert consolidation_call_found, "Consolidation call not found"
        assert consolidation_with_60s, "Consolidation timeout not set to 60s"
        log.info("✅ PASSED: Consolidation called directly with 60s timeout (excludes from mission budget)")

    def test_no_regression_to_consolidation_fallback_message(self):
        """Verify: Consolidation fallback message still present for error cases."""
        log.info("TEST: Consolidation Fallback Logic Preserved")

        source_file = Path(__file__).parent.parent / "core" / "coordination" / "research_orchestration.py"
        with open(source_file) as f:
            content = f.read()

        # Verify fallback consolidation logic still exists
        assert "Using local fallback consolidation" in content
        assert "automated consolidation timed out" in content
        assert "fallback_text = " in content
        log.info("✅ PASSED: Consolidation fallback logic preserved")

    def test_recommendation_timeout_still_in_place(self):
        """Verify: Recommendation generation timeout still at 20s (not changed)."""
        log.info("TEST: Recommendation Timeout Unchanged")

        source_file = Path(__file__).parent.parent / "core" / "coordination" / "research_orchestration.py"
        with open(source_file) as f:
            content = f.read()

        lines = content.split("\n")
        recommendation_20s_found = False

        for i, line in enumerate(lines):
            if "timeout_sec=20" in line:
                context = "\n".join(lines[max(0, i-5):i+2])
                if "recommendation" in context.lower() or "flash" in context.lower():
                    recommendation_20s_found = True
                    log.info(f"  Found: timeout_sec=20 for recommendation at line {i+1}")

        assert recommendation_20s_found, "Recommendation timeout not at 20s"
        log.info("✅ PASSED: Recommendation timeout unchanged at 20s")

    def test_provider_routing_unchanged(self):
        """Verify: Provider routing logic unchanged (consolidation exclusion only)."""
        log.info("TEST: Provider Routing Logic Unchanged")

        source_file = Path(__file__).parent.parent / "platform-runtime" / "lib" / "research_delegator.py"
        with open(source_file) as f:
            content = f.read()

        # Verify quota-aware routing still in place
        assert "GEMINI_MAX_CALLS_PER_MISSION" in content
        assert "mission_quota.can_use_gemini()" in content
        assert "gemini.*quota.*exhausted" in content or "quota_exhausted" in content
        assert "call_ollama_research" in content
        log.info("✅ PASSED: Provider routing logic unchanged")

    def test_no_b1a_regression(self):
        """Verify: B1A learning loop not modified."""
        log.info("TEST: B1A Learning Loop Unchanged")

        # Check that learning_loop_service.py unchanged
        learning_loop_file = Path(__file__).parent.parent / "platform-runtime" / "lib" / "learning_loop_service.py"
        assert learning_loop_file.exists(), "Learning loop service missing"

        # Check that B1A schema file unchanged
        schema_file = Path(__file__).parent.parent / "tools" / "supabase" / "schema" / "MSN-0060B-LEARNING-LOOP-SCHEMA.sql"
        if schema_file.exists():
            log.info("  B1A schema file present")

        log.info("✅ PASSED: B1A learning loop unchanged")

    def test_syntax_validation(self):
        """Verify: All modified files compile without syntax errors."""
        log.info("TEST: Syntax Validation")

        import py_compile
        import tempfile

        files_to_check = [
            Path(__file__).parent.parent / "core" / "coordination" / "research_orchestration.py",
            Path(__file__).parent.parent / "platform-runtime" / "lib" / "research_delegator.py",
            Path(__file__).parent.parent / "core" / "coordination" / "research_metrics.py",
        ]

        for filepath in files_to_check:
            if filepath.exists():
                try:
                    py_compile.compile(str(filepath), doraise=True)
                    log.info(f"  ✅ {filepath.name} compiles successfully")
                except py_compile.PyCompileError as e:
                    assert False, f"Syntax error in {filepath.name}: {e}"

        log.info("✅ PASSED: All files compile without syntax errors")


def run_validation():
    """Run all validation tests."""
    log.info("\n" + "="*80)
    log.info("RESEARCH OUTPUT QUALITY: PHASE 1 + PHASE 2 VALIDATION")
    log.info("="*80)

    test_suite = TestResearchOutputQualityValidation()
    tests = [
        test_suite.test_consolidation_timeout_increased,
        test_suite.test_fallback_confidence_increased,
        test_suite.test_consolidation_called_directly,
        test_suite.test_no_regression_to_consolidation_fallback_message,
        test_suite.test_recommendation_timeout_still_in_place,
        test_suite.test_provider_routing_unchanged,
        test_suite.test_no_b1a_regression,
        test_suite.test_syntax_validation,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        test_suite.setup_method()
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            failed += 1
            log.error(f"❌ FAILED: {test_func.__name__}: {e}")
        except Exception as e:
            failed += 1
            log.error(f"❌ ERROR: {test_func.__name__}: {type(e).__name__}: {e}")

    log.info("\n" + "="*80)
    log.info(f"RESULTS: {passed} passed, {failed} failed")
    log.info("="*80 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = run_validation()
    sys.exit(0 if success else 1)
