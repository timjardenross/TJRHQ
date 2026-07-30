#!/usr/bin/env python3
"""
Test & demo script for Issue 14 shadow-mode scoring + Issue 20 provenance + Issue 21 cost governance.

Usage:
    python -m intelligence.analysis.test_shadow_mode_scoring --demo
    python -m intelligence.analysis.test_shadow_mode_scoring --live-scoring

Demonstrates:
1. Dual-path scoring (heuristic + LLM in parallel)
2. Cost governance checks
3. Provenance logging
4. Agreement tracking (heuristic vs LLM)
"""

import argparse
import json
import sys
from pathlib import Path

# Repo setup
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from intelligence.analysis.intelligence_analyst import IntelligenceAnalyst
from intelligence.governance import LLMCostGovernance


def demo_shadow_mode():
    """Demonstrate shadow-mode scoring without real LLM calls."""
    print("=" * 80)
    print("DEMO: Shadow-Mode Scoring (Issue 14) + Provenance (Issue 20)")
    print("=" * 80)

    # Test signal
    test_signal = {
        "title": "Australian Banking System Experiences Payment Network Outage",
        "summary": "Major Australian payment processors report service degradation affecting retail transactions.",
        "sector": "financial",
        "event_type": "payments_disruption",
        "geography": "AU",
        "customer_impact": "high",
        "banking_relevance": "high",
        "cps230_relevance": True,
        "dependency_risk": True,
        "operational_relevance": 0.9,
    }

    print("\n[1] Test Signal:")
    print(json.dumps(test_signal, indent=2))

    # Initialize analyst with shadow-mode + cost governance (Issue 21)
    cost_gov = LLMCostGovernance()  # Uses Supabase if configured
    analyst = IntelligenceAnalyst(
        use_llm=True,  # Shadow-mode requires LLM path enabled
        shadow_mode=True,
        cost_governor=cost_gov,
    )

    print("\n[2] Running Shadow-Mode Scoring (both paths in parallel)...")
    result = analyst.score_dual_path(test_signal, event_id="test-event-001")

    print("\n[3] Heuristic Path Result:")
    print(f"  Breakdown: {result.heuristic.score_breakdown}")
    print(f"  Total Score: {result.heuristic.total_score}")
    print(f"  Risk Rating: {result.heuristic.risk_rating}")
    print(f"  Method: {result.heuristic.method}")

    print("\n[4] LLM Path Result:")
    if result.llm:
        print(f"  Breakdown: {result.llm.score_breakdown}")
        print(f"  Total Score: {result.llm.total_score}")
        print(f"  Risk Rating: {result.llm.risk_rating}")
        print(f"  Provider: {result.llm.provider}")
    else:
        print("  (Not run in this demo; would run in production)")

    print("\n[5] Agreement Analysis (Issue 15 data collection):")
    print(f"  Paths agree on risk_rating: {result.agree}")

    print("\n[6] Provenance (Issue 20 disclosure):")
    print(json.dumps(result.provenance, indent=2, default=str))

    print("\n[7] Phase A Fields to Persist:")
    phase_a_fields = {
        # Authoritative (heuristic, Issue 14 shadow-mode uses this)
        "score_breakdown": result.heuristic.score_breakdown,
        "relevance_score": result.heuristic.relevance_score,
        "risk_rating": result.heuristic.risk_rating,
        "score_method": "heuristic",  # Issue 20 disclosure
        "score_provenance": result.provenance,  # Issue 20 full trail
        # Shadow-mode parallel results (Issue 14)
        "llm_score_breakdown": result.llm.score_breakdown if result.llm else None,
        "llm_relevance_score": result.llm.relevance_score if result.llm else None,
        "llm_risk_rating": result.llm.risk_rating if result.llm else None,
        "llm_provider": result.llm.provider if result.llm else None,
    }
    print(json.dumps(phase_a_fields, indent=2, default=str))

    print("\n✓ Demo complete. In production, these fields would be persisted to Supabase.")
    print("  After 2+ weeks of shadow-mode data, Issue 15 analysis harness will")
    print("  compare heuristic vs LLM against QA decisions to determine if LLM adds value.")


def demo_cost_governance():
    """Demonstrate cost governance checks (Issue 21)."""
    print("\n" + "=" * 80)
    print("DEMO: Cost Governance (Issue 21)")
    print("=" * 80)

    cost_gov = LLMCostGovernance()

    print("\n[1] Check whether signal-scoring calls are allowed today:")
    check = cost_gov.can_call_llm("signal-scoring")
    print(f"  Allowed: {check.allowed}")
    print(f"  Reason: {check.reason}")
    print(f"  Daily calls so far: {check.daily_calls_so_far}")
    print(f"  Daily cost so far: ${check.daily_cost_so_far:.4f}")
    print(f"  Daily limit: {check.daily_limit}")
    print(f"  Cost limit: ${check.cost_limit}")

    print("\n[2] Simulate logging a successful LLM call:")
    logged = cost_gov.log_call(
        task_type="signal-scoring",
        provider="mistral",
        model_name="mistral-7b",
        input_tokens=500,
        output_tokens=200,
        latency_ms=1200,
        success=True,
        event_id="test-event-001",
        estimated_cost_usd=0.00015,
    )
    print(f"  Logged: {logged}")

    print("\n[3] Simulate logging a failed LLM call:")
    logged = cost_gov.log_call(
        task_type="signal-scoring",
        provider="gemini",
        success=False,
        failure_reason="timeout after 5s",
        event_id="test-event-002",
    )
    print(f"  Logged: {logged}")

    print("\n✓ Cost governance demo complete.")
    print("  In production, cost_gov.log_call() is called by IntelligenceAnalyst._score_via_llm(),")
    print("  and can_call_llm() is checked before firing expensive LLM calls.")


def main():
    parser = argparse.ArgumentParser(
        description="Test & demo Issue 14/20/21 integration (shadow-mode scoring + cost governance)"
    )
    parser.add_argument("--demo", action="store_true", help="Run demo (no live Supabase)")
    parser.add_argument(
        "--live-scoring",
        action="store_true",
        help="Run live shadow-mode scoring (requires Supabase + LLM provider configured)",
    )
    args = parser.parse_args()

    if args.demo:
        demo_shadow_mode()
        demo_cost_governance()
    elif args.live_scoring:
        print("Live shadow-mode scoring not yet implemented in this test script.")
        print("Use this in phase_a_enrichment.enrich_and_save(..., shadow_mode=True)")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
