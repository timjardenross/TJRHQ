#!/usr/bin/env python3
"""Validation tests for USS-TJR-MSN-0009B Decision Intelligence enhancements.

Items tested:
    1. Strategic format applied to challenge mode output
    2. Reversibility passed into challenge reviewer
    3. LLM classifier fallback behaviour (deterministic path tested here)
    4. Decision Register — strategic decisions logged; non-strategic skipped
    5. Notion sync includes decision_mode and current_bottleneck properties

All tests run in deterministic mode (no Ollama required).

Run:
    python3 tools/supabase/test_decision_intelligence_b.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from collaboration_logger import LOG_DIR
from collaborative_specialist_runtime import run
from challenge_review import (
    ChallengeReview,
    _is_low_reversibility,
    run_challenge_review,
    adjustment_for,
)
from decision_mode_classifier import classify_decision_mode, DecisionMode, _rules_classify
from decision_register import DECISION_DIR, load_decisions, write_decision_record
from specialist_executor import SpecialistOutput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_output(specialist: str, confidence: int = 75, recommendation: str = "") -> SpecialistOutput:
    return SpecialistOutput(
        specialist=specialist,
        routing_reason="Test routing.",
        perspective=f"{specialist} perspective.",
        recommendation=recommendation or f"{specialist} recommends the primary path.",
        confidence=confidence,
        sources=[],
        latency_ms=0.0,
        retrieval_mode="semantic",
    )


_STRATEGIC_Q = "Should USS TJR prioritise Slack specialist collaboration over Voice Core?"
_OPERATIONAL_Q = "How should we implement the Supabase knowledge ingestion pipeline?"

_LOW_REV_DECISION_CTX = {
    "decision_mode": "strategic",
    "current_bottleneck": "Daily usability.",
    "options": [{"label": "Option A", "description": "Slack"}, {"label": "Option B", "description": "Voice Core"}],
    "opportunity_cost": "Voice Core is delayed.",
    "time_to_value": "Short.",
    "reversibility": "Low — architectural decisions are expensive to reverse once in production.",
    "strategic_alignment": "High.",
    "required_decision": "Choose one.",
    "specialist_positions": [],
    "reviewer_position": None,
    "sources": [],
    "mission_id": "USS-TJR-MSN-0009B",
    "intent": "technical_delivery",
}

_HIGH_REV_DECISION_CTX = {
    **_LOW_REV_DECISION_CTX,
    "reversibility": "High — tooling decisions can be changed without major structural cost.",
}

_MISSION_CTX = {
    "question": _STRATEGIC_Q,
    "mission_id": "USS-TJR-MSN-0009B",
    "intent": "technical_delivery",
    "source_paths": [],
    "selected_specialists": ["Chief Engineer"],
    "routing_reasons": {},
    "confidence": {},
}


# ---------------------------------------------------------------------------
# 1. Strategic format in challenge mode
# ---------------------------------------------------------------------------

def test_challenge_mode_strategic_has_recommended_action() -> None:
    """When decision_mode=strategic, challenge mode output must contain ## Recommended Action."""
    os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "deterministic"
    import io, contextlib
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        run(
            _STRATEGIC_Q,
            "USS-TJR-MSN-0009B",
            True, 2, 0.0,
            challenge_mode=True,  # challenge enabled
        )
    output = captured.getvalue()
    assert "## Recommended Action" in output, (
        f"Strategic challenge mode must contain '## Recommended Action'. Got:\n{output[:800]}"
    )
    assert "Recommended Action:" in output
    print("  PASS test_challenge_mode_strategic_has_recommended_action")


def test_challenge_mode_strategic_has_expert_challenge_section() -> None:
    """Strategic challenge output must still expose the expert challenge detail."""
    os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "deterministic"
    import io, contextlib
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        run(_STRATEGIC_Q, "USS-TJR-MSN-0009B", True, 2, 0.0, challenge_mode=True)
    output = captured.getvalue()
    assert "## Expert Challenge" in output
    assert "Reviewer:" in output
    print("  PASS test_challenge_mode_strategic_has_expert_challenge_section")


def test_challenge_mode_operational_retains_old_format() -> None:
    """Operational challenge mode must NOT use the strategic ## Recommended Action format."""
    os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "deterministic"
    import io, contextlib
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        run(_OPERATIONAL_Q, "USS-TJR-MSN-0009B", True, 2, 0.0, challenge_mode=True)
    output = captured.getvalue()
    assert "## Recommended Action" not in output
    assert "## Final Recommendation" in output or "## Initial Recommendation" in output
    print("  PASS test_challenge_mode_operational_retains_old_format")


# ---------------------------------------------------------------------------
# 2. Reversibility in challenge reviewer
# ---------------------------------------------------------------------------

def test_low_reversibility_detected() -> None:
    assert _is_low_reversibility("Low — architectural decisions are expensive to reverse.")
    assert _is_low_reversibility("low reversibility")
    assert not _is_low_reversibility("High — can be changed without major cost.")
    assert not _is_low_reversibility("Medium — decision can likely be revisited.")
    print("  PASS test_low_reversibility_detected")


def test_challenge_review_surfaces_low_reversibility_assumption() -> None:
    """When reversibility is low, the reviewer must add it to assumptions_challenged."""
    primary = _make_output("Chief Engineer")
    context = {"source_paths": []}
    review = run_challenge_review(
        _STRATEGIC_Q, "Chief of Staff", "Intent-based", primary, [], context,
        decision_context=_LOW_REV_DECISION_CTX,
    )
    reversibility_assumptions = [a for a in review.assumptions_challenged if "reversib" in a.lower()]
    assert reversibility_assumptions, (
        f"Expected reversibility assumption, got: {review.assumptions_challenged}"
    )
    print("  PASS test_challenge_review_surfaces_low_reversibility_assumption")


def test_challenge_review_surfaces_low_reversibility_risk() -> None:
    """When reversibility is low, the reviewer must add it to risks_identified."""
    primary = _make_output("Chief Engineer")
    context = {"source_paths": []}
    review = run_challenge_review(
        _STRATEGIC_Q, "Chief of Staff", "Intent-based", primary, [], context,
        decision_context=_LOW_REV_DECISION_CTX,
    )
    rev_risks = [r for r in review.risks_identified if "reversib" in r.lower()]
    assert rev_risks, f"Expected reversibility risk, got: {review.risks_identified}"
    print("  PASS test_challenge_review_surfaces_low_reversibility_risk")


def test_challenge_review_escalates_on_low_reversibility_without_sources() -> None:
    """Low reversibility + no sources must trigger escalation_required=True."""
    primary = _make_output("Chief Engineer")
    context = {"source_paths": []}  # no sources
    review = run_challenge_review(
        _STRATEGIC_Q, "Chief of Staff", "Intent-based", primary, [], context,
        decision_context=_LOW_REV_DECISION_CTX,
    )
    assert review.escalation_required is True
    print("  PASS test_challenge_review_escalates_on_low_reversibility_without_sources")


def test_challenge_review_adjustment_mentions_rollback_for_low_reversibility() -> None:
    """Low-reversibility adjustment must mention a rollback or staged approach."""
    primary = _make_output("Chief Engineer")
    adj = adjustment_for("Chief of Staff", primary, _LOW_REV_DECISION_CTX["reversibility"])
    assert "rollback" in adj.lower() or "staged" in adj.lower(), (
        f"Expected rollback/staged in adjustment, got: {adj}"
    )
    print("  PASS test_challenge_review_adjustment_mentions_rollback_for_low_reversibility")


def test_challenge_review_high_reversibility_no_extra_risk() -> None:
    """High reversibility must NOT add a reversibility risk."""
    primary = _make_output("Chief Engineer")
    context = {"source_paths": ["knowledge/test.md"]}
    review = run_challenge_review(
        _STRATEGIC_Q, "Chief of Staff", "Intent-based", primary, [], context,
        decision_context=_HIGH_REV_DECISION_CTX,
    )
    rev_risks = [r for r in review.risks_identified if "reversib" in r.lower()]
    assert not rev_risks, f"High reversibility should not add risk, got: {rev_risks}"
    print("  PASS test_challenge_review_high_reversibility_no_extra_risk")


def test_challenge_review_no_decision_context_still_works() -> None:
    """Omitting decision_context must not break existing callers."""
    primary = _make_output("Chief Engineer")
    context = {"source_paths": []}
    review = run_challenge_review(
        _STRATEGIC_Q, "Chief of Staff", "Intent-based", primary, [], context,
    )
    assert review.reviewer == "Chief of Staff"
    assert review.assumptions_challenged
    assert review.risks_identified
    print("  PASS test_challenge_review_no_decision_context_still_works")


# ---------------------------------------------------------------------------
# 3. LLM classifier — deterministic fallback
# ---------------------------------------------------------------------------

def test_llm_classifier_falls_back_to_rules_when_no_ollama() -> None:
    """With provider=ollama but Ollama unavailable, must fall back to rules-based."""
    os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "ollama"
    os.environ["OLLAMA_BASE_URL"] = "http://localhost:19999"  # non-existent
    try:
        result = classify_decision_mode(_STRATEGIC_Q)
        assert result.mode == DecisionMode.STRATEGIC, (
            f"Fallback should still classify as strategic, got {result.mode}"
        )
    finally:
        os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "deterministic"
        os.environ.pop("OLLAMA_BASE_URL", None)
    print("  PASS test_llm_classifier_falls_back_to_rules_when_no_ollama")


def test_rules_classify_all_four_modes() -> None:
    cases = [
        ("Should we prioritise Slack over Voice Core?", DecisionMode.STRATEGIC),
        ("How should we implement this?", DecisionMode.OPERATIONAL),
        ("Where should this component live?", DecisionMode.ARCHITECTURAL),
        ("Who owns this decision?", DecisionMode.GOVERNANCE),
    ]
    for question, expected in cases:
        result = _rules_classify(question)
        assert result.mode == expected, f"'{question}': expected {expected}, got {result.mode}"
    print("  PASS test_rules_classify_all_four_modes")


# ---------------------------------------------------------------------------
# 4. Decision Register
# ---------------------------------------------------------------------------

def test_strategic_question_creates_decision_record() -> None:
    """A strategic run must create a file in logs/decisions/."""
    os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "deterministic"
    before = set(DECISION_DIR.glob("*.json")) if DECISION_DIR.exists() else set()
    run(_STRATEGIC_Q, "USS-TJR-MSN-0009B", True, 2, 0.0)
    after = set(DECISION_DIR.glob("*.json"))
    created = sorted(after - before)
    assert created, "Strategic run did not create a decision register record"
    record = json.loads(Path(created[-1]).read_text(encoding="utf-8"))
    assert record["decision_id"].startswith("DEC-")
    assert record["question"] == _STRATEGIC_Q
    assert record["decision_mode"] == "strategic"
    assert record["current_bottleneck"]
    assert record["opportunity_cost"]
    assert record["reversibility"]
    assert record["captain_outcome_review"] is None
    assert record["captain_decision_held"] is None
    print("  PASS test_strategic_question_creates_decision_record")


def test_operational_question_does_not_create_decision_record() -> None:
    """A non-strategic run must NOT create a decision register record."""
    os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "deterministic"
    before = set(DECISION_DIR.glob("*.json")) if DECISION_DIR.exists() else set()
    run(_OPERATIONAL_Q, "USS-TJR-MSN-0009B", True, 2, 0.0)
    after = set(DECISION_DIR.glob("*.json"))
    created = after - before
    assert not created, f"Operational run should not create decision record, but got: {created}"
    print("  PASS test_operational_question_does_not_create_decision_record")


def test_write_decision_record_returns_none_for_non_strategic() -> None:
    ctx = {"decision_mode": "operational"}
    result = write_decision_record("COL-001", "How to implement?", ctx, {})
    assert result is None
    print("  PASS test_write_decision_record_returns_none_for_non_strategic")


def test_load_decisions_returns_strategic_records() -> None:
    """After at least one strategic run, load_decisions must return records."""
    os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "deterministic"
    # Ensure at least one strategic decision exists
    run(_STRATEGIC_Q, "USS-TJR-MSN-0009B", True, 2, 0.0)
    records = load_decisions("strategic")
    assert len(records) >= 1
    for r in records:
        assert r.get("decision_mode") == "strategic"
    print("  PASS test_load_decisions_returns_strategic_records")


def test_decision_record_has_required_fields() -> None:
    ctx = {
        "decision_mode": "strategic",
        "current_bottleneck": "Test bottleneck.",
        "options": [{"label": "A", "description": "Option A"}, {"label": "B", "description": "Option B"}],
        "opportunity_cost": "Test cost.",
        "time_to_value": "Short.",
        "reversibility": "High.",
        "strategic_alignment": "High.",
        "required_decision": "Choose.",
        "specialist_positions": [],
        "reviewer_position": None,
        "sources": [],
        "mission_id": "TEST",
        "intent": "technical_delivery",
    }
    path = write_decision_record("COL-TEST", "Should we test this?", ctx, {})
    assert path is not None
    assert path.exists()
    record = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "decision_id", "collaboration_id", "timestamp", "question",
        "decision_mode", "current_bottleneck", "options", "opportunity_cost",
        "time_to_value", "reversibility", "strategic_alignment",
        "specialist_positions", "reviewer_position",
        "captain_outcome_review", "captain_decision_held",
        "captain_review_date", "captain_notes",
    }
    missing = required - set(record)
    assert not missing, f"Decision record missing fields: {missing}"
    print("  PASS test_decision_record_has_required_fields")


# ---------------------------------------------------------------------------
# 5. Notion sync — decision intelligence properties
# ---------------------------------------------------------------------------

def test_notion_sync_properties_include_decision_mode() -> None:
    """_decision_intelligence_properties must include decision_mode when present."""
    import sys
    notion_path = Path(__file__).resolve().parents[1] / "notion"
    if str(notion_path) not in sys.path:
        sys.path.insert(0, str(notion_path))
    from sync_collaboration_logs import _decision_intelligence_properties, properties_for

    record_with_mode = {
        "decision_mode": "strategic",
        "current_bottleneck": "Daily usability.",
        "opportunity_cost": "Voice Core delayed.",
        "time_to_value": "Short.",
        "reversibility": "High.",
        "recommended_action": "Recommended Action: Proceed with Slack.",
    }
    props = _decision_intelligence_properties(record_with_mode)
    assert "Decision Mode" in props, f"Expected 'Decision Mode' in properties, got: {list(props.keys())}"
    assert "Current Bottleneck" in props
    assert "Opportunity Cost" in props
    assert "Time to Value" in props
    assert "Reversibility" in props
    assert "Recommended Action" in props
    print("  PASS test_notion_sync_properties_include_decision_mode")


def test_notion_sync_no_decision_mode_returns_empty() -> None:
    import sys
    notion_path = Path(__file__).resolve().parents[1] / "notion"
    if str(notion_path) not in sys.path:
        sys.path.insert(0, str(notion_path))
    from sync_collaboration_logs import _decision_intelligence_properties

    props = _decision_intelligence_properties({})
    assert props == {}, f"Expected empty dict for missing decision_mode, got: {props}"
    print("  PASS test_notion_sync_no_decision_mode_returns_empty")


def test_notion_properties_for_includes_all_optional_blocks() -> None:
    """properties_for must merge base + decision intelligence + dual commander."""
    import sys
    notion_path = Path(__file__).resolve().parents[1] / "notion"
    if str(notion_path) not in sys.path:
        sys.path.insert(0, str(notion_path))
    from sync_collaboration_logs import properties_for

    record = {
        "collaboration_id": "COL-TEST",
        "decision_mode": "strategic",
        "current_bottleneck": "Bottleneck.",
        "opportunity_cost": "Cost.",
        "time_to_value": "Short.",
        "reversibility": "High.",
        "recommended_action": "Proceed.",
        "dual_commander_enabled": False,
        "timestamp": "2026-06-06",
        "source_count": 0,
        "next_actions": [],
        "risks": [],
        "risks_identified": [],
    }
    props = properties_for(record)
    assert "Name" in props           # base
    assert "Decision Mode" in props  # MSN-0009A/B
    # Dual Commander block not present (disabled)
    assert "Dual Commander" not in props
    print("  PASS test_notion_properties_for_includes_all_optional_blocks")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("Running MSN-0009B decision intelligence tests...\n")
    tests = [
        # 1. Strategic format in challenge mode
        test_challenge_mode_strategic_has_recommended_action,
        test_challenge_mode_strategic_has_expert_challenge_section,
        test_challenge_mode_operational_retains_old_format,
        # 2. Reversibility in challenge reviewer
        test_low_reversibility_detected,
        test_challenge_review_surfaces_low_reversibility_assumption,
        test_challenge_review_surfaces_low_reversibility_risk,
        test_challenge_review_escalates_on_low_reversibility_without_sources,
        test_challenge_review_adjustment_mentions_rollback_for_low_reversibility,
        test_challenge_review_high_reversibility_no_extra_risk,
        test_challenge_review_no_decision_context_still_works,
        # 3. LLM classifier fallback
        test_llm_classifier_falls_back_to_rules_when_no_ollama,
        test_rules_classify_all_four_modes,
        # 4. Decision Register
        test_strategic_question_creates_decision_record,
        test_operational_question_does_not_create_decision_record,
        test_write_decision_record_returns_none_for_non_strategic,
        test_load_decisions_returns_strategic_records,
        test_decision_record_has_required_fields,
        # 5. Notion sync
        test_notion_sync_properties_include_decision_mode,
        test_notion_sync_no_decision_mode_returns_empty,
        test_notion_properties_for_includes_all_optional_blocks,
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
    print(f"All {len(tests)} MSN-0009B tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
