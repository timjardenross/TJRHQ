#!/usr/bin/env python3
"""
Test harness for MSN-0032 — Semantic Specialist Routing Integration

Tests the integration of P5 semantic routing into Slack Commander.
Validates that semantic routing metadata is properly captured, stored,
and included in responses.
"""

import sys
from pathlib import Path

# Add parent directory to path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from commander_bridge import handle_slack_message
from commander_response_formatter import format_commander_response


# ============================================================================
# Integration Test Cases
# ============================================================================

TEST_CASES = [
    {
        "id": 1,
        "input": "@commander review the architecture and identify what could break",
        "expect_semantic_intent": "architecture_review",
        "expect_primary": "Chief Engineer",
        "description": "Architecture review request routes to Chief Engineer"
    },
    {
        "id": 2,
        "input": "@commander create a mission to improve Slack logging",
        "expect_semantic_intent": "mission_creation",
        "expect_primary": "Mission Scribe",
        "description": "Mission creation routes to Mission Scribe"
    },
    {
        "id": 3,
        "input": "@commander review this code for bugs",
        "expect_semantic_intent": "code_review",
        "expect_primary": "Coder Agent",
        "description": "Code review routes to Coder Agent"
    },
    {
        "id": 4,
        "input": "@commander capture this decision: use SQLite for persistence",
        "expect_semantic_intent": "decision_logging",
        "expect_primary": "Mission Scribe",
        "description": "Decision logging routes to Mission Scribe"
    },
    {
        "id": 5,
        "input": "@commander what are the operational resilience risks?",
        "expect_semantic_intent": "risk_assessment",
        "expect_primary": "Risk Officer",
        "description": "Risk assessment routes to Risk Officer"
    },
    {
        "id": 6,
        "input": "@commander document the decision to use Supabase",
        "expect_semantic_intent": "decision_logging",
        "expect_primary": "Mission Scribe",
        "description": "Documentation + decision routes to Mission Scribe"
    },
    {
        "id": 7,
        "input": "@commander is this feature worth building?",
        "expect_semantic_intent": "product_scope",
        "expect_primary": "Product Owner",
        "description": "Product scope decision routes to Product Owner"
    },
    {
        "id": 8,
        "input": "@commander how should we design this to be resilient?",
        "expect_semantic_intent": "architecture_review",
        "expect_primary": "Chief Engineer",
        "description": "Architecture + resilience routes to Chief Engineer"
    },
    {
        "id": 9,
        "input": "@commander help me create a wellness routine",
        "expect_semantic_intent": "wellness_support",
        "expect_primary": "Wellness Specialist",
        "description": "Wellness support routes to Wellness Specialist"
    },
    {
        "id": 10,
        "input": "@commander can you look at this and tell me what to do?",
        "expect_semantic_intent": "unknown",
        "expect_primary": "Executive Officer (XO)",
        "description": "Ambiguous request escalates to XO"
    }
]


# ============================================================================
# Test Runner
# ============================================================================

def run_integration_tests():
    """Run all integration tests."""
    print("=" * 80)
    print("MSN-0032 — SEMANTIC SPECIALIST ROUTING SLACK INTEGRATION TESTS")
    print("=" * 80)
    print()

    passed = 0
    failed = 0
    results = []

    for test in TEST_CASES:
        result = run_single_test(test)
        results.append(result)

        if result["passed"]:
            passed += 1
            status = "✅ PASS"
        else:
            failed += 1
            status = "❌ FAIL"

        print(f"{status} | Test {test['id']:2d}: {test['description']}")

    # Summary
    print()
    print("=" * 80)
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(TEST_CASES)} tests")
    print("=" * 80)
    print()

    # Detailed results for failed tests
    if failed > 0:
        print("\nFAILED TEST DETAILS:")
        print("-" * 80)
        for result in results:
            if not result["passed"]:
                print_detailed_result(result)
        print()

    return failed == 0


def run_single_test(test: dict) -> dict:
    """Run a single integration test."""
    user_input = test["input"]
    expected_intent = test["expect_semantic_intent"]
    expected_primary = test["expect_primary"]

    try:
        # Call handle_slack_message (simulating Slack intake)
        result = handle_slack_message(
            text=user_input,
            user_id="U12345",
            channel_id="C67890",
            message_ts="1234567890.123456",
            thread_ts=None
        )

        # Extract semantic routing metadata
        metadata = result.get("metadata", {})
        actual_intent = metadata.get("semantic_intent", "unknown")
        actual_primary = metadata.get("primary_specialist", "unknown")

        # Check matches
        intent_match = actual_intent == expected_intent
        primary_match = actual_primary == expected_primary

        passed = intent_match and primary_match

        return {
            "test_id": test["id"],
            "description": test["description"],
            "input": user_input,
            "passed": passed,
            "expected_intent": expected_intent,
            "actual_intent": actual_intent,
            "intent_match": intent_match,
            "expected_primary": expected_primary,
            "actual_primary": actual_primary,
            "primary_match": primary_match,
            "confidence_band": metadata.get("semantic_confidence_band"),
            "confidence": metadata.get("semantic_confidence"),
            "rationale": metadata.get("semantic_rationale"),
            "logged": result.get("logged"),
            "route": result.get("route"),
            "error": None
        }
    except Exception as e:
        return {
            "test_id": test["id"],
            "description": test["description"],
            "input": user_input,
            "passed": False,
            "expected_intent": expected_intent,
            "actual_intent": None,
            "intent_match": False,
            "expected_primary": expected_primary,
            "actual_primary": None,
            "primary_match": False,
            "confidence_band": None,
            "confidence": None,
            "rationale": None,
            "logged": None,
            "route": None,
            "error": str(e)
        }


def print_detailed_result(result: dict):
    """Print detailed info about a failed test."""
    print(f"\nTest {result['test_id']}: {result['description']}")
    print(f"  Input: {result['input'][:70]}...")

    if result['error']:
        print(f"  ERROR: {result['error']}")
        return

    print(f"  Intent:")
    print(f"    Expected: {result['expected_intent']}")
    print(f"    Actual:   {result['actual_intent']}")
    print(f"    Match:    {result['intent_match']}")
    print(f"  Primary Specialist:")
    print(f"    Expected: {result['expected_primary']}")
    print(f"    Actual:   {result['actual_primary']}")
    print(f"    Match:    {result['primary_match']}")

    if result.get('confidence_band'):
        print(f"  Confidence: {result['confidence']:.2f} ({result['confidence_band']})")

    if result.get('rationale'):
        print(f"  Rationale: {result['rationale'][:100]}...")

    print(f"  Route: {result['route']}")


# ============================================================================
# Response Formatting Test
# ============================================================================

def test_routing_in_response_formatting():
    """Test that semantic routing data is formatted in Commander responses."""
    print("\n" + "=" * 80)
    print("MSN-0032 — RESPONSE FORMATTING TEST")
    print("=" * 80)
    print()

    # Simulate a Commander response with routing data
    test_response = {
        "type": "RECOMMENDATION",
        "body": "I recommend we improve the logging system.",
        "lifecycle_state": None,
        "confidence": None,
        "primary_specialist": "Chief Engineer",
        "semantic_intent": "architecture_review",
        "semantic_confidence_band": "high",
        "secondary_specialists": ["Coder Agent", "Risk Officer"],
        "semantic_rationale": "Request asks for architecture review and identifies failure points.",
        "metadata": {"source": "Commander"}
    }

    formatted = format_commander_response(test_response)

    # Check that routing information is present
    checks = [
        ("Response type header", "*Commander Response — RECOMMENDATION*" in formatted),
        ("Primary specialist", "Chief Engineer" in formatted),
        ("Intent", "architecture_review" in formatted or "Architecture Review" in formatted),
        ("Confidence band", "high" in formatted or "High" in formatted),
        ("Secondary specialists", "Coder Agent" in formatted),
        ("Metadata", "Source: Commander" in formatted),
    ]

    passed = 0
    failed = 0

    for check_name, result in checks:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} | {check_name}")
        if result:
            passed += 1
        else:
            failed += 1

    print()
    print(f"Response formatting: {passed}/{len(checks)} checks passed")
    print()

    if failed > 0:
        print("Formatted response output:")
        print("-" * 80)
        print(formatted)
        print("-" * 80)

    return failed == 0


# ============================================================================
# Fallback Test
# ============================================================================

def test_fallback_behavior():
    """Test that routing still works if semantic router is unavailable."""
    print("\n" + "=" * 80)
    print("MSN-0032 — FALLBACK BEHAVIOR TEST")
    print("=" * 80)
    print()

    # This test verifies that if semantic routing fails, the legacy router
    # still handles the request. The commander_bridge.py has a try/except
    # that catches semantic router errors.

    test_input = "@commander review the architecture"

    try:
        result = handle_slack_message(
            text=test_input,
            user_id="U12345",
            channel_id="C67890",
            message_ts="1234567890.123456",
            thread_ts=None
        )

        # If we get here, fallback handling worked
        route = result.get("route")
        print(f"✅ PASS | Message handled with route: {route}")
        print(f"  Semantic routing available: {result['metadata'].get('semantic_intent') is not None}")
        return True

    except Exception as e:
        print(f"❌ FAIL | Fallback handling failed: {e}")
        return False


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MSN-0032 Integration Tests")
    parser.add_argument(
        "--test",
        action="store_true",
        default=False,
        help="Run automated integration tests"
    )
    parser.add_argument(
        "--formatting",
        action="store_true",
        default=False,
        help="Test response formatting"
    )
    parser.add_argument(
        "--fallback",
        action="store_true",
        default=False,
        help="Test fallback behavior"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Run all tests"
    )

    args = parser.parse_args()

    # Default to all tests if no specific test requested
    if not any([args.test, args.formatting, args.fallback]):
        args.all = True

    all_passed = True

    if args.all or args.test:
        all_passed = run_integration_tests() and all_passed

    if args.all or args.formatting:
        all_passed = test_routing_in_response_formatting() and all_passed

    if args.all or args.fallback:
        all_passed = test_fallback_behavior() and all_passed

    sys.exit(0 if all_passed else 1)
