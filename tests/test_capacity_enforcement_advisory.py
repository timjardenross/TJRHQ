"""Capacity gating is advisory by default (owner decision 2026-10-18): capacity is still read and
reported, but nothing is trimmed, deferred or blocked. CAPACITY_ENFORCEMENT=enforce restores D-055."""

from datetime import datetime, timezone

import pytest

from core.health import capacity_enforcement as ce
from core.health.capacity_gate import CapacityGate
from intelligence.adhd import follow_through_engine as fte

MISSIONS = [
    {"id": "M-1", "priority": "P2", "status": "active"},
    {"id": "M-2", "priority": "P1", "status": "active"},
    {"id": "M-3", "priority": "P3", "status": "active"},
]


@pytest.fixture
def advisory(monkeypatch):
    monkeypatch.delenv("CAPACITY_ENFORCEMENT", raising=False)


@pytest.fixture
def enforce(monkeypatch):
    monkeypatch.setenv("CAPACITY_ENFORCEMENT", "enforce")


def test_default_mode_is_advisory(advisory):
    assert ce.capacity_enforcement_mode() == "advisory"
    assert ce.enforcing() is False


def test_unknown_value_falls_back_to_advisory(monkeypatch):
    monkeypatch.setenv("CAPACITY_ENFORCEMENT", "banana")
    assert ce.enforcing() is False


@pytest.mark.parametrize("status", ["Red", "Amber"])
def test_gate_defers_and_limits_nothing_in_advisory(advisory, status):
    actions = CapacityGate().evaluate(20, status, MISSIONS)
    assert [a.action_type for a in actions] == ["notify"]
    assert "advisory" in actions[0].reason
    assert not any(a.action_type in ("defer_mission", "limit_missions", "trigger_recovery") for a in actions)


def test_gate_still_defers_when_enforcing(enforce):
    types = [a.action_type for a in CapacityGate().evaluate(20, "Red", MISSIONS)]
    assert "defer_mission" in types and "trigger_recovery" in types


def test_governance_statement_says_advisory(advisory):
    assert "Advisory only" in CapacityGate().get_governance_statement("Red")


def test_follow_through_never_trimmed_in_advisory(advisory):
    now = datetime(2026, 10, 18, 9, 0, tzinfo=timezone.utc)
    tasks = [{"id": "t1", "follow_through_mode": "gentle", "due_date": None}, {"id": "t2", "follow_through_mode": "normal", "due_date": None}]
    for status in ("Red", "Amber", "Unknown"):
        assert fte._apply_capacity_gate(list(tasks), status, now) == tasks


def test_follow_through_still_trimmed_when_enforcing(enforce):
    now = datetime(2026, 10, 18, 9, 0, tzinfo=timezone.utc)
    tasks = [{"id": "t1", "follow_through_mode": "gentle", "due_date": None}, {"id": "t2", "follow_through_mode": "normal", "due_date": None}]
    assert fte._apply_capacity_gate(list(tasks), "Red", now) == []



def _budget_module():
    import importlib.util
    import sys
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "platform-runtime" / "lib" / "improvement" / "budget.py"
    spec = importlib.util.spec_from_file_location("improvement_budget_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(mod)
    return mod


def test_improvement_budget_not_closed_by_red_in_advisory(advisory, monkeypatch):
    mod = _budget_module()
    engine = mod.ImprovementBudgetEngine()
    monkeypatch.setattr(engine, "_count_active_improvement_missions", lambda: 0)
    monkeypatch.setattr(engine, "_log_budget_state", lambda b: None)
    budget = engine.get_budget("Red")
    assert budget.capacity_status == "Red"  # still reported
    assert budget.can_create is True


def test_improvement_budget_still_closed_by_red_when_enforcing(enforce, monkeypatch):
    mod = _budget_module()
    engine = mod.ImprovementBudgetEngine()
    monkeypatch.setattr(engine, "_count_active_improvement_missions", lambda: 0)
    monkeypatch.setattr(engine, "_log_budget_state", lambda b: None)
    assert engine.get_budget("Red").can_create is False
