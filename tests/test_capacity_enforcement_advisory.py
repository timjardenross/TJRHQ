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


# --- Number One work queue and the context-service path (Codex P1 on this PR) ---

QUEUE_MISSIONS = [
    {"id": "M-P0", "mission_id": "M-P0", "title": "Critical thing", "priority": "P0", "status": "ACTIVE"},
    {"id": "M-P1", "mission_id": "M-P1", "title": "Important thing", "priority": "P1", "status": "ACTIVE"},
    {"id": "M-P2", "mission_id": "M-P2", "title": "Nice thing", "priority": "P2", "status": "ACTIVE"},
]


def _number_one():
    import importlib

    return importlib.import_module("core.coordination.number_one").NumberOne()


@pytest.mark.parametrize("status", ["Red", "Amber"])
def test_number_one_queue_defers_nothing_in_advisory(advisory, status):
    out = _number_one().get_health_adjusted_queue(QUEUE_MISSIONS, status)
    text = " ".join([n["capacity_note"] for n in out["queue"]] + [out["advisory"]] + out["recommended_focus"])
    assert "DEFERRED" not in text and "P0 only" not in text and "P0 missions only" not in text
    assert "advisory" in out["advisory"].lower()
    assert out["capacity_status"] == status  # still reported
    assert len(out["recommended_focus"]) == 3  # normal focus, not narrowed to P0/P1


def test_number_one_queue_red_still_defers_when_enforcing(enforce):
    out = _number_one().get_health_adjusted_queue(QUEUE_MISSIONS, "Red")
    notes = {n["priority"]: n["capacity_note"] for n in out["queue"]}
    assert notes["P2"].startswith("DEFERRED") and notes["P0"].startswith("CRITICAL")
    assert out["recommended_focus"] == ["Critical thing"]


def test_number_one_queue_amber_still_narrows_when_enforcing(enforce):
    out = _number_one().get_health_adjusted_queue(QUEUE_MISSIONS, "Amber")
    assert out["recommended_focus"] == ["Critical thing", "Important thing"]


def test_context_service_queue_path_is_advisory(advisory, monkeypatch):
    """The live path the mission workbench uses: context_service -> NumberOne.get_health_adjusted_queue."""
    import importlib.util
    import sys
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "core" / "context-assembly" / "context_service.py"
    spec = importlib.util.spec_from_file_location("context_service_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "_load_live_missions_for_number_one", lambda: list(QUEUE_MISSIONS))
    monkeypatch.setattr(mod, "_capacity_status_for_today", lambda: "Red")
    import engineering_handoff_reader  # imported by the function from core/coordination

    monkeypatch.setattr(engineering_handoff_reader, "load_engineering_handoffs", list)
    out = mod._http_health_adjusted_queue()
    blob = str(out)
    assert "DEFERRED" not in blob and "P0 only" not in blob


# --- Recommendation engine: ranking and notes ---

def _rec():
    import importlib

    return importlib.import_module("core.coordination.recommendation_engine")


def test_recommendation_note_is_not_a_defer_instruction_in_advisory(advisory):
    rec = _rec()

    class Health:
        capacity_status = "Red"
        workload_constraint = "normal"

    note = rec.check_health_constraints({"priority": "P3", "domain": "engineering"}, Health())
    assert note and "Defer" not in note and "nothing is deferred" in note


def test_recommendation_note_still_says_defer_when_enforcing(enforce):
    rec = _rec()

    class Health:
        capacity_status = "Red"
        workload_constraint = "normal"

    assert rec.check_health_constraints({"priority": "P3", "domain": "x"}, Health()).startswith("Defer")


# --- Consumers found by G7 review of PR #434 (attention state, command bus, Remember) ---


def _attention_note(status):
    from core.coordination.attention_state import (
        AttentionCategory,
        _capacity_note_and_category,
    )

    return _capacity_note_and_category(AttentionCategory.IMPORTANT_NOT_IMMEDIATE, False, False, status)


def test_attention_state_red_does_not_demote_in_advisory(advisory):
    from core.coordination.attention_state import AttentionCategory

    category, note = _attention_note("Red")
    assert category == AttentionCategory.IMPORTANT_NOT_IMMEDIATE
    assert note.startswith("Advisory")


def test_attention_state_red_still_demotes_when_enforcing(enforce):
    from core.coordination.attention_state import AttentionCategory

    category, note = _attention_note("Red")
    assert category == AttentionCategory.CAN_WAIT
    assert note.startswith("DEFERRED")


def _run_high_escalation(capacity):
    import sqlite3
    from unittest import mock

    import core.coordination.command_bus as cb

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cb._init_db(conn)
    brief = {"escalations": [{"escalation_type": "BLOCKED_P0", "mission_id": "MSN-1",
                              "level": "HIGH", "reason": "r", "recommendation": ""}]}
    with mock.patch.object(cb, "_get_number_one_brief", return_value=brief), \
         mock.patch.object(cb, "_capacity_status", return_value=capacity), \
         mock.patch.object(cb, "_in_number_one_quiet_hours", return_value=False), \
         mock.patch.object(cb, "_route", return_value=True) as route:
        cb._rule_number_one_escalations(conn, client=None)
    return route


def test_command_bus_high_on_red_is_sent_in_advisory(advisory):
    _run_high_escalation("Red").assert_called_once()


def test_command_bus_high_on_red_is_held_when_enforcing(enforce):
    _run_high_escalation("Red").assert_not_called()


def _remember_limit(status):
    import importlib.util
    import pathlib

    path = pathlib.Path(__file__).resolve().parents[1] / "core" / "context-assembly" / "context_service.py"
    spec = importlib.util.spec_from_file_location("context_service_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod._remember_capture_limit(status)


def test_remember_limit_is_common_in_advisory(advisory):
    assert {_remember_limit(s) for s in ("Red", "Amber", "Green", "Unknown", None)} == {30}


def test_remember_limit_follows_band_when_enforcing(enforce):
    assert (_remember_limit("Red"), _remember_limit("Amber"), _remember_limit("Green")) == (3, 10, 30)
