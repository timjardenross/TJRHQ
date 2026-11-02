"""Mission 1 (USS-TJR-MSN-1) fix: daily_ops_cycle.py:_step_human_systems
called `CapacityGate.evaluate(score, status, [])` with a hardcoded empty
mission list instead of the real `missions` list already in scope in
run_daily_cycle() — so RED capacity's `defer_mission` actions and AMBER's
`limit_missions` active-count check silently never fired against a real
mission, in any environment, ever (only the list-independent
trigger_recovery/notify/flag_for_number_one actions worked). Verifies the
fix threads the real list through, and that Green/Amber/Red + P0 protection
behave per D-055 once it does.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from platform_runtime.lib import daily_ops_cycle


@pytest.fixture(autouse=True)
def _no_real_command_memory_writes():
    """CapacityGate._log_gate_decision() writes to the real, shared
    .id-counters.json DEC sequence on every Red/Amber evaluation -- not
    something a unit test should touch. See mission_id_minting_drift
    memory: sentinel-value / real-counter hygiene."""
    import id_registry

    with mock.patch.object(id_registry, "next_id", return_value="DEC-TEST"):
        yield


MISSIONS = [
    {"id": "MSN-0001", "priority": "P0", "status": "active"},
    {"id": "MSN-0002", "priority": "P1", "status": "active"},
    {"id": "MSN-0003", "priority": "P2", "status": "designed"},
]


def _run_human_systems_step(missions, score, status):
    ctx = daily_ops_cycle.CycleContext()
    with mock.patch(
        "core.health.capacity_score.capacity_zone_from_checkin",
        return_value=(score, status),
    ):
        daily_ops_cycle._step_human_systems({"whatever": True}, missions, ctx)
    return ctx


class TestCapacityGateNeverHoldsWorkBack:
    """Owner decision 2026-11-02: Red / Amber produce one advisory notice and no
    defer / limit / recovery actions, whatever the mission list looks like."""

    @pytest.mark.parametrize("status,score", [("Red", 5), ("Amber", 50)])
    def test_only_an_advisory_notice_is_emitted(self, status, score):
        ctx = _run_human_systems_step(MISSIONS, score, status)
        types = {a["type"] for a in ctx.capacity_actions}
        assert types <= {"notify"}
        assert not types & {"defer_mission", "limit_missions", "trigger_recovery"}

    def test_amber_over_the_old_cap_is_not_limited(self):
        many_active = [{"id": f"MSN-{i:04d}", "priority": "P2", "status": "active"} for i in range(5)]
        ctx = _run_human_systems_step(many_active, 50, "Amber")
        assert not any(a["type"] == "limit_missions" for a in ctx.capacity_actions)

    def test_green_emits_no_gate_actions(self):
        ctx = _run_human_systems_step(MISSIONS, 90, "Green")
        assert ctx.capacity_actions == []

    def test_no_mission_is_mutated_by_the_gate(self):
        before = [dict(m) for m in MISSIONS]
        _run_human_systems_step(MISSIONS, 5, "Red")
        assert MISSIONS == before

    def test_empty_mission_list_still_degrades_safely(self):
        ctx = _run_human_systems_step([], 5, "Red")
        assert not any(a["type"] == "defer_mission" for a in ctx.capacity_actions)


class TestRunDailyCyclePlumbing:
    def test_run_daily_cycle_passes_its_missions_arg_into_the_gate(self):
        """End-to-end: the `missions` argument to run_daily_cycle() must be
        the same list the capacity gate evaluates -- not a separate/empty
        one constructed inside the human-systems step."""
        captured = {}

        def fake_evaluate(self, score, status, mission_queue, **kwargs):
            captured["mission_queue"] = mission_queue
            return []

        with mock.patch(
            "core.health.capacity_score.capacity_zone_from_checkin",
            return_value=(5, "Red"),
        ), mock.patch.object(
            daily_ops_cycle, "log", daily_ops_cycle.log
        ):
            from core.health.capacity_gate import CapacityGate
            with mock.patch.object(CapacityGate, "evaluate", fake_evaluate):
                daily_ops_cycle.run_daily_cycle(MISSIONS, {"whatever": True})

        assert captured["mission_queue"] is MISSIONS
