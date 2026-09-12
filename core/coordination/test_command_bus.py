"""Unit tests for command_bus.py's Number One escalation rule (USS-TJR-MSN-0362
candidate A, 2026-09-08) — the one rule in this file that had no coverage at
all before this. Covers severity filtering, dedup/cooldown, quiet-hours
suppression (delayed, never dropped), resolve-when-gone, and graceful
degradation on a brief-fetch failure.

Uses an in-memory sqlite connection (command_bus's rule functions take a
plain sqlite3.Connection) so nothing here touches outputs/command_bus.db.
"""

from __future__ import annotations

import sqlite3
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import core.coordination.command_bus as cb


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cb._init_db(conn)
    return conn


def _escalation(level="CRITICAL", etype="PR_CI_FAILING", mission_id="USS-TJR-MSN-9001",
                reason="CI is red", recommendation="Fix it"):
    return {
        "escalation_type": etype, "mission_id": mission_id, "level": level,
        "reason": reason, "recommendation": recommendation, "data": {},
    }


class TestInQuietHours(unittest.TestCase):
    def _at(self, hour: int) -> bool:
        fixed = datetime(2026, 9, 8, hour, 0, tzinfo=ZoneInfo("Australia/Brisbane"))
        with patch.object(cb, "datetime") as mock_dt:
            mock_dt.now.return_value = fixed
            return cb._in_number_one_quiet_hours()

    def test_default_window_is_7pm_to_7am(self):
        self.assertTrue(self._at(19))    # 7pm — quiet starts
        self.assertTrue(self._at(23))
        self.assertTrue(self._at(0))
        self.assertTrue(self._at(6))
        self.assertFalse(self._at(7))    # 7am — quiet ends
        self.assertFalse(self._at(12))
        self.assertFalse(self._at(18))


class TestNumberOneEscalationRule(unittest.TestCase):
    def setUp(self):
        self.conn = _conn()
        self._not_quiet = patch.object(cb, "_in_number_one_quiet_hours", return_value=False)
        self._not_quiet.start()

    def tearDown(self):
        self._not_quiet.stop()
        self.conn.close()

    def test_critical_escalation_is_pushed(self):
        brief = {"escalations": [_escalation(level="CRITICAL")]}
        with patch.object(cb, "_get_number_one_brief", return_value=brief), \
             patch.object(cb, "_route", return_value=True) as route:
            cb._rule_number_one_escalations(self.conn)
        route.assert_called_once()
        severity, tg = route.call_args[0]
        self.assertEqual(severity, "CRITICAL")
        self.assertIn("PR_CI_FAILING", tg)
        self.assertIn("USS-TJR-MSN-9001", tg)
        self.assertIn("Fix it", tg)

    def test_high_escalation_is_pushed(self):
        brief = {"escalations": [_escalation(level="HIGH")]}
        with patch.object(cb, "_get_number_one_brief", return_value=brief), \
             patch.object(cb, "_route", return_value=True) as route:
            cb._rule_number_one_escalations(self.conn)
        route.assert_called_once()
        self.assertEqual(route.call_args[0][0], "HIGH")

    def test_medium_escalation_is_not_pushed(self):
        brief = {"escalations": [_escalation(level="MEDIUM")]}
        with patch.object(cb, "_get_number_one_brief", return_value=brief), \
             patch.object(cb, "_route") as route:
            cb._rule_number_one_escalations(self.conn)
        route.assert_not_called()

    def test_lowercase_level_from_number_one_enum_still_matches(self):
        # esc.level.value in number_one.py's EscalationLevel enum is lowercase
        # ("critical"/"high"/"medium") — the rule must not be case-sensitive.
        brief = {"escalations": [_escalation(level="critical")]}
        with patch.object(cb, "_get_number_one_brief", return_value=brief), \
             patch.object(cb, "_route", return_value=True) as route:
            cb._rule_number_one_escalations(self.conn)
        route.assert_called_once()

    def test_repeat_within_cooldown_is_not_re_pushed(self):
        brief = {"escalations": [_escalation()]}
        with patch.object(cb, "_get_number_one_brief", return_value=brief), \
             patch.object(cb, "_route", return_value=True) as route:
            cb._rule_number_one_escalations(self.conn)
            cb._rule_number_one_escalations(self.conn)
        route.assert_called_once()

    def test_quiet_hours_suppresses_but_does_not_drop(self):
        brief = {"escalations": [_escalation()]}
        self._not_quiet.stop()
        try:
            with patch.object(cb, "_in_number_one_quiet_hours", return_value=True), \
                 patch.object(cb, "_get_number_one_brief", return_value=brief), \
                 patch.object(cb, "_route", return_value=True) as route:
                cb._rule_number_one_escalations(self.conn)
            route.assert_not_called()

            with patch.object(cb, "_in_number_one_quiet_hours", return_value=False), \
                 patch.object(cb, "_get_number_one_brief", return_value=brief), \
                 patch.object(cb, "_route", return_value=True) as route:
                cb._rule_number_one_escalations(self.conn)
            route.assert_called_once()
        finally:
            self._not_quiet = patch.object(cb, "_in_number_one_quiet_hours", return_value=False)
            self._not_quiet.start()

    def test_resolved_when_escalation_no_longer_present(self):
        brief = {"escalations": [_escalation()]}
        with patch.object(cb, "_get_number_one_brief", return_value=brief), \
             patch.object(cb, "_route", return_value=True):
            cb._rule_number_one_escalations(self.conn)

        key = "number_one_escalation:PR_CI_FAILING:USS-TJR-MSN-9001"
        row = self.conn.execute("SELECT resolved_at FROM bus_events WHERE event_key=?", (key,)).fetchone()
        self.assertIsNone(row["resolved_at"])

        with patch.object(cb, "_get_number_one_brief", return_value={"escalations": []}), \
             patch.object(cb, "_route", return_value=True):
            cb._rule_number_one_escalations(self.conn)

        row = self.conn.execute("SELECT resolved_at FROM bus_events WHERE event_key=?", (key,)).fetchone()
        self.assertIsNotNone(row["resolved_at"])

    def test_brief_fetch_failure_degrades_gracefully(self):
        with patch.object(cb, "_get_number_one_brief", return_value=None), \
             patch.object(cb, "_route") as route:
            cb._rule_number_one_escalations(self.conn)  # must not raise
        route.assert_not_called()

    def test_get_number_one_brief_never_raises_on_import_failure(self):
        with patch.dict(sys.modules, {"context_service": None}):
            result = cb._get_number_one_brief()
        # None (import failed) or a real dict if the module happened to
        # already be importable in this process — either way, no exception.
        self.assertTrue(result is None or isinstance(result, dict))


if __name__ == "__main__":
    unittest.main()
