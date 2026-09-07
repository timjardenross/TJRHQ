"""
Unit tests for intelligence/brief/morning_cycle.py — bounded degraded-cutoff
readiness policy (Briefs canonical uplift, Sections 4-6).
"""

import os
import sys
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.brief import morning_cycle

_TZ = ZoneInfo("Australia/Melbourne")


def _at(hour: int, minute: int, day: int = 6) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=_TZ)


class TestMorningCycleReadiness(unittest.TestCase):

    def test_not_ready_before_cutoff_with_no_heartbeat(self):
        with patch("core.platform.heartbeat.supabase_get", return_value=[]):
            status = morning_cycle.get_status(_at(6, 10))
        self.assertFalse(status.ready)
        self.assertFalse(status.cutoff_reached)
        self.assertFalse(status.degraded)

    def test_ready_when_heartbeat_ok(self):
        with patch("core.platform.heartbeat.supabase_get",
                    return_value=[{"status": "ok", "checked_at": "2026-09-06T06:05:00+10:00"}]):
            status = morning_cycle.get_status(_at(6, 10))
        self.assertTrue(status.ready)
        self.assertFalse(status.degraded)
        self.assertEqual(status.collection_status, "ok")

    def test_degraded_when_heartbeat_failed(self):
        with patch("core.platform.heartbeat.supabase_get",
                    return_value=[{"status": "failed", "checked_at": "2026-09-06T06:05:00+10:00"}]):
            status = morning_cycle.get_status(_at(6, 10))
        self.assertTrue(status.ready)
        self.assertTrue(status.degraded)

    def test_proceeds_degraded_past_cutoff_with_no_heartbeat(self):
        """One missing source/job must never block the brief indefinitely."""
        with patch("core.platform.heartbeat.supabase_get", return_value=[]):
            status = morning_cycle.get_status(_at(morning_cycle.MORNING_CUTOFF_HOUR,
                                                   morning_cycle.MORNING_CUTOFF_MINUTE + 1))
        self.assertTrue(status.ready)
        self.assertTrue(status.cutoff_reached)
        self.assertTrue(status.degraded)
        self.assertIsNotNone(status.reason)

    def test_supabase_outage_degrades_at_cutoff_instead_of_hanging(self):
        with patch("core.platform.heartbeat.supabase_get", side_effect=RuntimeError("down")):
            status = morning_cycle.get_status(_at(morning_cycle.MORNING_CUTOFF_HOUR,
                                                   morning_cycle.MORNING_CUTOFF_MINUTE + 1))
        self.assertTrue(status.ready)
        self.assertTrue(status.degraded)

    def test_supabase_outage_before_cutoff_waits_not_degrades(self):
        with patch("core.platform.heartbeat.supabase_get", side_effect=RuntimeError("down")):
            status = morning_cycle.get_status(_at(6, 5))
        self.assertFalse(status.ready)
        self.assertFalse(status.degraded)

    def test_cycle_id_is_local_calendar_date(self):
        self.assertEqual(morning_cycle.cycle_id_for(_at(6, 30)), "2026-09-06")

    def test_in_morning_window(self):
        self.assertTrue(morning_cycle.in_morning_window(_at(6, 0)))
        self.assertFalse(morning_cycle.in_morning_window(_at(14, 0)))


if __name__ == "__main__":
    unittest.main()
