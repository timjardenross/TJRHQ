"""Cognitive Core Regression Harness (MSN-0329 Phase 4, Objective 6).

Representative scenarios, re-run as prompts/thresholds/domain coverage
change over time, to catch quality regressions before they reach real
Captain-facing output. Covers the deterministic layers only (Operational
State Model, Understanding Engine) — the LLM layers (Insight/Reasoning
Engines) are exercised for their parsing/validation/graceful-degradation
behaviour (already covered in-module, per MSN-0329 Phase 2/3's own
validation), not re-asserted here, since their actual output is
non-deterministic by nature and not a fair regression target.

No pytest available in this environment (confirmed, matches every other
test file's own workaround this platform uses) — every scenario is a
plain function returning True/False, runnable directly via
`python3 tests/test_cognitive_core_regression.py`.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.platform.attention_engine import evaluate_batch
from core.platform.operational_state_model import assemble_operational_state
from core.platform.understanding_engine import build_understanding

_NOW = datetime.now(timezone.utc)


def _ev(i, dom, et, metrics=None, missions=None, hours_ago=0, importance=70, confidence=70):
    return {
        "event_id": str(i), "domain": dom, "event_type": et,
        "occurred_at": (_NOW - timedelta(hours=hours_ago)).isoformat(),
        "metrics": metrics or {}, "linked_missions": missions or [],
        "linked_entities": [], "linked_documents": [],
        "importance": importance, "confidence": confidence, "relevance": 70,
        "recommended_action": None,
    }


def scenario_phase3_real_world() -> bool:
    """Pins the real Phase 3 production finding: 16 events, one domain,
    all unscored (importance/confidence=None) — must still produce
    exactly one `aggregation` relationship via the Attention Engine's
    own grouping, and zero relationships/conflicts of any other kind."""
    events = [
        {"event_id": str(i), "domain": "operational-resilience-intelligence",
         "event_type": "intelligence.source.failed",
         "occurred_at": (_NOW - timedelta(hours=i)).isoformat(),
         "metrics": {}, "linked_missions": [], "linked_entities": [], "linked_documents": [],
         "importance": None, "confidence": None, "relevance": None, "recommended_action": None}
        for i in range(16)
    ]
    decisions = evaluate_batch(events)
    state = assemble_operational_state(events, window_hours=24)
    graph = build_understanding(state, events, decisions)

    kinds = {r.kind for r in graph.relationships}
    return (
        kinds == {"aggregation"}
        and len(graph.conflicts) == 0
        and len(graph.emerging_situations) == 1
    )


def scenario_cross_domain_mission_sequence() -> bool:
    """A mission rejected, then its delivery build finishes shortly
    after — must produce shared_mission + temporal_sequence, correctly
    ordered by real timestamps."""
    events = [
        _ev(1, "mission-lifecycle", "mission.rejected", missions=["MSN-TEST"], hours_ago=4),
        _ev(2, "engineering-delivery", "delivery.build_finished", missions=["MSN-TEST"], hours_ago=3),
    ]
    decisions = evaluate_batch(events)
    state = assemble_operational_state(events, window_hours=24)
    graph = build_understanding(state, events, decisions)

    kinds = {r.kind for r in graph.relationships}
    seq = next((r for r in graph.relationships if r.kind == "temporal_sequence"), None)
    return (
        {"shared_mission", "temporal_sequence"}.issubset(kinds)
        and seq is not None
        and seq.event_ids == ["1", "2"]  # rejection (older) before build (newer)
    )


def scenario_capacity_vs_demand_conflict() -> bool:
    """High delivery risk ratio + high mission load — must trigger the
    conflict, with real threshold values pinned."""
    events = [
        _ev(1, "engineering-delivery", "delivery.risk_snapshot",
            metrics={"high_risk_count": 6, "open_count": 15}, hours_ago=1),
        _ev(2, "mission-lifecycle", "mission.load_snapshot",
            metrics={"open_count": 22}, hours_ago=1),
    ]
    decisions = evaluate_batch(events)
    state = assemble_operational_state(events, window_hours=24)
    graph = build_understanding(state, events, decisions)
    return any(c.rule == "capacity_vs_demand" for c in graph.conflicts)


def scenario_quiet_period_no_false_positives() -> bool:
    """A quiet period: 2 low-importance, unrelated, single-domain
    events. Must produce ZERO relationships and ZERO conflicts — a
    quiet period should look quiet, not manufacture a finding."""
    events = [
        _ev(1, "health-intelligence", "health.readiness.scored", importance=30, confidence=40, hours_ago=1),
        _ev(2, "content-intelligence", "comms.content_recorded", importance=25, confidence=50, hours_ago=2),
    ]
    decisions = evaluate_batch(events)
    state = assemble_operational_state(events, window_hours=24)
    graph = build_understanding(state, events, decisions)
    return len(graph.relationships) == 0 and len(graph.conflicts) == 0


def scenario_unrelated_events_no_cross_contamination() -> bool:
    """Multiple domains active, but NO shared missions between them —
    must produce zero shared_mission/temporal_sequence relationships.
    Activity existing is not the same as activity being connected."""
    events = [
        _ev(1, "mission-lifecycle", "mission.status_changed", missions=["MSN-A"], hours_ago=1),
        _ev(2, "engineering-delivery", "delivery.build_finished", missions=["MSN-B"], hours_ago=1),
        _ev(3, "strategic-planning", "strategy.focus_snapshot", metrics={"orphan_count": 0}, hours_ago=1),
    ]
    decisions = evaluate_batch(events)
    state = assemble_operational_state(events, window_hours=24)
    graph = build_understanding(state, events, decisions)
    return not any(r.kind in ("shared_mission", "temporal_sequence") for r in graph.relationships)


def scenario_metrics_recency_merge() -> bool:
    """An older mission.load_snapshot event must not override a newer
    one's value in the Operational State Model's aggregated_metrics."""
    events = [
        _ev(1, "mission-lifecycle", "mission.load_snapshot", metrics={"open_count": 40}, hours_ago=5),
        _ev(2, "mission-lifecycle", "mission.load_snapshot", metrics={"open_count": 42}, hours_ago=1),
    ]
    state = assemble_operational_state(events, window_hours=24)
    return state.domains["Missions"].aggregated_metrics.get("open_count") == 42


SCENARIOS = {
    "phase3_real_world": scenario_phase3_real_world,
    "cross_domain_mission_sequence": scenario_cross_domain_mission_sequence,
    "capacity_vs_demand_conflict": scenario_capacity_vs_demand_conflict,
    "quiet_period_no_false_positives": scenario_quiet_period_no_false_positives,
    "unrelated_events_no_cross_contamination": scenario_unrelated_events_no_cross_contamination,
    "metrics_recency_merge": scenario_metrics_recency_merge,
}


def run_all() -> bool:
    all_passed = True
    for name, fn in SCENARIOS.items():
        try:
            passed = fn()
        except Exception as exc:
            passed = False
            print(f"  ERROR  {name}: {exc}")
        else:
            print(f"  {'PASS' if passed else 'FAIL'}  {name}")
        all_passed = all_passed and passed
    return all_passed


if __name__ == "__main__":
    ok = run_all()
    print()
    print("ALL SCENARIOS PASSED" if ok else "SOME SCENARIOS FAILED")
    sys.exit(0 if ok else 1)
