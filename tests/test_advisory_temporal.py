"""Tests for MSN-0095 (temporal/patterns/episodic/signals) and MSN-0096
(triggers/escalation/opportunities/notifications/advisory_health/proactive).

Isolated via conftest (ADVISORY_DATA_ROOT → temp). Runs offline.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ADVISORY = _REPO_ROOT / "core" / "advisory"
if str(_ADVISORY) not in sys.path:
    sys.path.insert(0, str(_ADVISORY))


@pytest.fixture()
def seeded(tmp_path, monkeypatch):
    """Fresh data root with a few advisory records + outcomes for signal tests."""
    monkeypatch.setenv("ADVISORY_DATA_ROOT", str(tmp_path))
    for m in ("outcomes", "timeline", "learning", "calibration", "metrics",
              "patterns", "signals", "episodic", "temporal",
              "escalation", "triggers", "opportunities", "notifications",
              "advisory_health", "proactive", "service"):
        importlib.reload(importlib.import_module(m))
    import service, outcomes
    for q, o in [
        ("Should we ship the hub to mobile?", "success"),
        ("Should we sequence the rollout carefully?", "failure"),
        ("Should we automate the deploys now?", "success"),
        ("Should we expand telegram coverage?", "success"),
    ]:
        r = service.request_advice(q)
        outcomes.record_outcome(r.advisory_id, outcome=o)
    return tmp_path


# --- Timeline / Temporal (WP1) --------------------------------------------

def test_timeline_loads_events():
    import timeline
    importlib.reload(timeline)
    events = timeline.load_events()
    assert isinstance(events, list)
    # repo has decision logs even with empty advisory store
    assert any(e.kind == "decision" for e in events)


def test_temporal_queries_return_narratives():
    import temporal
    importlib.reload(temporal)
    for fn, arg in [("what_changed", None), ("state_at", "2026-06-10")]:
        res = getattr(temporal, fn)(arg) if arg else getattr(temporal, fn)()
        assert "narrative" in res and isinstance(res["narrative"], str)
    assert "narrative" in temporal.what_preceded("Voice Core")
    assert temporal.when_did_begin("Voice Core")["occurrences"] >= 1
    assert "narrative" in temporal.what_happens_next("Slack over Voice Core")


# --- Patterns / Episodic / Signals (WP2-4) --------------------------------

def test_patterns_return_list(seeded):
    import patterns
    importlib.reload(patterns)
    ps = patterns.detect_patterns()
    assert isinstance(ps, list)
    # with 4 closed outcomes, advisor_outcome patterns should exist
    assert any(p.pattern_type == "advisor_outcome" for p in ps)


def test_episodic_resemblance():
    import episodic
    importlib.reload(episodic)
    r = episodic.find_similar_episodes("prioritise Slack over Voice Core")
    assert "resembles" in r and r["resembles"] >= 1
    assert "narrative" in r


def test_signals_return_list(seeded):
    import signals
    importlib.reload(signals)
    ss = signals.emerging_signals()
    assert isinstance(ss, list)


# --- Escalation (WP2 of 0096) ---------------------------------------------

def test_escalation_levels():
    import escalation
    importlib.reload(escalation)
    # cry-wolf guard: single observation can't exceed observation
    assert escalation.classify("concern", frequency=1).level == "observation"
    assert escalation.classify("concern", frequency=2).level == "concern"
    assert escalation.classify("concern", frequency=3).level == "escalation"
    assert escalation.classify("info", frequency=5).level == "observation"


# --- Triggers / Opportunities / Notifications (0096) ----------------------

def test_triggers_evaluate(seeded):
    import triggers
    importlib.reload(triggers)
    trigs = triggers.evaluate_triggers()
    assert isinstance(trigs, list)
    for t in trigs:
        assert t.level in ("observation", "warning", "concern", "escalation")


def test_opportunities_detect(seeded):
    import opportunities
    importlib.reload(opportunities)
    opps = opportunities.detect_opportunities()
    assert isinstance(opps, list)
    # reusable solutions should surface from the seeded successes
    assert any(o.opportunity_type == "reusable_solution" for o in opps)


def test_notifications_route(seeded):
    import triggers, opportunities, notifications
    for m in (triggers, opportunities, notifications):
        importlib.reload(m)
    plan = notifications.route(triggers.evaluate_triggers(), opportunities.detect_opportunities())
    assert set(["interrupt", "daily_brief", "wait", "summary", "note"]).issubset(plan.keys())
    # opportunities are never interruptions
    assert all(it["level"] != "opportunity" for it in plan["interrupt"])


# --- Advisory health (WP5) -------------------------------------------------

def test_advisory_health_unknown_on_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVISORY_DATA_ROOT", str(tmp_path))
    import advisory_health
    importlib.reload(advisory_health)
    h = advisory_health.advisory_health()
    # empty dataset must not claim "degraded"
    assert h["status"] == "unknown"
    assert h["score"] is None


def test_advisory_health_scores_with_data(seeded):
    import advisory_health
    importlib.reload(advisory_health)
    h = advisory_health.advisory_health()
    assert h["status"] in ("healthy", "watch", "degraded")
    assert h["recommendation_quality"] is not None


# --- Proactive orchestrator (0096) ----------------------------------------

def test_proactive_scan_structure(seeded):
    import proactive
    importlib.reload(proactive)
    scan = proactive.proactive_scan()
    for key in ("triggers", "opportunities", "emerging_signals", "notification_plan",
                "advisory_health", "headline", "attention_required", "note"):
        assert key in scan
    # informational only
    assert "actioned" in scan["note"] or "Informational" in scan["note"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
