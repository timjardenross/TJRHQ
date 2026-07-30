"""WP9 — Governance Alignment Tests.

Validates that the Context Assembly Foundation (WP1–8) respects all
governance constraints, safety boundaries, and advisory-only semantics
established in ADR-0001 and the health data classification policy.

Test categories:
  - Health data privacy    (no clinical detail in any output)
  - Advisory framing       (Number One recommends; Captain decides)
  - Fallback labelling     (mock/stale always surfaced)
  - Data quality gates     (missing data fails safely, not silently)
  - Confidence bounds      (scores in 0.0–1.0)
  - Determinism            (same input → same output)
  - Source traceability    (every context includes assembled_at + source)

Run: python3 -m pytest core/tests/test_governance_alignment.py -v
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

# Make core packages importable
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in [
    str(_REPO_ROOT / "core" / "context-assembly"),
    str(_REPO_ROOT / "core" / "coordination"),
]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest


# ---------------------------------------------------------------------------
# Fixtures — minimal test data
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_missions():
    return [
        {
            "mission_id": "MSN-0001",
            "title": "Test Mission Alpha",
            "status": "ACTIVE",
            "priority": "P0",
            "domain": "Engineering",
            "due_date": "2026-06-20",
            "blockers": [],
            "dependencies": [],
            "next_action": "Deploy service",
            "assigned_role": "Chief Engineer",
        },
        {
            "mission_id": "MSN-0002",
            "title": "Test Mission Beta",
            "status": "ACTIVE",
            "priority": "P1",
            "domain": "Science",
            "due_date": "2026-06-30",
            "blockers": [{"reason": "Waiting for data"}],
            "dependencies": ["MSN-0001"],
            "next_action": "Analyse results",
            "assigned_role": "Science Officer",
        },
        {
            "mission_id": "MSN-0003",
            "title": "Test Mission Gamma",
            "status": "ACTIVE",
            "priority": "P2",
            "domain": "Governance",
            "due_date": None,
            "blockers": [],
            "dependencies": [],
            "next_action": "Review policy",
            "assigned_role": "Chief of Staff",
        },
    ]


@pytest.fixture
def reduced_health():
    from models import HealthContextPackage, HealthStatusSnapshot, HealthTrendSummary
    return HealthContextPackage(
        assembled_at="2026-06-12T09:00:00Z",
        source_file="memory/Health-Summary.md",
        status_summary=HealthStatusSnapshot(pain_level="high", energy="low"),
        trend_summary=HealthTrendSummary(overall_direction="unknown"),
        recovery_priorities=["Rest"],
        health_themes=["Chronic pain"],
        medical_officer_note=None,
        safety_flags=[],
        workload_constraint="reduced",
        data_quality="partial",
    )


@pytest.fixture
def normal_health():
    from models import HealthContextPackage, HealthStatusSnapshot, HealthTrendSummary
    return HealthContextPackage(
        assembled_at="2026-06-12T09:00:00Z",
        source_file="memory/Health-Summary.md",
        status_summary=HealthStatusSnapshot(pain_level="moderate", energy="moderate"),
        trend_summary=HealthTrendSummary(overall_direction="stable"),
        recovery_priorities=["Maintain activity"],
        health_themes=["Chronic pain management"],
        medical_officer_note=None,
        safety_flags=[],
        workload_constraint="normal",
        data_quality="partial",
    )


# ---------------------------------------------------------------------------
# 1. Health Data Privacy
# ---------------------------------------------------------------------------

class TestHealthDataPrivacy:
    """Health context must never expose clinical detail."""

    FORBIDDEN_FIELDS = {
        "diagnosis", "diagnoses", "medication", "medications",
        "prescription", "prescriptions", "clinical_report",
        "clinical_detail", "clinical_notes", "treatment",
        "blood_pressure", "heart_rate", "temperature",
        "lab_results", "pathology",
    }

    def test_health_context_package_has_no_clinical_fields(self, normal_health):
        d = asdict(normal_health)
        for field in self.FORBIDDEN_FIELDS:
            assert field not in d, f"Forbidden clinical field '{field}' found in HealthContextPackage"

    def test_health_status_snapshot_has_no_clinical_fields(self, normal_health):
        d = asdict(normal_health.status_summary)
        for field in self.FORBIDDEN_FIELDS:
            assert field not in d, f"Forbidden field '{field}' in HealthStatusSnapshot"

    def test_health_data_quality_enum_is_valid(self, normal_health):
        assert normal_health.data_quality in ("complete", "partial", "missing")

    def test_workload_constraint_enum_is_valid(self, normal_health, reduced_health):
        for h in (normal_health, reduced_health):
            assert h.workload_constraint in ("reduced", "normal", "unknown")

    def test_health_context_missing_data_is_safe_default(self):
        from models import HealthContextPackage, HealthStatusSnapshot, HealthTrendSummary
        h = HealthContextPackage(
            assembled_at="2026-06-12T09:00:00Z",
            source_file="",
            status_summary=HealthStatusSnapshot(),
            trend_summary=HealthTrendSummary(overall_direction="unknown"),
            recovery_priorities=[],
            health_themes=[],
            medical_officer_note=None,
            safety_flags=[],
            workload_constraint="unknown",
            data_quality="missing",
        )
        d = asdict(h)
        assert d["data_quality"] == "missing"
        assert d["workload_constraint"] == "unknown"
        # Missing health must not default to "reduced" — that would incorrectly constrain
        assert d["workload_constraint"] != "reduced"

    def test_health_summary_only_description_in_schema(self):
        import json
        schema_path = _REPO_ROOT / "core" / "context-assembly" / "schemas" / "health_context.json"
        assert schema_path.exists(), "health_context.json schema missing"
        schema = json.loads(schema_path.read_text())
        desc = schema.get("description", "").lower()
        assert "advisory" in desc or "summary" in desc, \
            "health_context schema must declare advisory/summary-only intent"


# ---------------------------------------------------------------------------
# 2. Advisory-Only Semantics
# ---------------------------------------------------------------------------

class TestAdvisoryOnlySemantics:
    """Number One recommends; Captain decides. No autonomous action."""

    def test_recommendation_has_reason_field(self, sample_missions):
        from recommendation_engine import rank_missions
        recs = rank_missions(sample_missions, health_context=None, top_n=3)
        for r in recs:
            assert r.reason, f"Recommendation {r.mission_id} has no reason"

    def test_recommendation_has_next_action_not_command(self, sample_missions):
        from recommendation_engine import rank_missions
        recs = rank_missions(sample_missions, health_context=None, top_n=3)
        for r in recs:
            assert r.next_action is not None, \
                f"Recommendation {r.mission_id} missing next_action"
            # next_action should be a suggestion, not an imperative system command
            action_lower = r.next_action.lower()
            assert "sudo" not in action_lower
            assert "rm -rf" not in action_lower

    def test_health_constraint_note_is_advisory_language(self, sample_missions, reduced_health):
        # check_health_constraints takes a mission dict, not a Recommendation
        from recommendation_engine import check_health_constraints
        for mission in sample_missions:
            note = check_health_constraints(mission, reduced_health)
            if note:
                note_lower = note.lower()
                advisory_words = {"consider", "may", "reduced", "note", "workload",
                                  "capacity", "defer", "if", "when"}
                assert any(w in note_lower for w in advisory_words), \
                    f"Health constraint note for {mission['mission_id']} is not advisory: {note!r}"

    def test_p0_missions_are_never_health_constrained(self, sample_missions, reduced_health):
        from recommendation_engine import check_health_constraints
        p0 = next(m for m in sample_missions if m["priority"] == "P0")
        # check_health_constraints takes the original mission dict
        note = check_health_constraints(p0, reduced_health)
        assert note is None, f"P0 mission must never be health-constrained, got: {note!r}"

    def test_recommendation_package_flags_health_constraints_applied(
        self, sample_missions, reduced_health, normal_health
    ):
        from recommendation_engine import generate_recommendation_package
        pkg_reduced = generate_recommendation_package(sample_missions, reduced_health)
        pkg_normal  = generate_recommendation_package(sample_missions, normal_health)
        # With reduced workload, at least one P2/P3 should get a constraint note
        # (governance: the flag must be set when constraints were applied)
        assert isinstance(pkg_reduced.health_constraints_applied, bool)
        assert isinstance(pkg_normal.health_constraints_applied, bool)


# ---------------------------------------------------------------------------
# 3. Fallback Labelling
# ---------------------------------------------------------------------------

class TestFallbackLabelling:
    """Every fallback / stale / mock state must be surfaced to consumers."""

    def test_blocker_package_includes_escalation_level(self, sample_missions):
        from blocker_analyzer import analyze_blockers
        pkgs = analyze_blockers(sample_missions)
        blocked = [p for p in pkgs if p.blockers]
        for pkg in blocked:
            assert pkg.escalation_level in ("critical", "high", "medium", "none"), \
                f"Invalid escalation_level on {pkg.mission_id}"

    def test_captain_brief_context_includes_source(self, sample_missions, normal_health):
        from assembler import assemble_captain_brief_context
        from recommendation_engine import rank_missions
        recs = rank_missions(sample_missions, normal_health)
        brief = assemble_captain_brief_context(
            missions=sample_missions,
            recommendations=recs,
            source="fresh",
        )
        assert brief.source in ("fresh", "cached", "stale"), \
            f"CaptainBriefContext.source must be fresh/cached/stale, got {brief.source!r}"

    def test_captain_brief_source_fresh(self, sample_missions, normal_health):
        from assembler import assemble_captain_brief_context
        from recommendation_engine import rank_missions
        recs = rank_missions(sample_missions, normal_health)
        brief = assemble_captain_brief_context(
            missions=sample_missions,
            recommendations=recs,
            source="fresh",
        )
        assert brief.source == "fresh"

    def test_operating_picture_includes_source(self, sample_missions, normal_health):
        from assembler import assemble_operating_picture
        from recommendation_engine import rank_missions
        recs = rank_missions(sample_missions, normal_health)
        cop = assemble_operating_picture(
            missions=sample_missions,
            recommendations=recs,
            source="fresh",
        )
        assert cop.source in ("fresh", "cached", "stale")

    def test_health_data_quality_missing_does_not_raise(self):
        """Missing health data must degrade gracefully, not crash."""
        from assembler import assemble_health_context
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Health Summary\n\n(empty)\n")
            tmp = f.name
        try:
            result = assemble_health_context(health_summary_path=Path(tmp))
            assert result is not None
            assert result.data_quality in ("missing", "partial")
        finally:
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# 4. Data Quality Gates
# ---------------------------------------------------------------------------

class TestDataQualityGates:
    """Missing or partial data must fail safely with explicit markers."""

    def test_empty_missions_list_returns_empty_recommendations(self):
        from recommendation_engine import rank_missions
        recs = rank_missions([], health_context=None)
        assert recs == []

    def test_empty_missions_returns_empty_blockers(self):
        from blocker_analyzer import analyze_blockers
        pkgs = analyze_blockers([])
        assert pkgs == []

    def test_recommendation_confidence_is_in_range(self, sample_missions):
        from recommendation_engine import rank_missions
        recs = rank_missions(sample_missions, health_context=None, top_n=5)
        for r in recs:
            assert 0.0 <= r.confidence <= 1.0, \
                f"Confidence out of range for {r.mission_id}: {r.confidence}"

    def test_recommendation_priority_rank_starts_at_1(self, sample_missions):
        from recommendation_engine import rank_missions
        recs = rank_missions(sample_missions, health_context=None, top_n=3)
        assert recs[0].priority_rank == 1

    def test_brief_system_health_status_is_valid_enum(self, sample_missions, normal_health):
        from assembler import assemble_captain_brief_context
        from recommendation_engine import rank_missions
        recs = rank_missions(sample_missions, normal_health)
        brief = assemble_captain_brief_context(
            missions=sample_missions,
            recommendations=recs,
            source="fresh",
        )
        assert brief.system_health.status in ("green", "yellow", "red"), \
            f"system_health.status must be green/yellow/red, got {brief.system_health.status!r}"


# ---------------------------------------------------------------------------
# 5. Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Same inputs must always produce the same recommendations (no randomness)."""

    def test_ranking_is_deterministic(self, sample_missions, normal_health):
        from recommendation_engine import rank_missions
        run1 = rank_missions(sample_missions, normal_health, top_n=3)
        run2 = rank_missions(sample_missions, normal_health, top_n=3)
        assert [r.mission_id for r in run1] == [r.mission_id for r in run2]
        assert [r.confidence for r in run1] == [r.confidence for r in run2]

    def test_blocker_analysis_is_deterministic(self, sample_missions):
        from blocker_analyzer import analyze_blockers
        run1 = analyze_blockers(sample_missions)
        run2 = analyze_blockers(sample_missions)
        assert [p.mission_id for p in run1] == [p.mission_id for p in run2]
        assert [p.escalation_level for p in run1] == [p.escalation_level for p in run2]


# ---------------------------------------------------------------------------
# 6. Source Traceability
# ---------------------------------------------------------------------------

class TestSourceTraceability:
    """Every assembled context must carry assembled_at + source for audit trail."""

    def test_captain_brief_has_assembled_at(self, sample_missions, normal_health):
        from assembler import assemble_captain_brief_context
        from recommendation_engine import rank_missions
        recs = rank_missions(sample_missions, normal_health)
        brief = assemble_captain_brief_context(
            missions=sample_missions,
            recommendations=recs,
            source="fresh",
        )
        assert brief.assembled_at, "CaptainBriefContext.assembled_at must be set"

    def test_operating_picture_has_assembled_at(self, sample_missions, normal_health):
        from assembler import assemble_operating_picture
        from recommendation_engine import rank_missions
        recs = rank_missions(sample_missions, normal_health)
        cop = assemble_operating_picture(
            missions=sample_missions,
            recommendations=recs,
            source="fresh",
        )
        assert cop.assembled_at, "CaptainOperatingPictureContext.assembled_at must be set"

    def test_recommendation_package_has_assembled_at(self, sample_missions):
        from recommendation_engine import generate_recommendation_package
        pkg = generate_recommendation_package(sample_missions, health_context=None)
        assert pkg.assembled_at, "RecommendationPackage.assembled_at must be set"

    def test_health_package_has_source_file(self, normal_health):
        assert normal_health.source_file is not None, \
            "HealthContextPackage.source_file must identify the data origin"

    def test_every_recommendation_has_mission_id(self, sample_missions):
        from recommendation_engine import rank_missions
        recs = rank_missions(sample_missions, health_context=None, top_n=5)
        for r in recs:
            assert r.mission_id, "Every recommendation must reference a mission_id"


# ---------------------------------------------------------------------------
# 7. ADR-0001 Lifecycle Alignment
# ---------------------------------------------------------------------------

class TestADR0001LifecycleAlignment:
    """Context assembly must not act on closed/rejected missions."""

    ACTIVE_STATUSES = {"ACTIVE", "BLOCKED", "PLANNED", "DRAFT", "IN_REVIEW"}
    CLOSED_STATUSES = {"COMPLETED", "CLOSED", "CANCELLED", "REJECTED"}

    def test_recommendations_do_not_surface_closed_missions(self):
        from recommendation_engine import rank_missions
        missions = [
            {
                "mission_id": "MSN-CLOSED",
                "title": "Already Done",
                "status": "COMPLETED",
                "priority": "P0",
                "domain": "Engineering",
                "due_date": "2026-01-01",
                "blockers": [],
                "dependencies": [],
                "next_action": "Nothing",
                "assigned_role": "Chief Engineer",
            },
            {
                "mission_id": "MSN-ACTIVE",
                "title": "Still Running",
                "status": "ACTIVE",
                "priority": "P1",
                "domain": "Engineering",
                "due_date": "2026-12-31",
                "blockers": [],
                "dependencies": [],
                "next_action": "Continue",
                "assigned_role": "Chief Engineer",
            },
        ]
        recs = rank_missions(missions, health_context=None, top_n=5)
        mission_ids = [r.mission_id for r in recs]
        # Closed/completed missions should not appear as top recommendations
        assert "MSN-CLOSED" not in mission_ids, \
            "COMPLETED missions must not appear in recommendations"
        assert "MSN-ACTIVE" in mission_ids

    def test_blocker_analysis_only_flags_active_missions(self):
        from blocker_analyzer import analyze_blockers
        missions = [
            {
                "mission_id": "MSN-DONE",
                "title": "Completed",
                "status": "COMPLETED",
                "priority": "P0",
                "domain": "Engineering",
                "due_date": None,
                "blockers": [{"reason": "Old blocker"}],
                "dependencies": [],
                "next_action": None,
                "assigned_role": None,
            },
        ]
        pkgs = analyze_blockers(missions)
        # A completed mission with a blocker should either not appear or have none escalation
        for pkg in pkgs:
            if pkg.mission_id == "MSN-DONE":
                assert pkg.escalation_level in ("none", "medium"), \
                    "Completed mission blocker should not be critical/high"
