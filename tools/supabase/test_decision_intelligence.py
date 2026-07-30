#!/usr/bin/env python3
"""Validation tests for USS-TJR-MSN-0009A Decision Intelligence Core.

All tests run in deterministic mode (no Ollama required).

Run:
    python3 tools/supabase/test_decision_intelligence.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from collaboration_logger import LOG_DIR
from collaborative_specialist_runtime import run
from decision_mode_classifier import (
    DecisionMode,
    classify_decision_mode,
)
from decision_context_builder import (
    build_decision_context,
    _extract_options,
    _infer_bottleneck,
    _infer_opportunity_cost,
)
from specialist_executor import SpecialistOutput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_output(specialist: str, recommendation: str = "", confidence: int = 75) -> SpecialistOutput:
    return SpecialistOutput(
        specialist=specialist,
        routing_reason="Test routing.",
        perspective=f"{specialist} perspective.",
        recommendation=recommendation or f"{specialist} recommends the primary path.",
        confidence=confidence,
        sources=["knowledge/test-source.md"],
        latency_ms=0.0,
        retrieval_mode="semantic",
    )


MISSION_CTX = {
    "question": "Should USS TJR prioritise Slack over Voice Core?",
    "mission_id": "USS-TJR-MSN-0009A",
    "intent": "technical_delivery",
    "source_paths": [],
    "selected_specialists": ["Chief Engineer"],
    "routing_reasons": {},
    "confidence": {},
}


# ---------------------------------------------------------------------------
# Decision Mode Classifier tests
# ---------------------------------------------------------------------------

def test_classify_strategic_prioritisation() -> None:
    q = "Should USS TJR prioritise Slack specialist collaboration over Voice Core?"
    result = classify_decision_mode(q)
    assert result.mode == DecisionMode.STRATEGIC, f"Expected strategic, got {result.mode}"
    assert result.confidence >= 50
    assert result.matched_signals
    print("  PASS test_classify_strategic_prioritisation")


def test_classify_strategic_build_now() -> None:
    q = "Should we build the Notion Command Centre now?"
    result = classify_decision_mode(q)
    assert result.mode == DecisionMode.STRATEGIC, f"Expected strategic, got {result.mode}"
    print("  PASS test_classify_strategic_build_now")


def test_classify_strategic_invest() -> None:
    q = "Should we invest in Notion visibility this quarter?"
    result = classify_decision_mode(q)
    assert result.mode == DecisionMode.STRATEGIC, f"Expected strategic, got {result.mode}"
    print("  PASS test_classify_strategic_invest")


def test_classify_operational_how() -> None:
    q = "How should this be implemented?"
    result = classify_decision_mode(q)
    assert result.mode == DecisionMode.OPERATIONAL, f"Expected operational, got {result.mode}"
    print("  PASS test_classify_operational_how")


def test_classify_operational_sequence() -> None:
    q = "What sequence should we follow for the Voice Core rollout?"
    result = classify_decision_mode(q)
    assert result.mode == DecisionMode.OPERATIONAL, f"Expected operational, got {result.mode}"
    print("  PASS test_classify_operational_sequence")


def test_classify_architectural_where() -> None:
    q = "Where should this component live in the USS TJR architecture?"
    result = classify_decision_mode(q)
    assert result.mode == DecisionMode.ARCHITECTURAL, f"Expected architectural, got {result.mode}"
    print("  PASS test_classify_architectural_where")


def test_classify_architectural_service() -> None:
    q = "How should this service interact with the Supabase knowledge store?"
    result = classify_decision_mode(q)
    assert result.mode == DecisionMode.ARCHITECTURAL, f"Expected architectural, got {result.mode}"
    print("  PASS test_classify_architectural_service")


def test_classify_governance_who_owns() -> None:
    q = "Who owns the knowledge architecture decision?"
    result = classify_decision_mode(q)
    assert result.mode == DecisionMode.GOVERNANCE, f"Expected governance, got {result.mode}"
    print("  PASS test_classify_governance_who_owns")


def test_classify_governance_who_approves() -> None:
    q = "Who approves new specialist commissions?"
    result = classify_decision_mode(q)
    assert result.mode == DecisionMode.GOVERNANCE, f"Expected governance, got {result.mode}"
    print("  PASS test_classify_governance_who_approves")


def test_classify_no_signals_defaults_operational() -> None:
    q = "Tell me about the weather."
    result = classify_decision_mode(q)
    assert result.mode == DecisionMode.OPERATIONAL
    assert result.confidence < 60
    print("  PASS test_classify_no_signals_defaults_operational")


# ---------------------------------------------------------------------------
# Decision Context Builder tests
# ---------------------------------------------------------------------------

def test_build_context_has_required_keys() -> None:
    from decision_mode_classifier import classify_decision_mode
    q = "Should USS TJR prioritise Slack over Voice Core?"
    cls = classify_decision_mode(q)
    outputs = [_make_output("Chief Engineer"), _make_output("Chief of Staff")]
    ctx = build_decision_context(q, cls, outputs, None, MISSION_CTX)
    required = {
        "question", "decision_mode", "decision_mode_confidence",
        "current_situation", "current_bottleneck", "options",
        "specialist_positions", "reviewer_position",
        "strategic_alignment", "opportunity_cost",
        "time_to_value", "reversibility", "required_decision", "sources",
    }
    missing = required - set(ctx)
    assert not missing, f"Decision context missing keys: {missing}"
    print("  PASS test_build_context_has_required_keys")


def test_build_context_strategic_has_two_options() -> None:
    from decision_mode_classifier import classify_decision_mode
    q = "Should USS TJR prioritise Slack over Voice Core?"
    cls = classify_decision_mode(q)
    outputs = [_make_output("Chief Engineer")]
    ctx = build_decision_context(q, cls, outputs, None, MISSION_CTX)
    assert ctx["decision_mode"] == "strategic"
    assert len(ctx["options"]) == 2, f"Expected 2 options, got {ctx['options']}"
    print("  PASS test_build_context_strategic_has_two_options")


def test_build_context_bottleneck_not_empty() -> None:
    from decision_mode_classifier import classify_decision_mode
    q = "Should USS TJR prioritise Slack over Voice Core?"
    cls = classify_decision_mode(q)
    outputs = [_make_output("Chief Engineer")]
    ctx = build_decision_context(q, cls, outputs, None, MISSION_CTX)
    assert ctx["current_bottleneck"]
    assert len(ctx["current_bottleneck"]) > 10
    print("  PASS test_build_context_bottleneck_not_empty")


def test_build_context_opportunity_cost_not_empty() -> None:
    from decision_mode_classifier import classify_decision_mode
    q = "Should USS TJR prioritise Slack over Voice Core?"
    cls = classify_decision_mode(q)
    outputs = [_make_output("Chief Engineer")]
    ctx = build_decision_context(q, cls, outputs, None, MISSION_CTX)
    assert ctx["opportunity_cost"]
    print("  PASS test_build_context_opportunity_cost_not_empty")


def test_build_context_specialist_positions_populated() -> None:
    from decision_mode_classifier import classify_decision_mode
    q = "Should USS TJR prioritise Slack over Voice Core?"
    cls = classify_decision_mode(q)
    outputs = [
        _make_output("Chief Engineer", "Build the Slack Runtime first."),
        _make_output("Chief of Staff", "Proceed with Slack as the immediate priority."),
    ]
    ctx = build_decision_context(q, cls, outputs, None, MISSION_CTX)
    assert len(ctx["specialist_positions"]) == 2
    for pos in ctx["specialist_positions"]:
        assert "specialist" in pos
        assert "recommendation" in pos
        assert "stance" in pos
    print("  PASS test_build_context_specialist_positions_populated")


def test_build_context_reviewer_position_when_challenge() -> None:
    from decision_mode_classifier import classify_decision_mode
    from challenge_review import ChallengeReview
    q = "Should USS TJR prioritise Slack over Voice Core?"
    cls = classify_decision_mode(q)
    outputs = [_make_output("Chief Engineer")]
    challenge = ChallengeReview(
        reviewer="Chief of Staff",
        reviewer_reason="Test",
        challenge_position="Challenger position.",
        assumptions_challenged=["Assumption A"],
        risks_identified=["Risk A"],
        alternative_view="Alternative.",
        recommendation_adjustment="Adjustment.",
        escalation_required=False,
    )
    ctx = build_decision_context(q, cls, outputs, challenge, MISSION_CTX)
    assert ctx["reviewer_position"] is not None
    assert ctx["reviewer_position"]["reviewer"] == "Chief of Staff"
    print("  PASS test_build_context_reviewer_position_when_challenge")


# ---------------------------------------------------------------------------
# Commander output format tests
# ---------------------------------------------------------------------------

def test_strategic_output_begins_with_recommended_action() -> None:
    """Strategic decision output must contain Recommended Action section."""
    os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "deterministic"
    import io, contextlib
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        run(
            "Should USS TJR prioritise Slack specialist collaboration over Voice Core?",
            "USS-TJR-MSN-0009A",
            True, 2, 0.0,
        )
    output = captured.getvalue()
    assert "## Recommended Action" in output, (
        "Strategic response must contain '## Recommended Action' section"
    )
    assert "Recommended Action:" in output, (
        "Strategic response must begin recommendation with 'Recommended Action:'"
    )
    print("  PASS test_strategic_output_begins_with_recommended_action")


def test_strategic_output_has_trade_offs() -> None:
    os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "deterministic"
    import io, contextlib
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        run(
            "Should USS TJR prioritise Slack specialist collaboration over Voice Core?",
            "USS-TJR-MSN-0009A",
            True, 2, 0.0,
        )
    output = captured.getvalue()
    assert "## Trade-Offs" in output or "## Key Trade-offs" in output
    print("  PASS test_strategic_output_has_trade_offs")


def test_operational_output_format() -> None:
    """Operational question should NOT produce the strategic Recommended Action format."""
    os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "deterministic"
    import io, contextlib
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        run(
            "How should we implement the Supabase knowledge ingestion pipeline?",
            "USS-TJR-MSN-0009A",
            True, 2, 0.0,
        )
    output = captured.getvalue()
    # Operational: should NOT use strategic format
    assert "## Recommended Action" not in output
    print("  PASS test_operational_output_format")


# ---------------------------------------------------------------------------
# Log field tests
# ---------------------------------------------------------------------------

def test_log_contains_decision_intelligence_fields() -> None:
    os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "deterministic"
    before = set(LOG_DIR.glob("*.json")) if LOG_DIR.exists() else set()
    run(
        "Should USS TJR prioritise Slack specialist collaboration over Voice Core?",
        "USS-TJR-MSN-0009A",
        True, 2, 0.0,
    )
    after = set(LOG_DIR.glob("*.json"))
    created = sorted(after - before)
    assert created, "No log file created"
    payload = json.loads(Path(created[-1]).read_text(encoding="utf-8"))

    required_di_fields = {
        "decision_mode",
        "decision_mode_confidence",
        "decision_mode_rationale",
        "current_bottleneck",
        "opportunity_cost",
        "time_to_value",
        "reversibility",
        "strategic_alignment",
    }
    missing = required_di_fields - set(payload)
    assert not missing, f"Log missing decision intelligence fields: {missing}"
    assert payload["decision_mode"] == "strategic"
    assert isinstance(payload["decision_mode_confidence"], int)
    assert payload["current_bottleneck"]
    print("  PASS test_log_contains_decision_intelligence_fields")


def test_log_decision_mode_for_operational_question() -> None:
    os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "deterministic"
    before = set(LOG_DIR.glob("*.json")) if LOG_DIR.exists() else set()
    run(
        "How should we implement the Supabase knowledge ingestion pipeline?",
        "USS-TJR-MSN-0009A",
        True, 2, 0.0,
    )
    after = set(LOG_DIR.glob("*.json"))
    created = sorted(after - before)
    assert created
    payload = json.loads(Path(created[-1]).read_text(encoding="utf-8"))
    assert payload["decision_mode"] == "operational"
    print("  PASS test_log_decision_mode_for_operational_question")


# ---------------------------------------------------------------------------
# Dual Commander + Decision Intelligence compatibility test
# ---------------------------------------------------------------------------

def test_dual_commander_receives_decision_context() -> None:
    """Dual Commander mode must still work with decision context (MSN-0010A + MSN-0009A)."""
    os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "deterministic"
    before = set(LOG_DIR.glob("*.json")) if LOG_DIR.exists() else set()
    run(
        "Should USS TJR prioritise Slack specialist collaboration over Voice Core?",
        "USS-TJR-MSN-0009A",
        True, 2, 0.0,
        False, None, False, False,
        True,  # dual_commander
    )
    after = set(LOG_DIR.glob("*.json"))
    created = sorted(after - before)
    assert created
    payload = json.loads(Path(created[-1]).read_text(encoding="utf-8"))

    # Both MSN-0009A and MSN-0010A fields must be present
    assert payload["decision_mode"] == "strategic"
    assert payload["dual_commander_enabled"] is True
    assert payload["current_bottleneck"]
    assert payload["opportunity_cost"]
    print("  PASS test_dual_commander_receives_decision_context")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("Running MSN-0009A decision intelligence tests...\n")
    tests = [
        # Classifier
        test_classify_strategic_prioritisation,
        test_classify_strategic_build_now,
        test_classify_strategic_invest,
        test_classify_operational_how,
        test_classify_operational_sequence,
        test_classify_architectural_where,
        test_classify_architectural_service,
        test_classify_governance_who_owns,
        test_classify_governance_who_approves,
        test_classify_no_signals_defaults_operational,
        # Context builder
        test_build_context_has_required_keys,
        test_build_context_strategic_has_two_options,
        test_build_context_bottleneck_not_empty,
        test_build_context_opportunity_cost_not_empty,
        test_build_context_specialist_positions_populated,
        test_build_context_reviewer_position_when_challenge,
        # Output format
        test_strategic_output_begins_with_recommended_action,
        test_strategic_output_has_trade_offs,
        test_operational_output_format,
        # Log fields
        test_log_contains_decision_intelligence_fields,
        test_log_decision_mode_for_operational_question,
        # Dual Commander compatibility
        test_dual_commander_receives_decision_context,
    ]
    failures = 0
    for test in tests:
        try:
            test()
        except Exception as error:
            print(f"  FAIL {test.__name__}: {error}")
            failures += 1
    print()
    if failures:
        print(f"{failures}/{len(tests)} tests FAILED")
        return 1
    print(f"All {len(tests)} decision intelligence tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
