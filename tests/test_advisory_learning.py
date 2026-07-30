"""Tests for the MSN-0093 advisory learning loop (outcomes, calibration,
learning, metrics, and the XO/Number One consumption adapters).

Isolated: ADVISORY_DATA_ROOT points every test at a fresh temp dir, so the
committed repo is never written to. Runs fully offline.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ADVISORY = _REPO_ROOT / "core" / "advisory"
_COORD = _REPO_ROOT / "core" / "coordination"
for _p in (str(_ADVISORY), str(_COORD)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture()
def fresh(tmp_path, monkeypatch):
    """Point the advisory data store at a temp dir and reload modules."""
    monkeypatch.setenv("ADVISORY_DATA_ROOT", str(tmp_path))
    import outcomes
    importlib.reload(outcomes)
    import learning
    importlib.reload(learning)
    import calibration
    importlib.reload(calibration)
    import metrics
    importlib.reload(metrics)
    import service
    importlib.reload(service)
    return {
        "outcomes": outcomes, "learning": learning,
        "calibration": calibration, "metrics": metrics, "service": service,
        "root": tmp_path,
    }


# ---------------------------------------------------------------------------
# Outcome tracking (WP3)
# ---------------------------------------------------------------------------

def test_record_advisory_and_outcome(fresh):
    svc, oc = fresh["service"], fresh["outcomes"]
    resp = svc.request_advice("Should we ship the advisor hub to mobile?")
    assert resp.advisory_id, "advice should be recorded with an id"

    res = oc.record_outcome(resp.advisory_id, outcome="success", decision_taken="shipped")
    assert res["ok"]
    rec = oc.get_record(resp.advisory_id)
    assert rec["success"] is True
    assert rec["outcome"] == "success"
    events = oc.load_outcomes()
    assert len(events) == 1 and events[0]["advisory_id"] == resp.advisory_id


def test_record_outcome_validation(fresh):
    oc = fresh["outcomes"]
    assert oc.record_outcome("ADV-nope", outcome="banana")["ok"] is False
    assert oc.record_outcome("ADV-missing", outcome="success")["ok"] is False


def test_outcome_last_alias(fresh):
    svc, oc = fresh["service"], fresh["outcomes"]
    resp = svc.request_advice("Should we add an evidence tab?")
    res = oc.record_outcome("last", outcome="partial")
    assert res["ok"] and res["advisory_id"] == resp.advisory_id


# ---------------------------------------------------------------------------
# Learning (WP5)
# ---------------------------------------------------------------------------

def _seed(svc, oc, question, outcome):
    resp = svc.request_advice(question, record=True)
    oc.record_outcome(resp.advisory_id, outcome=outcome)
    return resp


def test_historical_signal_after_outcomes(fresh):
    svc, oc, learn = fresh["service"], fresh["outcomes"], fresh["learning"]
    _seed(svc, oc, "Should we prioritise the mobile rollout plan?", "success")
    _seed(svc, oc, "Should we prioritise the mobile rollout sequencing?", "success")
    sig = learn.historical_signal("Should we prioritise the mobile rollout?")
    assert sig["matched"] >= 2
    assert sig["success_rate"] == 1.0
    assert sig["confidence_delta"] > 0


def test_learning_signal_influences_confidence(fresh):
    svc, oc = fresh["service"], fresh["outcomes"]
    # Two successes on a distinctive topic, then ask again — confidence note set.
    _seed(svc, oc, "Should we adopt zorblax indexing for retrieval?", "success")
    _seed(svc, oc, "Should we adopt zorblax indexing widely?", "success")
    resp = svc.request_advice("Should we adopt zorblax indexing next quarter?")
    assert resp.learning_note, "learning note should be attached once a signal exists"


def test_lesson_reinforcement(fresh):
    svc, oc, learn = fresh["service"], fresh["outcomes"], fresh["learning"]
    r = svc.request_advice("Should we automate the rollout?")
    oc.record_outcome(r.advisory_id, outcome="success")
    reinforcement = learn.lesson_reinforcement()
    # Reinforcement maps lesson_id -> stats; may be empty if no lessons attached,
    # but must be a dict and not raise.
    assert isinstance(reinforcement, dict)


# ---------------------------------------------------------------------------
# Calibration (WP4)
# ---------------------------------------------------------------------------

def test_calibration_report(fresh):
    svc, oc, cal = fresh["service"], fresh["outcomes"], fresh["calibration"]
    _seed(svc, oc, "Mission A sequencing?", "success")
    _seed(svc, oc, "Mission B sequencing?", "failure")
    _seed(svc, oc, "Mission C sequencing?", "success")
    report = cal.calibration_report()
    assert report["total_outcomes"] == 3
    assert report["overall_accuracy"] is not None
    assert "officer_accuracy" in report
    assert "confidence_alignment" in report
    assert "challenge_effectiveness" in report


def test_officer_accuracy_keys(fresh):
    svc, oc, cal = fresh["service"], fresh["outcomes"], fresh["calibration"]
    _seed(svc, oc, "Officer accuracy test mission?", "success")
    acc = cal.officer_accuracy()
    for stats in acc.values():
        assert set(["samples", "accuracy", "sufficient"]).issubset(stats.keys())


# ---------------------------------------------------------------------------
# Metrics (WP7)
# ---------------------------------------------------------------------------

def test_metrics_aggregate(fresh):
    svc, oc, met = fresh["service"], fresh["outcomes"], fresh["metrics"]
    _seed(svc, oc, "Metrics mission one?", "success")
    svc.request_challenge("Metrics mission two challenge?")
    m = met.advisory_metrics()
    assert m["totals"]["advisory_requests"] >= 2
    assert m["totals"]["challenge_requests"] >= 1
    assert "confidence_distribution" in m
    assert "advisor_utilisation" in m
    assert "top_advisors" in m["dashboard"]


# ---------------------------------------------------------------------------
# XO / Number One consumption adapters (WP1/WP2)
# ---------------------------------------------------------------------------

def test_xo_consumer_frames_authority(fresh):
    import xo_advisory
    importlib.reload(xo_advisory)
    out = xo_advisory.request_advisory_review("Should the XO back the hub rollout?")
    assert "XO retains policy and approval authority" in out
    assert "Advisory only" in out


def test_number_one_advisory_support(fresh):
    import number_one_advisory
    importlib.reload(number_one_advisory)
    support = number_one_advisory.advisory_support({
        "mission_id": "MSN-TEST", "title": "Test mission",
        "dependencies": ["MSN-0001"], "blockers": [],
    })
    assert support["mission_id"] == "MSN-TEST"
    assert "risk_analysis" in support
    assert support["dependency_signals"]["dependency_count"] == 1
    assert "Number One decides" in support["authority_note"]


def test_number_one_method_delegates(fresh):
    import number_one
    importlib.reload(number_one)
    n1 = number_one.NumberOne()
    support = n1.request_advisory_support({"mission_id": "MSN-X", "title": "X", "dependencies": [], "blockers": ["stuck"]})
    assert support.get("mission_id") == "MSN-X"
    # Either advisory support (has authority_note) or graceful error — never raises.
    assert "authority_note" in support


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
