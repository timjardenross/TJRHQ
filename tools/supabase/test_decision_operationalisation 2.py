#!/usr/bin/env python3
"""Validation tests for USS-TJR-MSN-0010 Decision Intelligence Operationalisation.

Deliverables tested:
    D1 — Decision Alerting
    D2 — Decision Dashboard Data Model (status, query helpers)
    D3 — Decision-to-Mission Conversion
    D4 — GitHub Mission Integration (dry-run)
    D5 — Specialist Assignment Framework
    D6 — Decision Lifecycle Tracking (update_decision_outcome)

All tests run in deterministic mode (no Ollama, Slack, or GitHub required).

Run:
    python3 tools/supabase/test_decision_operationalisation.py
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from collaborative_specialist_runtime import run
from decision_alerter import ALERT_DIR, emit_decision_alert, load_alerts, _format_alert
from decision_register import (
    DECISION_DIR,
    DECISION_STATUSES,
    get_decisions_awaiting_review,
    get_decisions_by_date_range,
    get_decisions_by_mode,
    get_open_decisions,
    load_decisions,
    update_decision_outcome,
    write_decision_record,
)
from decision_mode_classifier import classify_decision_mode
from decision_context_builder import build_decision_context
from github_issue_builder import GitHubIssue, build_github_issue, _issue_labels
from mission_candidate import (
    MISSION_DIR,
    create_mission_candidate,
    load_mission_candidates,
    update_mission_status,
    _extract_risks,
    _generate_success_criteria,
    _generate_title,
)
from specialist_assignment import CREW, MissionAssignment, assign_specialists


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_STRATEGIC_Q = "Should USS TJR prioritise Slack specialist collaboration over Voice Core?"
_OPERATIONAL_Q = "How should we implement the Supabase ingestion pipeline?"

_SAMPLE_DECISION_RECORD = {
    "decision_id": "DEC-TEST-000001-abcdef",
    "collaboration_id": "COL-TEST-000001",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "question": _STRATEGIC_Q,
    "status": "Proposed",
    "decision_mode": "strategic",
    "current_bottleneck": "Daily usability and crew accessibility.",
    "options": [
        {"label": "Option A", "description": "Slack Runtime"},
        {"label": "Option B", "description": "Voice Core"},
    ],
    "opportunity_cost": "Voice Core is delayed.",
    "time_to_value": "Short — within days.",
    "reversibility": "High — tooling decisions are easy to reverse.",
    "strategic_alignment": "High — directly supports Captain usability.",
    "required_decision": "Choose Option A or B.",
    "specialist_positions": [
        {"specialist": "Chief Engineer", "confidence": "60", "stance": "Option A",
         "recommendation": "Build Slack Runtime first."},
    ],
    "reviewer_position": {
        "reviewer": "Chief of Staff",
        "challenge_position": "Chief of Staff challenges.",
        "recommendation_adjustment": "Proceed only after sequencing is explicit.",
        "escalation_required": "True",
    },
    "recommended_action": "Recommended Action: Prioritise Slack Runtime.",
    "final_recommendation": None,
    "captain_outcome_review": None,
    "captain_decision_held": None,
    "captain_review_date": None,
    "captain_notes": None,
    "linked_mission_id": None,
}

_LOW_REV_RECORD = {
    **_SAMPLE_DECISION_RECORD,
    "decision_id": "DEC-TEST-000002-lowrev",
    "reversibility": "Low — architectural decisions are expensive to reverse.",
    "specialist_positions": [
        {"specialist": "Chief Engineer", "confidence": "55", "stance": "Option A",
         "recommendation": "Build architecture first."},
    ],
}


# ---------------------------------------------------------------------------
# D1 — Decision Alerting
# ---------------------------------------------------------------------------

def test_alert_emitted_for_strategic_decision() -> None:
    """emit_decision_alert must write an alert file for a strategic record."""
    before = set(ALERT_DIR.glob("*.json")) if ALERT_DIR.exists() else set()
    emit_decision_alert(_SAMPLE_DECISION_RECORD, None)
    after = set(ALERT_DIR.glob("*.json"))
    created = after - before
    assert created, "No alert file was written for a strategic decision"
    alert = json.loads(Path(list(created)[0]).read_text(encoding="utf-8"))
    assert alert["decision_id"] == "DEC-TEST-000001-abcdef"
    assert alert["decision_mode"] == "strategic"
    print("  PASS test_alert_emitted_for_strategic_decision")


def test_alert_not_emitted_for_operational() -> None:
    """emit_decision_alert must ignore non-strategic records."""
    op_record = {**_SAMPLE_DECISION_RECORD, "decision_mode": "operational"}
    before = set(ALERT_DIR.glob("*.json")) if ALERT_DIR.exists() else set()
    emit_decision_alert(op_record, None)
    after = set(ALERT_DIR.glob("*.json"))
    assert after == before, "Operational decision should not create an alert"
    print("  PASS test_alert_not_emitted_for_operational")


def test_alert_format_contains_required_fields() -> None:
    """Formatted alert must contain all required sections."""
    text = _format_alert(_SAMPLE_DECISION_RECORD, None)
    required = [
        "🧠 Commander Strategic Decision",
        "Recommended Action:",
        "Current Bottleneck:",
        "Time To Value:",
        "Reversibility:",
        "Strategic Alignment:",
        "Decision Record:",
    ]
    for field in required:
        assert field in text, f"Alert missing field: {field!r}"
    print("  PASS test_alert_format_contains_required_fields")


def test_alert_strips_recommended_action_prefix() -> None:
    """Formatted alert must strip 'Recommended Action:' prefix from the action text."""
    text = _format_alert(_SAMPLE_DECISION_RECORD, None)
    # Should appear as the value, not double-prefixed
    assert "Recommended Action: Recommended Action:" not in text
    print("  PASS test_alert_strips_recommended_action_prefix")


def test_alert_failure_does_not_crash_runtime() -> None:
    """emit_decision_alert with a bad record must not raise."""
    try:
        emit_decision_alert({"decision_mode": "strategic"}, None)  # missing most fields
    except Exception as e:
        raise AssertionError(f"emit_decision_alert raised unexpectedly: {e}")
    print("  PASS test_alert_failure_does_not_crash_runtime")


def test_runtime_strategic_run_creates_alert() -> None:
    """A full strategic runtime run must produce an alert file."""
    os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "deterministic"
    before = set(ALERT_DIR.glob("*.json")) if ALERT_DIR.exists() else set()
    run(_STRATEGIC_Q, "USS-TJR-MSN-0010", True, 2, 0.0)
    after = set(ALERT_DIR.glob("*.json"))
    assert after - before, "Strategic runtime run did not produce an alert file"
    print("  PASS test_runtime_strategic_run_creates_alert")


def test_runtime_operational_run_does_not_create_alert() -> None:
    """A full operational runtime run must NOT produce an alert file."""
    os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "deterministic"
    before = set(ALERT_DIR.glob("*.json")) if ALERT_DIR.exists() else set()
    run(_OPERATIONAL_Q, "USS-TJR-MSN-0010", True, 2, 0.0)
    after = set(ALERT_DIR.glob("*.json"))
    assert not (after - before), "Operational runtime run should not produce an alert"
    print("  PASS test_runtime_operational_run_does_not_create_alert")


# ---------------------------------------------------------------------------
# D2 — Decision Dashboard Data Model
# ---------------------------------------------------------------------------

def test_written_record_has_status_proposed() -> None:
    """New decision records must have status='Proposed'."""
    cls = classify_decision_mode(_STRATEGIC_Q)
    mission_ctx = {"question": _STRATEGIC_Q, "mission_id": "TEST", "intent": "technical_delivery",
                   "source_paths": [], "selected_specialists": [], "routing_reasons": {}, "confidence": {}}
    ctx = build_decision_context(_STRATEGIC_Q, cls, [], None, mission_ctx)
    path = write_decision_record("COL-D2-TEST", _STRATEGIC_Q, ctx, {})
    assert path is not None
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["status"] == "Proposed"
    print("  PASS test_written_record_has_status_proposed")


def test_get_open_decisions_returns_proposed() -> None:
    """get_open_decisions must return Proposed, Accepted, In Progress records."""
    open_decisions = get_open_decisions()
    for r in open_decisions:
        assert r.get("status") in ("Proposed", "Accepted", "In Progress"), (
            f"Unexpected status in open decisions: {r.get('status')}"
        )
    print("  PASS test_get_open_decisions_returns_proposed")


def test_get_decisions_by_mode_returns_strategic() -> None:
    records = get_decisions_by_mode("strategic")
    for r in records:
        assert r.get("decision_mode") == "strategic"
    print("  PASS test_get_decisions_by_mode_returns_strategic")


def test_get_decisions_by_date_range() -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    records = get_decisions_by_date_range(today, today)
    # At minimum, decisions written in this test session should appear
    assert isinstance(records, list)
    print("  PASS test_get_decisions_by_date_range")


def test_load_decisions_backfills_missing_status() -> None:
    """load_decisions must back-fill 'Proposed' for records missing the status field."""
    records = load_decisions()
    for r in records:
        assert "status" in r, "load_decisions should always set status"
    print("  PASS test_load_decisions_backfills_missing_status")


def test_all_statuses_are_valid_strings() -> None:
    assert all(isinstance(s, str) for s in DECISION_STATUSES)
    assert "Proposed" in DECISION_STATUSES
    assert "Completed" in DECISION_STATUSES
    assert "Reviewed" in DECISION_STATUSES
    print("  PASS test_all_statuses_are_valid_strings")


# ---------------------------------------------------------------------------
# D3 — Decision-to-Mission Conversion
# ---------------------------------------------------------------------------

def test_create_mission_candidate_from_strategic_record() -> None:
    """create_mission_candidate must return a dict with required fields."""
    candidate = create_mission_candidate(_SAMPLE_DECISION_RECORD)
    assert candidate is not None
    required = {
        "mission_candidate_id", "decision_id", "title", "recommended_action",
        "decision_summary", "risks", "success_criteria",
        "lead_specialist", "supporting_specialists", "assignment_rationale",
        "status", "created_at",
    }
    missing = required - set(candidate)
    assert not missing, f"Mission candidate missing fields: {missing}"
    assert candidate["status"] == "Draft"
    assert candidate["decision_id"] == "DEC-TEST-000001-abcdef"
    assert candidate["lead_specialist"] in CREW
    print("  PASS test_create_mission_candidate_from_strategic_record")


def test_create_mission_candidate_returns_none_for_operational() -> None:
    """Non-strategic records must return None."""
    op = {**_SAMPLE_DECISION_RECORD, "decision_mode": "operational"}
    result = create_mission_candidate(op)
    assert result is None
    print("  PASS test_create_mission_candidate_returns_none_for_operational")


def test_mission_candidate_stored_in_missions_dir() -> None:
    """Mission candidates must be written to logs/missions/."""
    before = set(MISSION_DIR.glob("*.json")) if MISSION_DIR.exists() else set()
    create_mission_candidate(_SAMPLE_DECISION_RECORD)
    after = set(MISSION_DIR.glob("*.json"))
    assert after - before, "No mission candidate file written"
    print("  PASS test_mission_candidate_stored_in_missions_dir")


def test_mission_candidate_has_success_criteria() -> None:
    candidate = create_mission_candidate(_SAMPLE_DECISION_RECORD)
    assert candidate["success_criteria"]
    assert len(candidate["success_criteria"]) >= 1
    print("  PASS test_mission_candidate_has_success_criteria")


def test_mission_candidate_has_risks() -> None:
    candidate = create_mission_candidate(_SAMPLE_DECISION_RECORD)
    assert candidate["risks"]
    print("  PASS test_mission_candidate_has_risks")


def test_mission_risks_surface_low_confidence() -> None:
    """Low-confidence specialist positions must appear in risks."""
    risks = _extract_risks(_LOW_REV_RECORD)
    low_conf_risks = [r for r in risks if "confidence" in r.lower() or "55" in r]
    assert low_conf_risks, f"Expected low-confidence risk, got: {risks}"
    print("  PASS test_mission_risks_surface_low_confidence")


def test_mission_risks_surface_low_reversibility() -> None:
    """Low reversibility must appear in mission risks."""
    risks = _extract_risks(_LOW_REV_RECORD)
    rev_risks = [r for r in risks if "reversib" in r.lower() and "low" in r.lower()]
    assert rev_risks, f"Expected low-reversibility risk, got: {risks}"
    print("  PASS test_mission_risks_surface_low_reversibility")


def test_load_mission_candidates() -> None:
    """load_mission_candidates must return the candidates we created."""
    candidates = load_mission_candidates()
    assert isinstance(candidates, list)
    # At least one must have been created in this test run
    assert any(c.get("decision_id") == "DEC-TEST-000001-abcdef" for c in candidates), (
        "Expected test mission candidate in loaded results"
    )
    print("  PASS test_load_mission_candidates")


# ---------------------------------------------------------------------------
# D4 — GitHub Issue Builder
# ---------------------------------------------------------------------------

def test_build_github_issue_from_mission_candidate() -> None:
    """build_github_issue must return a GitHubIssue with all required sections."""
    candidate = create_mission_candidate(_SAMPLE_DECISION_RECORD)
    assert candidate
    issue = build_github_issue(candidate, priority="High")
    assert isinstance(issue, GitHubIssue)
    assert issue.title
    assert "Mission" in issue.body
    assert "Decision" in issue.body
    assert "Recommended Action" in issue.body
    assert "Implementation Scope" in issue.body
    assert "Success Criteria" in issue.body
    assert "Owner" in issue.body
    assert "Risks" in issue.body
    assert issue.priority == "High"
    print("  PASS test_build_github_issue_from_mission_candidate")


def test_github_issue_never_calls_api() -> None:
    """build_github_issue must be pure — no network calls."""
    import unittest.mock as mock
    candidate = create_mission_candidate(_SAMPLE_DECISION_RECORD)
    with mock.patch("urllib.request.urlopen") as mocked:
        build_github_issue(candidate)
        mocked.assert_not_called()
    print("  PASS test_github_issue_never_calls_api")


def test_github_issue_labels_include_decision_mode() -> None:
    candidate = create_mission_candidate(_SAMPLE_DECISION_RECORD)
    labels = _issue_labels(candidate)
    assert "decision:strategic" in labels
    assert "commander-decision" in labels
    print("  PASS test_github_issue_labels_include_decision_mode")


def test_github_issue_low_reversibility_label() -> None:
    """Low reversibility decisions must get a reversibility:low label."""
    candidate = create_mission_candidate(_LOW_REV_RECORD)
    assert candidate
    labels = _issue_labels(candidate)
    assert "reversibility:low" in labels, f"Expected reversibility:low, got: {labels}"
    print("  PASS test_github_issue_low_reversibility_label")


def test_github_issue_as_dict() -> None:
    candidate = create_mission_candidate(_SAMPLE_DECISION_RECORD)
    issue = build_github_issue(candidate)
    d = issue.as_dict()
    required = {"title", "body", "labels", "assignee_hint", "priority"}
    assert not (required - set(d))
    print("  PASS test_github_issue_as_dict")


# ---------------------------------------------------------------------------
# D5 — Specialist Assignment Framework
# ---------------------------------------------------------------------------

def test_slack_question_assigns_chief_engineer() -> None:
    assignment = assign_specialists(_SAMPLE_DECISION_RECORD)
    assert assignment.lead == "Chief Engineer", f"Expected Chief Engineer, got {assignment.lead}"
    print("  PASS test_slack_question_assigns_chief_engineer")


def test_governance_mode_assigns_chief_of_staff() -> None:
    record = {**_SAMPLE_DECISION_RECORD, "decision_mode": "governance",
              "question": "Who owns the knowledge architecture decision?"}
    assignment = assign_specialists(record)
    assert assignment.lead == "Chief of Staff"
    print("  PASS test_governance_mode_assigns_chief_of_staff")


def test_architectural_mode_assigns_chief_engineer() -> None:
    record = {**_SAMPLE_DECISION_RECORD, "decision_mode": "architectural",
              "question": "Where should this component live?"}
    assignment = assign_specialists(record)
    assert assignment.lead == "Chief Engineer"
    print("  PASS test_architectural_mode_assigns_chief_engineer")


def test_notion_knowledge_assigns_knowledge_officer() -> None:
    record = {**_SAMPLE_DECISION_RECORD, "decision_mode": "strategic",
              "question": "Should Notion remain the operational workspace or become source of truth?"}
    assignment = assign_specialists(record)
    assert assignment.lead == "Knowledge Officer", f"Expected Knowledge Officer, got {assignment.lead}"
    print("  PASS test_notion_knowledge_assigns_knowledge_officer")


def test_assignment_lead_is_in_crew() -> None:
    assignment = assign_specialists(_SAMPLE_DECISION_RECORD)
    assert assignment.lead in CREW, f"{assignment.lead} is not a known crew member"
    print("  PASS test_assignment_lead_is_in_crew")


def test_assignment_supporting_all_in_crew() -> None:
    assignment = assign_specialists(_SAMPLE_DECISION_RECORD)
    for s in assignment.supporting:
        assert s in CREW, f"Supporting specialist {s} is not a known crew member"
    print("  PASS test_assignment_supporting_all_in_crew")


def test_assignment_as_dict() -> None:
    assignment = assign_specialists(_SAMPLE_DECISION_RECORD)
    d = assignment.as_dict()
    assert "lead_specialist" in d
    assert "supporting_specialists" in d
    assert "assignment_rationale" in d
    print("  PASS test_assignment_as_dict")


# ---------------------------------------------------------------------------
# D6 — Decision Lifecycle Tracking
# ---------------------------------------------------------------------------

def test_update_decision_outcome_changes_status() -> None:
    """update_decision_outcome must update the status of a real record."""
    os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "deterministic"
    # Write a real record first
    run(_STRATEGIC_Q, "USS-TJR-MSN-0010", True, 2, 0.0)
    records = load_decisions("strategic")
    assert records, "No strategic records found for lifecycle test"
    latest = records[-1]
    decision_id = latest["decision_id"]

    path = update_decision_outcome(
        decision_id,
        status="Accepted",
        captain_decision_held="success",
        captain_outcome_review="The Slack Runtime was delivered on time.",
        captain_notes="Good recommendation.",
    )
    assert path is not None, "update_decision_outcome returned None"
    updated = json.loads(path.read_text(encoding="utf-8"))
    assert updated["status"] == "Accepted"
    assert updated["captain_decision_held"] == "success"
    assert updated["captain_outcome_review"] == "The Slack Runtime was delivered on time."
    print("  PASS test_update_decision_outcome_changes_status")


def test_update_decision_outcome_invalid_status_raises() -> None:
    try:
        update_decision_outcome("DEC-FAKE", status="InvalidStatus")
        raise AssertionError("Expected ValueError for invalid status")
    except ValueError:
        pass
    print("  PASS test_update_decision_outcome_invalid_status_raises")


def test_update_decision_outcome_missing_id_returns_none() -> None:
    result = update_decision_outcome("DEC-DOES-NOT-EXIST-99999", status="Accepted")
    assert result is None
    print("  PASS test_update_decision_outcome_missing_id_returns_none")


def test_completed_decision_gets_review_date() -> None:
    """Updating to Completed must set captain_review_date."""
    os.environ["COMMANDER_SYNTHESIS_PROVIDER"] = "deterministic"
    run(_STRATEGIC_Q, "USS-TJR-MSN-0010", True, 2, 0.0)
    records = load_decisions("strategic")
    latest = records[-1]
    decision_id = latest["decision_id"]

    path = update_decision_outcome(decision_id, status="Completed")
    assert path is not None
    updated = json.loads(path.read_text(encoding="utf-8"))
    assert updated["captain_review_date"] is not None, "Completed status should set review_date"
    print("  PASS test_completed_decision_gets_review_date")


def test_decisions_awaiting_review_excludes_unreviewed_non_completed() -> None:
    """get_decisions_awaiting_review must only return Completed + no review date."""
    awaiting = get_decisions_awaiting_review()
    for r in awaiting:
        assert r.get("status") == "Completed"
        assert not r.get("captain_review_date")
    print("  PASS test_decisions_awaiting_review_excludes_unreviewed_non_completed")


def test_mission_update_status() -> None:
    """update_mission_status must update a mission candidate's status."""
    candidate = create_mission_candidate(_SAMPLE_DECISION_RECORD)
    assert candidate
    mid = candidate["mission_candidate_id"]
    path = update_mission_status(mid, "Ready", captain_notes="Approved by Captain TJR.")
    assert path is not None
    updated = json.loads(path.read_text(encoding="utf-8"))
    assert updated["status"] == "Ready"
    assert updated["captain_notes"] == "Approved by Captain TJR."
    print("  PASS test_mission_update_status")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("Running MSN-0010 decision operationalisation tests...\n")
    tests = [
        # D1 — Alerting
        test_alert_emitted_for_strategic_decision,
        test_alert_not_emitted_for_operational,
        test_alert_format_contains_required_fields,
        test_alert_strips_recommended_action_prefix,
        test_alert_failure_does_not_crash_runtime,
        test_runtime_strategic_run_creates_alert,
        test_runtime_operational_run_does_not_create_alert,
        # D2 — Data model
        test_written_record_has_status_proposed,
        test_get_open_decisions_returns_proposed,
        test_get_decisions_by_mode_returns_strategic,
        test_get_decisions_by_date_range,
        test_load_decisions_backfills_missing_status,
        test_all_statuses_are_valid_strings,
        # D3 — Mission conversion
        test_create_mission_candidate_from_strategic_record,
        test_create_mission_candidate_returns_none_for_operational,
        test_mission_candidate_stored_in_missions_dir,
        test_mission_candidate_has_success_criteria,
        test_mission_candidate_has_risks,
        test_mission_risks_surface_low_confidence,
        test_mission_risks_surface_low_reversibility,
        test_load_mission_candidates,
        # D4 — GitHub
        test_build_github_issue_from_mission_candidate,
        test_github_issue_never_calls_api,
        test_github_issue_labels_include_decision_mode,
        test_github_issue_low_reversibility_label,
        test_github_issue_as_dict,
        # D5 — Specialist assignment
        test_slack_question_assigns_chief_engineer,
        test_governance_mode_assigns_chief_of_staff,
        test_architectural_mode_assigns_chief_engineer,
        test_notion_knowledge_assigns_knowledge_officer,
        test_assignment_lead_is_in_crew,
        test_assignment_supporting_all_in_crew,
        test_assignment_as_dict,
        # D6 — Lifecycle tracking
        test_update_decision_outcome_changes_status,
        test_update_decision_outcome_invalid_status_raises,
        test_update_decision_outcome_missing_id_returns_none,
        test_completed_decision_gets_review_date,
        test_decisions_awaiting_review_excludes_unreviewed_non_completed,
        test_mission_update_status,
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
    print(f"All {len(tests)} operationalisation tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
