#!/usr/bin/env python3
"""Validation tests for USS-TJR-MSN-0010A Dual Commander Evaluation Mode.

All tests run in deterministic mode (no Ollama required).

Run:
    python3 tools/supabase/test_dual_commander.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from collaboration_logger import LOG_DIR
from collaborative_specialist_runtime import run
from dual_commander_evaluator import (
    DualCommanderEvaluation,
    _compare,
    _extract_section_names,
    _shared_keywords,
    run_dual_commander,
)
from specialist_executor import SpecialistOutput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_output(specialist: str, confidence: int = 75) -> SpecialistOutput:
    return SpecialistOutput(
        specialist=specialist,
        routing_reason="Test routing.",
        perspective=f"{specialist} perspective on the question.",
        recommendation=f"{specialist} recommends proceeding with the primary path.",
        confidence=confidence,
        sources=["knowledge/test-source.md"],
        latency_ms=0.0,
        retrieval_mode="semantic",
    )


SAMPLE_CONTEXT = {
    "question": "Should USS TJR prioritise Slack specialist collaboration over Voice Core?",
    "mission_id": "USS-TJR-MSN-0010A",
    "intent": "technical_delivery",
    "source_paths": ["knowledge/test-source.md"],
}


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_extract_section_names() -> None:
    response = "## Position\nSome text.\n\n## Risks\n- Risk 1\n\n## Next Actions\n- Do something"
    sections = _extract_section_names(response)
    assert "Position" in sections
    assert "Risks" in sections
    assert "Next Actions" in sections
    print("  PASS test_extract_section_names")


def test_shared_keywords() -> None:
    a = "Proceed with Slack integration as the primary communication channel."
    b = "Slack integration should proceed as the primary delivery channel."
    shared = _shared_keywords(a, b)
    assert "slack" in shared or "integration" in shared or "primary" in shared
    print("  PASS test_shared_keywords")


def test_compare_identical_responses() -> None:
    response = (
        "## Position\nProceed with Slack.\n\n"
        "## Risks\n- Risk A\n\n"
        "## Next Actions\n- Action 1"
    )
    comparison = _compare("qwen3:8b", response, "deepseek-r1:14b", response)
    assert isinstance(comparison["areas_of_agreement"], list)
    assert isinstance(comparison["areas_of_difference"], list)
    assert isinstance(comparison["decision_style_observations"], list)
    assert isinstance(comparison["practical_usefulness_notes"], list)
    assert "summary" in comparison
    assert len(comparison["areas_of_agreement"]) >= 1
    print("  PASS test_compare_identical_responses")


def test_compare_different_responses() -> None:
    primary = (
        "## Position\nProceed with Slack first.\n\n"
        "## Key Trade-offs\n- Speed vs depth\n\n"
        "## Risks\n- Risk A\n\n"
        "## Next Actions\n- Action 1"
    )
    candidate = (
        "## Final Recommendation\nProceed with Voice Core.\n\n"
        "## Rationale\nVoice Core is foundational.\n\n"
        "## Risks\n- Risk B"
    )
    comparison = _compare("qwen3:8b", primary, "deepseek-r1:14b", candidate)
    # Must detect section differences
    combined = " ".join(comparison["areas_of_difference"])
    assert len(comparison["areas_of_difference"]) >= 1
    print("  PASS test_compare_different_responses")


def test_dual_commander_evaluation_dataclass() -> None:
    evaluation = DualCommanderEvaluation(
        primary_model="qwen3:8b",
        candidate_model="deepseek-r1:14b",
        primary_response="## Position\nProceed.",
        candidate_response="## Final Recommendation\nProceed with caution.",
        comparison_summary="1 agreement, 1 difference.",
        areas_of_agreement=["Both produced a recommendation."],
        areas_of_difference=["Different section names."],
        decision_style_observations=["Primary: 20 chars."],
        practical_usefulness_notes=["Review position sections."],
    )
    output = evaluation.formatted_output()
    assert "# Dual Commander Evaluation" in output
    assert "## Qwen Commander Recommendation" in output
    assert "## DeepSeek Commander Recommendation" in output
    assert "## Commander Comparison" in output
    assert "### Areas of Agreement" in output
    assert "### Areas of Difference" in output
    assert "### Decision Style Observations" in output
    assert "### Practical Usefulness Notes" in output
    assert "### Captain Decision" in output
    assert "Pending" in output
    print("  PASS test_dual_commander_evaluation_dataclass")


def test_dual_commander_as_dict() -> None:
    evaluation = DualCommanderEvaluation(
        primary_model="qwen3:8b",
        candidate_model="deepseek-r1:14b",
        primary_response="Primary response.",
        candidate_response="Candidate response.",
        comparison_summary="Summary.",
        areas_of_agreement=["Agreement 1."],
        areas_of_difference=["Difference 1."],
        decision_style_observations=["Obs 1."],
        practical_usefulness_notes=["Note 1."],
    )
    d = evaluation.as_dict()
    required_keys = {
        "dual_commander_enabled",
        "primary_model",
        "candidate_model",
        "primary_response",
        "candidate_response",
        "comparison_summary",
        "areas_of_agreement",
        "areas_of_difference",
        "decision_style_observations",
        "practical_usefulness_notes",
        "captain_preferred_model",
        "captain_decision_status",
        "captain_notes",
    }
    missing = required_keys - set(d)
    assert not missing, f"as_dict() missing keys: {missing}"
    assert d["dual_commander_enabled"] is True
    assert d["captain_decision_status"] == "Pending"
    assert d["captain_preferred_model"] is None
    print("  PASS test_dual_commander_as_dict")


def test_run_dual_commander_deterministic() -> None:
    """run_dual_commander must work in deterministic mode (no Ollama required)."""
    os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "deterministic"
    outputs = [_make_output("Chief Engineer"), _make_output("Chief of Staff", 70)]
    evaluation = run_dual_commander(
        "Should USS TJR prioritise Slack specialist collaboration over Voice Core?",
        SAMPLE_CONTEXT,
        outputs,
        challenge=None,
    )
    assert isinstance(evaluation, DualCommanderEvaluation)
    assert evaluation.primary_model == os.environ.get("COMMANDER_PRIMARY_MODEL", "qwen3:8b")
    assert evaluation.candidate_model == os.environ.get("COMMANDER_CANDIDATE_MODEL", "deepseek-r1:14b")
    assert evaluation.primary_response
    assert evaluation.candidate_response
    assert evaluation.captain_decision_status == "Pending"
    assert evaluation.captain_preferred_model is None
    output = evaluation.formatted_output()
    assert "# Dual Commander Evaluation" in output
    print("  PASS test_run_dual_commander_deterministic")


def test_runtime_dual_commander_creates_log() -> None:
    """run() with dual_commander=True must create a log with dual commander fields."""
    os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "deterministic"
    before = set(LOG_DIR.glob("*.json")) if LOG_DIR.exists() else set()

    run(
        "Should USS TJR prioritise Slack specialist collaboration over Voice Core?",
        "USS-TJR-MSN-0010A",
        True,   # keyword
        2,      # limit
        0.0,    # threshold
        False,  # challenge_mode
        None,   # reviewer
        False,  # force_reviewer
        False,  # sync_notion
        True,   # dual_commander
    )

    after = set(LOG_DIR.glob("*.json"))
    created = sorted(after - before)
    assert created, "dual commander run did not create a collaboration log"

    payload = json.loads(Path(created[-1]).read_text(encoding="utf-8"))

    # Core fields must still be present
    core_required = {
        "question", "selected_specialists", "routing_reasons",
        "retrieval_mode", "source_paths", "latency_ms",
    }
    missing_core = core_required - set(payload)
    assert not missing_core, f"Log missing core fields: {missing_core}"

    # MSN-0010A dual commander fields must be present
    dual_required = {
        "dual_commander_enabled",
        "primary_model",
        "candidate_model",
        "primary_response",
        "candidate_response",
        "comparison_summary",
        "areas_of_agreement",
        "areas_of_difference",
        "decision_style_observations",
        "practical_usefulness_notes",
        "captain_preferred_model",
        "captain_decision_status",
        "captain_notes",
    }
    missing_dual = dual_required - set(payload)
    assert not missing_dual, f"Log missing dual commander fields: {missing_dual}"

    assert payload["dual_commander_enabled"] is True
    assert payload["captain_decision_status"] == "Pending"
    assert isinstance(payload["areas_of_agreement"], list)
    assert isinstance(payload["areas_of_difference"], list)
    print("  PASS test_runtime_dual_commander_creates_log")


def test_runtime_existing_mode_unaffected() -> None:
    """run() without --dual-commander must NOT log dual commander fields as True."""
    os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "deterministic"
    before = set(LOG_DIR.glob("*.json")) if LOG_DIR.exists() else set()

    run(
        "How should we build Voice Core?",
        "USS-TJR-MSN-0010A-control",
        True, 2, 0.0,
    )

    after = set(LOG_DIR.glob("*.json"))
    created = sorted(after - before)
    assert created, "control run did not create a log"

    payload = json.loads(Path(created[-1]).read_text(encoding="utf-8"))
    assert payload.get("dual_commander_enabled") is False, (
        "dual_commander_enabled should be False in normal runtime"
    )
    print("  PASS test_runtime_existing_mode_unaffected")


def test_runtime_dual_commander_output_format() -> None:
    """Formatted output must contain all required section headings."""
    os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "deterministic"
    before = set(LOG_DIR.glob("*.json")) if LOG_DIR.exists() else set()
    import io, contextlib

    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        run(
            "Should USS TJR prioritise Slack specialist collaboration over Voice Core?",
            "USS-TJR-MSN-0010A",
            True, 2, 0.0,
            False, None, False, False,
            True,  # dual_commander
        )

    output = captured.getvalue()
    required_sections = [
        "# Dual Commander Evaluation",
        "## Qwen Commander Recommendation",
        "## DeepSeek Commander Recommendation",
        "## Commander Comparison",
        "### Areas of Agreement",
        "### Areas of Difference",
        "### Decision Style Observations",
        "### Practical Usefulness Notes",
        "### Captain Decision",
        "Pending",
    ]
    for section in required_sections:
        assert section in output, f"Missing section in output: {section!r}"
    print("  PASS test_runtime_dual_commander_output_format")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("Running MSN-0010A dual commander tests...\n")
    tests = [
        test_extract_section_names,
        test_shared_keywords,
        test_compare_identical_responses,
        test_compare_different_responses,
        test_dual_commander_evaluation_dataclass,
        test_dual_commander_as_dict,
        test_run_dual_commander_deterministic,
        test_runtime_dual_commander_creates_log,
        test_runtime_existing_mode_unaffected,
        test_runtime_dual_commander_output_format,
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
    print(f"All {len(tests)} dual commander tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
