#!/usr/bin/env python3
"""
Test harness for P5 — Semantic Specialist Routing

Run: python3 test_semantic_routing.py

Tests the semantic routing engine with 10+ test cases covering all intent categories.
"""

from semantic_router import (
    route_request_semantic,
    classify_intent,
    Intent,
    ConfidenceBand,
)
import json


# ============================================================================
# Test Cases
# ============================================================================

TEST_CASES = [
    {
        "id": 1,
        "input": "Review the architecture and identify what could break first.",
        "expected_intent": Intent.ARCHITECTURE_REVIEW,
        "expected_primary": "Chief Engineer",
        "description": "Architecture review request"
    },
    {
        "id": 2,
        "input": "Is this feature actually worth building for Captain TJR?",
        "expected_intent": Intent.PRODUCT_SCOPE,
        "expected_primary": "Product Owner",
        "description": "Product scope decision"
    },
    {
        "id": 3,
        "input": "Can you look at this and tell me what to do?",
        "expected_intent": Intent.UNKNOWN,
        "expected_primary": "Executive Officer (XO)",
        "description": "Ambiguous request - should escalate to XO"
    },
    {
        "id": 4,
        "input": "Create a mission to improve Slack logging and monitoring capabilities.",
        "expected_intent": Intent.MISSION_CREATION,
        "expected_primary": "Mission Scribe",
        "description": "Mission creation request"
    },
    {
        "id": 5,
        "input": "Draft a GitHub issue for handling command failure scenarios.",
        "expected_intent": Intent.CODE_REVIEW,
        "expected_primary": "Coder Agent",
        "description": "Code issue creation"
    },
    {
        "id": 6,
        "input": "Capture this decision: use Dashy as command centre dashboard.",
        "expected_intent": Intent.DECISION_LOGGING,
        "expected_primary": "Mission Scribe",
        "description": "Decision logging"
    },
    {
        "id": 7,
        "input": "Summarise this document and classify it in our knowledge base.",
        "expected_intent": Intent.KNOWLEDGE_MANAGEMENT,
        "expected_primary": "Knowledge Officer",
        "description": "Knowledge management"
    },
    {
        "id": 8,
        "input": "Review this code for bugs and potential issues.",
        "expected_intent": Intent.CODE_REVIEW,
        "expected_primary": "Coder Agent",
        "description": "Code review"
    },
    {
        "id": 9,
        "input": "What operational resilience risks does this architecture create?",
        "expected_intent": Intent.RISK_ASSESSMENT,
        "expected_primary": "Risk Officer",
        "description": "Risk and resilience assessment"
    },
    {
        "id": 10,
        "input": "Help me create a wellness routine that works with my chronic pain.",
        "expected_intent": Intent.WELLNESS_SUPPORT,
        "expected_primary": "Wellness Specialist",
        "description": "Wellness support"
    },
    {
        "id": 11,
        "input": "How should we design this system to be resilient to failures?",
        "expected_intent": Intent.ARCHITECTURE_REVIEW,
        "expected_primary": "Chief Engineer",
        "description": "Architecture and resilience design"
    },
    {
        "id": 12,
        "input": "Document the decision to use Supabase as our primary database.",
        "expected_intent": Intent.DECISION_LOGGING,
        "expected_primary": "Mission Scribe",
        "description": "Architectural decision logging"
    }
]


# ============================================================================
# Test Runner
# ============================================================================

def run_tests():
    """Run all test cases and report results."""
    print("=" * 80)
    print("P5 — SEMANTIC SPECIALIST ROUTING TEST SUITE")
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
    """Run a single test case."""
    user_input = test["input"]
    expected_intent = test["expected_intent"]
    expected_primary = test["expected_primary"]

    # Run routing
    routing = route_request_semantic(user_input)

    # Check intent (if not UNKNOWN, we check it)
    intent_match = (routing.intent == expected_intent)

    # Check primary specialist
    primary_match = (routing.primary_specialist == expected_primary)

    # Determine pass/fail
    passed = intent_match and primary_match

    return {
        "test_id": test["id"],
        "description": test["description"],
        "input": user_input,
        "passed": passed,
        "expected_intent": expected_intent,
        "actual_intent": routing.intent,
        "intent_match": intent_match,
        "expected_primary": expected_primary,
        "actual_primary": routing.primary_specialist,
        "primary_match": primary_match,
        "confidence": routing.confidence,
        "confidence_band": routing.confidence_band,
        "rationale": routing.rationale,
        "signals_matched": routing.intent_signals_matched
    }


def print_detailed_result(result: dict):
    """Print detailed info about a failed test."""
    print(f"\nTest {result['test_id']}: {result['description']}")
    print(f"  Input: {result['input'][:60]}...")
    print(f"  Intent:")
    print(f"    Expected: {result['expected_intent'].value}")
    print(f"    Actual:   {result['actual_intent'].value}")
    print(f"    Match:    {result['intent_match']}")
    print(f"  Primary Specialist:")
    print(f"    Expected: {result['expected_primary']}")
    print(f"    Actual:   {result['actual_primary']}")
    print(f"    Match:    {result['primary_match']}")
    print(f"  Confidence: {result['confidence']:.2f} ({result['confidence_band'].value})")
    print(f"  Signals:  {', '.join(result['signals_matched'][:3]) if result['signals_matched'] else '(none)'}")
    print(f"  Rationale: {result['rationale']}")


# ============================================================================
# Interactive Mode
# ============================================================================

def interactive_mode():
    """Run in interactive mode - accept user input."""
    print("=" * 80)
    print("P5 — SEMANTIC SPECIALIST ROUTING - INTERACTIVE MODE")
    print("=" * 80)
    print("\nEnter requests to route them semantically.")
    print("Type 'quit' to exit, 'test' to run test suite.\n")

    while True:
        try:
            user_input = input("Request > ").strip()

            if not user_input:
                continue

            if user_input.lower() == "quit":
                print("Exiting...")
                break

            if user_input.lower() == "test":
                success = run_tests()
                continue

            # Route the request
            routing = route_request_semantic(user_input)

            print_routing_result(routing)
            print()

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")
            print()


def print_routing_result(routing):
    """Pretty-print a routing result."""
    print()
    print("-" * 80)
    print("ROUTING DECISION:")
    print(f"  Primary Specialist:      {routing.primary_specialist}")
    print(f"  Secondary Specialists:   {', '.join(routing.secondary_specialists) if routing.secondary_specialists else '(none)'}")
    print(f"  Intent:                  {routing.intent.value.replace('_', ' ').title()}")
    print(f"  Confidence:              {routing.confidence:.2f} ({routing.confidence_band.value})")
    print(f"  Escalate to XO:          {'Yes' if routing.escalate_to_xo else 'No'}")
    print(f"  Rationale:               {routing.rationale}")

    signals_str = ', '.join(f"'{s}'" for s in routing.intent_signals_matched[:5]) if routing.intent_signals_matched else '(none)'
    print(f"  Signals Matched:         {signals_str}")
    print("-" * 80)


# ============================================================================
# JSON Output Mode
# ============================================================================

def json_output_mode(user_input: str):
    """Output routing decision as JSON."""
    routing = route_request_semantic(user_input)
    result = routing.to_dict()
    print(json.dumps(result, indent=2))


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "--test":
            success = run_tests()
            sys.exit(0 if success else 1)
        elif sys.argv[1] == "--json":
            if len(sys.argv) > 2:
                user_input = " ".join(sys.argv[2:])
                json_output_mode(user_input)
            else:
                print("Usage: python3 test_semantic_routing.py --json '<request>'")
                sys.exit(1)
        elif sys.argv[1] == "--interactive":
            interactive_mode()
        else:
            print(f"Unknown option: {sys.argv[1]}")
            print("Usage:")
            print("  python3 test_semantic_routing.py --test       # Run automated tests")
            print("  python3 test_semantic_routing.py --interactive  # Interactive mode")
            print("  python3 test_semantic_routing.py --json '<request>'  # JSON output")
            sys.exit(1)
    else:
        # Default: run tests
        success = run_tests()
        sys.exit(0 if success else 1)
