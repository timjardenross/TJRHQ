"""Mission 2 (USS-TJR-MSN-2): command_bus.py's Number One escalation
routing had ZERO capacity-awareness -- it pushed CRITICAL/HIGH escalations
to Telegram regardless of the Captain's current capacity, unlike
follow_through_engine.py's already-established Amber/Red pattern.

Fix: CRITICAL always pushes (safety-equivalent to P0 protection elsewhere
in this mission). HIGH on Red defers using the exact same never-drop
mechanism command_bus.py's own quiet-hours gate already relies on --
leaving the event un-notified so _should_notify() is still True next
cycle, not a new persistence/deferred-queue mechanism.

Uses an in-memory sqlite connection (not the real outputs/command_bus.db)
and mocks _get_number_one_brief()/_capacity_status() -- no real network
calls, no real Telegram sends (_route/_notify mocked too).
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

import core.coordination.command_bus as cb


def _memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cb._init_db(conn)
    return conn


def _brief_with(level: str, mission_id: str = "MSN-1") -> dict:
    return {"escalations": [{
        "escalation_type": "BLOCKED_P0", "mission_id": mission_id,
        "level": level, "reason": "test reason", "recommendation": "",
    }]}


class TestCriticalAlwaysPushesRegardlessOfCapacity:
    def test_critical_pushes_on_red_capacity(self):
        conn = _memory_conn()
        with mock.patch.object(cb, "_get_number_one_brief", return_value=_brief_with("CRITICAL")), \
             mock.patch.object(cb, "_capacity_status", return_value="Red"), \
             mock.patch.object(cb, "_in_number_one_quiet_hours", return_value=False), \
             mock.patch.object(cb, "_route", return_value=True) as route_mock:
            cb._rule_number_one_escalations(conn, client=None)
        route_mock.assert_called_once()
        assert route_mock.call_args[0][0] == "CRITICAL"


class TestHighDefersOnRedNotDropped:
    def test_high_does_not_push_on_red_capacity(self):
        conn = _memory_conn()
        with mock.patch.object(cb, "_get_number_one_brief", return_value=_brief_with("HIGH")), \
             mock.patch.object(cb, "_capacity_status", return_value="Red"), \
             mock.patch.object(cb, "_in_number_one_quiet_hours", return_value=False), \
             mock.patch.object(cb, "_route", return_value=True) as route_mock:
            cb._rule_number_one_escalations(conn, client=None)
        route_mock.assert_not_called()

    def test_high_pushes_normally_on_green_capacity(self):
        conn = _memory_conn()
        with mock.patch.object(cb, "_get_number_one_brief", return_value=_brief_with("HIGH")), \
             mock.patch.object(cb, "_capacity_status", return_value="Green"), \
             mock.patch.object(cb, "_in_number_one_quiet_hours", return_value=False), \
             mock.patch.object(cb, "_route", return_value=True) as route_mock:
            cb._rule_number_one_escalations(conn, client=None)
        route_mock.assert_called_once()

    def test_high_pushes_normally_on_unknown_capacity(self):
        """Unknown must not be treated as a reason to suppress -- only a
        confirmed Red defers HIGH (Mission 2's "absence must not imply
        Green" cuts both ways: it also must not manufacture false
        restriction)."""
        conn = _memory_conn()
        with mock.patch.object(cb, "_get_number_one_brief", return_value=_brief_with("HIGH")), \
             mock.patch.object(cb, "_capacity_status", return_value="Unknown"), \
             mock.patch.object(cb, "_in_number_one_quiet_hours", return_value=False), \
             mock.patch.object(cb, "_route", return_value=True) as route_mock:
            cb._rule_number_one_escalations(conn, client=None)
        route_mock.assert_called_once()

    def test_deferred_high_is_not_dropped_and_pushes_once_capacity_recovers(self):
        """The core "deferred, not dropped" guarantee: an escalation
        suppressed on Red must still be eligible to push on a later cycle
        once capacity recovers -- proven by running two cycles against the
        same in-memory event store, exactly as the live watchdog's
        poll loop would."""
        conn = _memory_conn()
        brief = _brief_with("HIGH", mission_id="MSN-RECOVER")

        with mock.patch.object(cb, "_get_number_one_brief", return_value=brief), \
             mock.patch.object(cb, "_capacity_status", return_value="Red"), \
             mock.patch.object(cb, "_in_number_one_quiet_hours", return_value=False), \
             mock.patch.object(cb, "_route", return_value=True) as route_mock:
            cb._rule_number_one_escalations(conn, client=None)  # cycle 1: Red -> deferred
        route_mock.assert_not_called()

        # Confirm it's still an open, un-notified event (not silently lost).
        row = conn.execute(
            "SELECT notif_count, resolved_at FROM bus_events WHERE event_key LIKE 'number_one_escalation:%MSN-RECOVER'"
        ).fetchone()
        assert row is not None
        assert row["notif_count"] == 0
        assert row["resolved_at"] is None

        with mock.patch.object(cb, "_get_number_one_brief", return_value=brief), \
             mock.patch.object(cb, "_capacity_status", return_value="Green"), \
             mock.patch.object(cb, "_in_number_one_quiet_hours", return_value=False), \
             mock.patch.object(cb, "_route", return_value=True) as route_mock:
            cb._rule_number_one_escalations(conn, client=None)  # cycle 2: Green -> pushes
        route_mock.assert_called_once()


class TestCapacityStatusHelper:
    def test_returns_unknown_when_client_is_none(self):
        assert cb._capacity_status(None) == "Unknown"

    def test_returns_unknown_on_supabase_exception(self):
        class RaisingClient:
            def select(self, *a, **kw):
                raise ConnectionError("simulated outage")
        assert cb._capacity_status(RaisingClient()) == "Unknown"

    def test_returns_red_from_a_real_capacity_checkins_row(self):
        class FakeClient:
            def select(self, table, filters=None, limit=None):
                assert table == "capacity_checkins"
                return [{"capacity_state": "red"}]
        assert cb._capacity_status(FakeClient()) == "Red"

    def test_returns_unknown_when_no_todays_row(self):
        class EmptyClient:
            def select(self, table, filters=None, limit=None):
                return []
        assert cb._capacity_status(EmptyClient()) == "Unknown"
