#!/usr/bin/env python3
"""MSN-[GEMINI-QUOTA-AWARE-ROUTING]: Validation Tests

Tests quota-aware routing behavior:
1. Per-mission Gemini call budgeting (max 1 call/mission)
2. Daily quota exhaustion detection (no repeated retries)
3. Fallback to Ollama when Gemini quota exhausted
4. Provider health tracking with quota-aware skipping
5. Detailed logging of provider selection and fallback usage

Tests use mocking to simulate:
- Gemini 429 daily quota exhausted errors
- Ollama successful fallback responses
- Provider circuit breaker skipping
"""

import logging
import sys
from pathlib import Path
from unittest.mock import patch

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format="[%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger(__name__)

# Add platform-runtime/lib to path
slack_bot_lib = Path(__file__).parent.parent / "platform-runtime" / "lib"
sys.path.insert(0, str(slack_bot_lib))

from research_delegator import (
    ProviderHealth,
    ResearchOutcome,
    delegate_research_task,
    get_mission_gemini_quota,
)


class TestGeminiQuotaAware:
    """Test suite for quota-aware routing."""

    def setup_method(self):
        """Setup for each test."""
        # Reset mission quotas
        from research_delegator import _mission_gemini_quotas
        _mission_gemini_quotas.clear()

    def test_mission_quota_tracking(self):
        """Test: Per-mission Gemini call budgeting works correctly."""
        log.info("\n=== TEST: Mission Quota Tracking ===")

        mission_id = "MSN-TEST-001"
        quota = get_mission_gemini_quota(mission_id)

        # Initial state
        assert quota.gemini_calls_made == 0
        assert quota.can_use_gemini() == True
        log.info("✓ Initial quota: calls=0, can_use=True")

        # Record call
        quota.record_gemini_call()
        assert quota.gemini_calls_made == 1
        assert quota.can_use_gemini() == False  # Max 1 per mission
        log.info("✓ After 1 call: calls=1, can_use=False (budget exhausted)")

    def test_daily_quota_exhaustion_detection(self):
        """Test: Daily quota exhaustion returns immediately (no retry).

        Provider chain is Mistral -> Ollama -> Gemini (M-20260612-MISTRAL-AGENT-
        RESEARCH-WORKFLOW put Mistral first and pushed Gemini to last), so for
        Gemini to be attempted at all here, Mistral and Ollama both have to
        fail first — Gemini can no longer "fall back to Ollama" since Ollama
        is earlier in the chain, not later. The thing this test actually
        verifies (quota_exhausted causes exactly one call, no retry) still
        holds regardless of chain position.
        """
        log.info("\n=== TEST: Daily Quota Exhaustion Detection ===")

        with patch("research_delegator.call_mistral_research") as mock_mistral:
            mock_mistral.return_value = ResearchOutcome(status="failed", provider="mistral_agent", error_message="not configured")

            with patch("research_delegator.call_ollama_research") as mock_ollama:
                mock_ollama.return_value = ResearchOutcome(status="failed", provider="ollama", error_message="model not available")

                with patch("research_delegator.call_gemini_2_5_flash_lite_research") as mock_gemini:
                    mock_gemini.return_value = ResearchOutcome(
                        status="quota_exhausted",
                        provider="gemini-3.5-flash-lite",
                        error_message="Gemini daily quota exhausted (retry_delay=86400s). No fallback retry.",
                        fallback_reason="gemini_quota_exhausted"
                    )

                    result = delegate_research_task(
                        task_description="Test research task",
                        mission_id="MSN-TEST-002"
                    )

                    # Verify: Gemini was attempted (returned quota_exhausted)
                    assert "gemini-3.5-flash-lite" in result.provider_attempted
                    log.info("✓ Gemini was attempted")

                    # Verify: Gemini not retried (quota_exhausted → no retry)
                    assert mock_gemini.call_count == 1  # Only called once, no retry
                    log.info("✓ Gemini not retried (quota_exhausted detected)")

                    # Verify: no provider left after Gemini (last in chain) also
                    # exhausted its quota — overall delegation fails cleanly.
                    assert result.status == "error"
                    assert result.provider == "none"
                    log.info("✓ All providers exhausted, no crash, clean error result")

    def test_mission_budget_prevents_second_gemini_call(self):
        """Test: Per-mission budget prevents 2nd Gemini call within same mission."""
        log.info("\n=== TEST: Mission Budget Prevents 2nd Gemini Call ===")

        mission_id = "MSN-TEST-003"
        # Deliberately a fresh ProviderHealth per sub-test below, not shared:
        # the per-mission Gemini quota this test verifies is keyed by
        # mission_id in a module-level dict (_mission_gemini_quotas),
        # independent of any ProviderHealth instance, so it persists across
        # both calls regardless. ProviderHealth's circuit breaker has no
        # concept of scope beyond "unavailable forever within this
        # instance" — sharing one across sub-tests would mean Ollama
        # failing in sub-test 1 (needed so Gemini gets reached at all,
        # since chain order is Mistral -> Ollama -> Gemini) permanently
        # excludes Ollama from sub-test 2 too, which isn't what either
        # sub-test is trying to verify.

        # First task: Mistral+Ollama fail (chain order: Mistral -> Ollama ->
        # Gemini), Gemini succeeds as last resort.
        with patch("research_delegator.call_mistral_research") as mock_mistral, \
             patch("research_delegator.call_ollama_research") as mock_ollama, \
             patch("research_delegator.call_gemini_2_5_flash_lite_research") as mock_gemini:
            mock_mistral.return_value = ResearchOutcome(status="failed", provider="mistral_agent", error_message="not configured")
            mock_ollama.return_value = ResearchOutcome(status="failed", provider="ollama", error_message="model not available")
            mock_gemini.return_value = ResearchOutcome(
                status="success",
                provider="gemini-3.5-flash-lite",
                findings="First task findings"
            )

            result1 = delegate_research_task(
                task_description="First task",
                mission_id=mission_id,
                provider_health=ProviderHealth()
            )

            assert result1.status == "success"
            assert result1.provider == "gemini-3.5-flash-lite"
            log.info("✓ First task: Gemini succeeded")

            # Verify: Mission quota now exhausted
            quota = get_mission_gemini_quota(mission_id)
            assert quota.gemini_calls_made == 1
            assert quota.can_use_gemini() == False
            log.info("✓ Mission quota exhausted: calls=1, can_use=False")

        # Second task: Mistral fails again, Ollama succeeds this time. Gemini
        # must be skipped (quota exhausted) before it's ever reached, so
        # Ollama becomes the provider actually used.
        with patch("research_delegator.call_mistral_research") as mock_mistral, \
             patch("research_delegator.call_gemini_2_5_flash_lite_research") as mock_gemini:
            mock_mistral.return_value = ResearchOutcome(status="failed", provider="mistral_agent", error_message="not configured")
            mock_gemini.return_value = ResearchOutcome(
                status="error",
                provider="gemini-3.5-flash-lite",
                error_message="Should not be called"
            )

            with patch("research_delegator.call_ollama_research") as mock_ollama:
                mock_ollama.return_value = ResearchOutcome(
                    status="success",
                    provider="ollama",
                    findings="Second task findings (Ollama)"
                )

                result2 = delegate_research_task(
                    task_description="Second task",
                    mission_id=mission_id,
                    provider_health=ProviderHealth()
                )

                # Verify: Gemini skipped (not in attempted list)
                assert "gemini-3.5-flash-lite" not in result2.provider_attempted
                log.info("✓ Gemini skipped (not in attempted list)")

                # Verify: Ollama used instead
                assert result2.provider == "ollama"
                assert result2.status == "success"
                log.info("✓ Ollama used for second task")

                # Verify: Gemini never called for task 2 (quota-skipped)
                assert mock_gemini.call_count == 0
                log.info("✓ Gemini not called for second task")

    def test_circuit_breaker_with_quota_aware_skipping(self):
        """Test: Circuit breaker + quota-aware skipping prevents cascading failures."""
        log.info("\n=== TEST: Circuit Breaker + Quota-Aware Skipping ===")

        mission_id = "MSN-TEST-004"
        provider_health = ProviderHealth()
        # Chain order is Mistral -> Ollama -> Gemini, so for Gemini to be
        # reached at all, both earlier providers must be unavailable.
        # Pre-seeding them as already-unavailable (a real scenario: both
        # already failed earlier in this mission, a prior task hit them) is
        # cleaner than mocking them to fail here — it exercises the same
        # circuit-breaker skip logic without a fragile chained failure mock,
        # and avoids needing to mock call_mistral_research at all (never
        # reached).
        provider_health.mark_unavailable("mistral_agent", "test_setup")
        provider_health.mark_unavailable("ollama", "test_setup")

        # Task 1: Gemini hits daily quota
        with patch("research_delegator.call_gemini_2_5_flash_lite_research") as mock_gemini:
            mock_gemini.return_value = ResearchOutcome(
                status="quota_exhausted",
                provider="gemini-3.5-flash-lite",
                error_message="Gemini daily quota exhausted",
                fallback_reason="gemini_quota_exhausted"
            )

            result1 = delegate_research_task(
                task_description="Task 1",
                mission_id=mission_id,
                provider_health=provider_health
            )

            # Nothing left after Gemini (last in chain) also fails.
            assert result1.status == "error"
            assert result1.provider == "none"
            # Verify Gemini was marked unavailable
            assert not provider_health.is_available("gemini-3.5-flash-lite")
            log.info("✓ Task 1: Gemini quota exhausted, marked unavailable")

        # Ollama "recovers" between tasks (a real prior failure clearing) —
        # this test only cares about Gemini's circuit-breaker persistence,
        # not Ollama's.
        provider_health.mark_available("ollama")

        # Task 2: Gemini should be skipped (marked unavailable by circuit breaker)
        with patch("research_delegator.call_gemini_2_5_flash_lite_research") as mock_gemini:
            # Should not be called at all
            mock_gemini.side_effect = Exception("Should not be called!")

            with patch("research_delegator.call_ollama_research") as mock_ollama:
                mock_ollama.return_value = ResearchOutcome(
                    status="success",
                    provider="ollama",
                    findings="Task 2 findings (Ollama)"
                )

                result2 = delegate_research_task(
                    task_description="Task 2",
                    mission_id=mission_id,
                    provider_health=provider_health
                )

                # Verify: Gemini was skipped (not called)
                assert mock_gemini.call_count == 0
                log.info("✓ Task 2: Gemini skipped by circuit breaker (call_count=0)")

                # Verify: Ollama used
                assert result2.provider == "ollama"
                log.info("✓ Task 2: Ollama fallback successful")

    def test_detailed_logging_of_provider_selection(self):
        """Test: Detailed logging shows provider selection, skipping, and fallback."""
        log.info("\n=== TEST: Detailed Logging of Provider Selection ===")

        mission_id = "MSN-TEST-005"

        with patch("research_delegator.call_gemini_2_5_flash_lite_research") as mock_gemini:
            mock_gemini.return_value = ResearchOutcome(
                status="quota_exhausted",
                provider="gemini-3.5-flash-lite",
                error_message="Gemini quota exhausted",
                fallback_reason="gemini_quota_exhausted"
            )

            with patch("research_delegator.call_ollama_research") as mock_ollama:
                mock_ollama.return_value = ResearchOutcome(
                    status="success",
                    provider="ollama",
                    findings="Ollama findings"
                )

                # Capture logging output
                result = delegate_research_task(
                    task_description="Test with detailed logging",
                    mission_id=mission_id
                )

                # Verify: Result contains telemetry
                assert hasattr(result, "provider_attempted")
                assert hasattr(result, "provider_skipped")
                assert hasattr(result, "fallback_reason")
                log.info(f"✓ Result has telemetry: attempted={result.provider_attempted}, skipped={result.provider_skipped}, reason={result.fallback_reason}")

    def test_no_repeated_retries_on_daily_quota(self):
        """Test: Daily quota exhaustion causes NO repeated retries."""
        log.info("\n=== TEST: No Repeated Retries on Daily Quota ===")

        call_count = {"gemini": 0}

        def mock_gemini_with_quota(*args, **kwargs):
            call_count["gemini"] += 1
            return ResearchOutcome(
                status="quota_exhausted",
                provider="gemini-3.5-flash-lite",
                error_message="Daily quota exhausted"
            )

        with (
            patch("research_delegator.call_mistral_research") as mock_mistral,
            patch("research_delegator.call_ollama_research") as mock_ollama,
            patch("research_delegator.call_gemini_2_5_flash_lite_research", side_effect=mock_gemini_with_quota),
        ):
            # Chain order is Mistral -> Ollama -> Gemini; both earlier
            # providers must fail for Gemini (last) to be reached at all.
            mock_mistral.return_value = ResearchOutcome(status="failed", provider="mistral_agent", error_message="not configured")
            mock_ollama.return_value = ResearchOutcome(status="failed", provider="ollama", error_message="model not available")

            result = delegate_research_task(task_description="Test no retries")

            # Verify: Gemini called exactly once (no retries)
            assert call_count["gemini"] == 1
            log.info("✓ Gemini called exactly 1 time (no retries on daily quota)")

            # Verify: nothing left after Gemini also fails — clean error.
            assert result.status == "error"
            assert result.provider == "none"
            log.info("✓ All providers exhausted, no crash, clean error result")


def run_tests():
    """Run all tests."""
    log.info("\n" + "="*80)
    log.info("GEMINI QUOTA-AWARE ROUTING VALIDATION TESTS")
    log.info("="*80)

    test_suite = TestGeminiQuotaAware()
    tests = [
        test_suite.test_mission_quota_tracking,
        test_suite.test_daily_quota_exhaustion_detection,
        test_suite.test_mission_budget_prevents_second_gemini_call,
        test_suite.test_circuit_breaker_with_quota_aware_skipping,
        test_suite.test_detailed_logging_of_provider_selection,
        test_suite.test_no_repeated_retries_on_daily_quota,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        test_suite.setup_method()
        try:
            test_func()
            passed += 1
            log.info(f"✅ PASSED: {test_func.__name__}")
        except AssertionError as e:
            failed += 1
            log.error(f"❌ FAILED: {test_func.__name__}: {e}")
        except Exception as e:  # noqa: BLE001 - test-runner harness: must catch any failure from a test function to tally it and continue
            failed += 1
            log.error(f"❌ ERROR: {test_func.__name__}: {e}")

    log.info("\n" + "="*80)
    log.info(f"RESULTS: {passed} passed, {failed} failed")
    log.info("="*80)

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
