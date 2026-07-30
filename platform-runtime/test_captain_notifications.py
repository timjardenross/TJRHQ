"""
Tests for captain_notifications — Proactive Captain Notification Framework
"""

import os
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from captain_notifications import (
    NotificationConfig,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    SEVERITY_ALERT,
    SEVERITY_CRITICAL,
    severity_header,
    max_severity,
    _parse_mission_open_date,
    format_mission_escalation_batch,
    format_forgotten_decisions,
    build_work_queue,
    health_nudge_text,
    mission_close_lesson_warning,
)


class TestSeverityModel(unittest.TestCase):

    def test_severity_header_includes_emoji_and_label(self):
        h = severity_header(SEVERITY_ALERT, "Test Title")
        self.assertIn("Alert", h)
        self.assertIn("Test Title", h)
        self.assertIn(":rotating_light:", h)

    def test_severity_header_critical(self):
        h = severity_header(SEVERITY_CRITICAL, "Immediate")
        self.assertIn(":sos:", h)
        self.assertIn("Critical", h)

    def test_max_severity_escalates(self):
        self.assertEqual(max_severity(SEVERITY_WARNING, SEVERITY_ALERT), SEVERITY_ALERT)
        self.assertEqual(max_severity(SEVERITY_ALERT, SEVERITY_WARNING), SEVERITY_ALERT)
        self.assertEqual(max_severity(None, SEVERITY_INFO), SEVERITY_INFO)
        self.assertEqual(max_severity(SEVERITY_CRITICAL, SEVERITY_WARNING), SEVERITY_CRITICAL)


class TestNotificationConfig(unittest.TestCase):

    def _env(self, **kwargs):
        return patch.dict(os.environ, kwargs, clear=False)

    def test_defaults(self):
        with self._env():
            cfg = NotificationConfig()
        self.assertEqual(cfg.level, "WARNING")
        self.assertEqual(cfg.quiet_start, 22)
        self.assertEqual(cfg.quiet_end, 7)
        self.assertFalse(cfg.weekend)
        self.assertTrue(cfg.daily_brief)
        self.assertTrue(cfg.mission_escalations)
        self.assertTrue(cfg.health_reminders)
        self.assertTrue(cfg.forgotten_decisions)
        self.assertEqual(cfg.mission_open_days, 3)
        self.assertEqual(cfg.mission_stale_hours, 48)
        self.assertEqual(cfg.decision_stale_days, 7)

    def test_custom_env(self):
        with self._env(
            NOTIFICATION_LEVEL="CRITICAL",
            MISSION_OPEN_DAYS="5",
            WEEKEND_NOTIFICATIONS="true",
        ):
            cfg = NotificationConfig()
        self.assertEqual(cfg.level, "CRITICAL")
        self.assertEqual(cfg.mission_open_days, 5)
        self.assertTrue(cfg.weekend)

    def test_should_send_respects_minimum_level(self):
        with self._env(NOTIFICATION_LEVEL="ALERT"):
            cfg = NotificationConfig()
        # Quiet hours are 22-07; simulate midday so quiet hours don't interfere
        with patch("captain_notifications.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 16, 10, 0)  # Monday 10:00
            self.assertFalse(cfg.should_send(SEVERITY_INFO))
            self.assertFalse(cfg.should_send(SEVERITY_WARNING))
            self.assertTrue(cfg.should_send(SEVERITY_ALERT))
            self.assertTrue(cfg.should_send(SEVERITY_CRITICAL))

    def test_quiet_hours_block_non_critical(self):
        with self._env(NOTIFICATION_LEVEL="INFO"):
            cfg = NotificationConfig()
        with patch("captain_notifications.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 16, 23, 0)  # 23:00 — quiet
            self.assertFalse(cfg.should_send(SEVERITY_ALERT))
            self.assertTrue(cfg.should_send(SEVERITY_CRITICAL))  # CRITICAL breaks quiet

    def test_weekend_suppression(self):
        with self._env(NOTIFICATION_LEVEL="INFO", WEEKEND_NOTIFICATIONS="false"):
            cfg = NotificationConfig()
        with patch("captain_notifications.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 14, 10, 0)  # Saturday 10:00
            self.assertFalse(cfg.should_send(SEVERITY_INFO, is_routine=True))
            # Non-routine should still pass
            self.assertTrue(cfg.should_send(SEVERITY_INFO, is_routine=False))


class TestParseMissionOpenDate(unittest.TestCase):

    def test_standard_id_format(self):
        d = _parse_mission_open_date("M-20260607-132532")
        self.assertEqual(d, date(2026, 6, 7))

    def test_named_mission_id(self):
        d = _parse_mission_open_date("M-20260613-INTELLIGENCE-LAYER-ASSESSMENT")
        self.assertEqual(d, date(2026, 6, 13))

    def test_fallback_to_timestamp_string(self):
        d = _parse_mission_open_date("USS-TJR-MSN-0001", "2026-06-01 09:00")
        self.assertEqual(d, date(2026, 6, 1))

    def test_no_date_returns_none(self):
        d = _parse_mission_open_date("SOME-ID-WITH-NO-DATE")
        self.assertIsNone(d)


class TestFormatMissionEscalationBatch(unittest.TestCase):

    def test_empty_returns_empty(self):
        self.assertEqual(format_mission_escalation_batch([]), "")

    def test_formats_escalations(self):
        escalations = [
            {
                "id": "M-20260607-132532",
                "title": "Test Mission",
                "status": "BLOCKED",
                "severity": SEVERITY_ALERT,
                "reasons": ["Mission is BLOCKED"],
            }
        ]
        msg = format_mission_escalation_batch(escalations)
        self.assertIn("M-20260607-132532", msg)
        self.assertIn("BLOCKED", msg)
        self.assertIn("Alert", msg)
        self.assertIn(":rotating_light:", msg)

    def test_multiple_severities(self):
        escalations = [
            {"id": "M-CRIT", "title": "Crit", "status": "BLOCKED", "severity": SEVERITY_CRITICAL, "reasons": ["BLOCKED"]},
            {"id": "M-WARN", "title": "Warn", "status": "Active", "severity": SEVERITY_WARNING, "reasons": ["Open 5 days"]},
        ]
        msg = format_mission_escalation_batch(escalations)
        self.assertIn("M-CRIT", msg)
        self.assertIn("M-WARN", msg)


class TestFormatForgottenDecisions(unittest.TestCase):

    def test_empty_returns_empty(self):
        self.assertEqual(format_forgotten_decisions([]), "")

    def test_formats_governance_decision(self):
        items = [{
            "id": "D-007",
            "title": "Adopt new auth pattern",
            "date": "2026-06-01",
            "status": "PROPOSED",
            "age_days": 12,
            "type": "governance_decision",
        }]
        msg = format_forgotten_decisions(items)
        self.assertIn("D-007", msg)
        self.assertIn("12 days", msg)
        self.assertIn("Governance Attention Required", msg)
        self.assertIn(":scales:", msg)

    def test_formats_adr(self):
        items = [{
            "id": "ADR-0007",
            "title": "Use Postgres",
            "date": "2026-05-20",
            "status": "Awaiting Validation",
            "age_days": 24,
            "type": "adr",
        }]
        msg = format_forgotten_decisions(items)
        self.assertIn("ADR-0007", msg)
        self.assertIn(":scroll:", msg)


class TestBuildWorkQueue(unittest.TestCase):

    def test_empty_returns_clear(self):
        msg = build_work_queue([], [])
        self.assertIn("Clear", msg)

    def test_blocked_missions_appear_first(self):
        escalations = [
            {"id": "M-BLOCK", "title": "Blocked Mission", "status": "BLOCKED", "severity": SEVERITY_ALERT, "reasons": ["Mission is BLOCKED"]},
            {"id": "M-WARN", "title": "Warn Mission", "status": "Active", "severity": SEVERITY_WARNING, "reasons": ["Open 3 days"]},
        ]
        msg = build_work_queue(escalations, [])
        idx_block = msg.index("M-BLOCK")
        idx_warn  = msg.index("M-WARN")
        self.assertLess(idx_block, idx_warn)

    def test_max_items_capped(self):
        escalations = [
            {"id": f"M-{i:03d}", "title": f"Mission {i}", "status": "Active",
             "severity": SEVERITY_WARNING, "reasons": [f"Open {i} days"]}
            for i in range(20)
        ]
        msg = build_work_queue(escalations, [], max_items=5)
        # Should only have 5 numbered items
        item_count = sum(1 for line in msg.splitlines() if line.strip() and line.strip()[0].isdigit())
        self.assertLessEqual(item_count, 5)

    def test_shows_item_count_header(self):
        escalations = [
            {"id": "M-001", "title": "T", "status": "BLOCKED", "severity": SEVERITY_ALERT, "reasons": ["BLOCKED"]}
        ]
        msg = build_work_queue(escalations, [])
        self.assertIn("Work Queue", msg)
        self.assertIn("1 item", msg)


class TestHealthNudge(unittest.TestCase):

    def test_nudge_text_contains_command(self):
        msg = health_nudge_text()
        self.assertIn("/health-check", msg)
        self.assertIn("Health Log Reminder", msg)


class TestLessonCaptureWarning(unittest.TestCase):

    def test_returns_warning_when_no_lesson(self):
        with patch("captain_notifications.check_lesson_captured", return_value=False):
            msg = mission_close_lesson_warning("M-20260613-TEST", "Test Mission")
        self.assertIsNotNone(msg)
        self.assertIn("M-20260613-TEST", msg)
        self.assertIn("lesson-capture", msg)

    def test_returns_none_when_lesson_exists(self):
        with patch("captain_notifications.check_lesson_captured", return_value=True):
            msg = mission_close_lesson_warning("M-20260613-TEST", "Test Mission")
        self.assertIsNone(msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
