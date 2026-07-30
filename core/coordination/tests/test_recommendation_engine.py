"""
Tests for recommendation_engine — WP5
"""

import sys
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "core" / "context-assembly"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "core" / "coordination"))

from recommendation_engine import (
    rank_missions,
    score_priority,
    check_health_constraints,
    explain_recommendation,
    generate_recommendation_package,
    _deadline_urgency,
    _count_dependents,
)
from models import HealthContextPackage, HealthStatusSnapshot, HealthTrendSummary, Recommendation


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _mission(id="MSN-0001", priority="P1", status="ACTIVE", due_days=None, domain="Engineering",
             blockers=None, dependencies=None, next_action=None):
    m = {
        "mission_id": id,
        "title": f"Test Mission {id}",
        "priority": priority,
        "status": status,
        "domain": domain,
        "blockers": blockers or [],
        "dependencies": dependencies or [],
    }
    if due_days is not None:
        m["due_date"] = str(date.today() + timedelta(days=due_days))
    if next_action:
        m["next_action"] = next_action
    return m


def _health(workload="normal", pain="moderate", energy="moderate"):
    return HealthContextPackage(
        source_file="test",
        status_summary=HealthStatusSnapshot(pain_level=pain, energy=energy),
        trend_summary=HealthTrendSummary(),
        workload_constraint=workload,
        data_quality="complete",
    )


# ---------------------------------------------------------------------------
# score_priority
# ---------------------------------------------------------------------------

class TestScorePriority:

    def test_p0_scores_highest(self):
        m = _mission(priority="P0")
        s = score_priority(m, [m])
        assert s >= 0.40

    def test_p1_scores_above_p2(self):
        p1 = _mission(id="MSN-0001", priority="P1")
        p2 = _mission(id="MSN-0002", priority="P2")
        assert score_priority(p1, [p1, p2]) > score_priority(p2, [p1, p2])

    def test_overdue_adds_score(self):
        no_due = _mission(priority="P2")
        overdue = _mission(priority="P2", due_days=-3)
        assert score_priority(overdue, [overdue]) > score_priority(no_due, [no_due])

    def test_dependents_add_score(self):
        m = _mission(id="MSN-0001", priority="P2")
        dep = _mission(id="MSN-0002", priority="P3", dependencies=["MSN-0001"])
        alone = score_priority(m, [m])
        with_dep = score_priority(m, [m, dep])
        assert with_dep > alone

    def test_score_capped_at_1(self):
        m = _mission(priority="P0", due_days=-5)
        # Add multiple dependents
        deps = [_mission(id=f"MSN-{i:04d}", dependencies=["MSN-0001"]) for i in range(10, 20)]
        s = score_priority(m, [m] + deps)
        assert s <= 1.0


# ---------------------------------------------------------------------------
# rank_missions
# ---------------------------------------------------------------------------

class TestRankMissions:

    def test_returns_top_3(self):
        missions = [_mission(id=f"MSN-{i:04d}", priority="P1") for i in range(10)]
        recs = rank_missions(missions)
        assert len(recs) == 3

    def test_rank_1_is_highest_priority(self):
        m_p0 = _mission(id="MSN-0001", priority="P0")
        m_p3 = _mission(id="MSN-0002", priority="P3")
        recs = rank_missions([m_p0, m_p3])
        assert recs[0].mission_id == "MSN-0001"

    def test_terminal_missions_excluded(self):
        active = _mission(id="MSN-0001", priority="P0", status="ACTIVE")
        completed = _mission(id="MSN-0002", priority="P0", status="COMPLETED")
        recs = rank_missions([active, completed])
        ids = [r.mission_id for r in recs]
        assert "MSN-0001" in ids
        assert "MSN-0002" not in ids

    def test_recommendations_have_rationale(self):
        missions = [_mission(priority="P1", due_days=3)]
        recs = rank_missions(missions)
        assert len(recs) == 1
        assert recs[0].reason != ""
        assert recs[0].next_action != ""

    def test_deterministic(self):
        missions = [_mission(id=f"MSN-{i:04d}", priority="P1") for i in range(5)]
        recs1 = rank_missions(missions)
        recs2 = rank_missions(missions)
        assert [r.mission_id for r in recs1] == [r.mission_id for r in recs2]

    def test_due_today_ranks_above_no_due(self):
        no_due = _mission(id="MSN-0001", priority="P2")
        due_today = _mission(id="MSN-0002", priority="P2", due_days=0)
        recs = rank_missions([no_due, due_today])
        assert recs[0].mission_id == "MSN-0002"

    def test_confidence_is_valid_range(self):
        missions = [_mission(priority="P1", due_days=5)]
        recs = rank_missions(missions)
        for r in recs:
            assert 0.0 <= r.confidence <= 1.0


# ---------------------------------------------------------------------------
# check_health_constraints
# ---------------------------------------------------------------------------

class TestCheckHealthConstraints:

    def test_no_constraint_when_no_health(self):
        m = _mission(priority="P2", domain="Engineering")
        result = check_health_constraints(m, None)
        assert result is None

    def test_no_constraint_when_workload_normal(self):
        m = _mission(priority="P2", domain="Engineering")
        result = check_health_constraints(m, _health(workload="normal"))
        assert result is None

    def test_constraint_returned_for_heavy_domain_reduced_workload(self):
        m = _mission(priority="P2", domain="Engineering")
        result = check_health_constraints(m, _health(workload="reduced"))
        assert result is not None
        assert isinstance(result, str)

    def test_p0_not_constrained_even_in_reduced_workload(self):
        m = _mission(priority="P0", domain="Engineering")
        result = check_health_constraints(m, _health(workload="reduced"))
        assert result is None

    def test_p3_gets_defer_suggestion(self):
        m = _mission(priority="P3", domain="Operations")
        result = check_health_constraints(m, _health(workload="reduced"))
        assert result is not None
        assert "defer" in result.lower() or "capacity" in result.lower()


# ---------------------------------------------------------------------------
# deadline_urgency
# ---------------------------------------------------------------------------

class TestDeadlineUrgency:

    def test_overdue(self):
        assert _deadline_urgency(str(date.today() - timedelta(days=1))) == "high"

    def test_today(self):
        assert _deadline_urgency(str(date.today())) == "high"

    def test_this_week(self):
        assert _deadline_urgency(str(date.today() + timedelta(days=5))) == "medium"

    def test_next_month(self):
        assert _deadline_urgency(str(date.today() + timedelta(days=30))) == "low"

    def test_no_due_date(self):
        assert _deadline_urgency(None) == "none"


# ---------------------------------------------------------------------------
# generate_recommendation_package
# ---------------------------------------------------------------------------

class TestGenerateRecommendationPackage:

    def test_returns_package(self):
        missions = [_mission(priority="P1", due_days=3)]
        pkg = generate_recommendation_package(missions)
        assert pkg.assembled_at is not None
        assert len(pkg.recommendations) >= 1

    def test_health_constraints_applied_flag(self):
        missions = [_mission(priority="P2", domain="Engineering")]
        pkg = generate_recommendation_package(missions, health_context=_health(workload="reduced"))
        assert pkg.health_constraints_applied is True

    def test_health_constraints_not_applied_when_normal(self):
        missions = [_mission(priority="P2")]
        pkg = generate_recommendation_package(missions, health_context=_health(workload="normal"))
        assert pkg.health_constraints_applied is False

    def test_serialisable(self):
        import json
        missions = [_mission(priority="P1", due_days=2)]
        pkg = generate_recommendation_package(missions)
        d = pkg.to_dict()
        json.dumps(d, default=str)  # Should not raise


# ---------------------------------------------------------------------------
# explain_recommendation
# ---------------------------------------------------------------------------

class TestExplainRecommendation:

    def test_explanation_includes_mission_id(self):
        rec = Recommendation(
            priority_rank=1,
            mission_id="MSN-0001",
            title="Test Mission",
            reason="P1 priority; due in 2 days",
            deadline_urgency="high",
            confidence=0.85,
            next_action="Continue implementation",
        )
        text = explain_recommendation(rec)
        assert "MSN-0001" in text
        assert "PRIORITY #1" in text

    def test_explanation_includes_blockers(self):
        rec = Recommendation(
            priority_rank=1,
            mission_id="MSN-0001",
            title="Test",
            reason="Reason",
            blockers=["Waiting on external dependency"],
            deadline_urgency="medium",
            confidence=0.7,
            next_action="Resolve blocker",
        )
        text = explain_recommendation(rec)
        assert "Waiting on external dependency" in text
