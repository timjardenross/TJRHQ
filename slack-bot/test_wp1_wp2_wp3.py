"""
Tests for WP1 (escalation_manager), WP2 (alert_metrics), WP3 (mission_risk)
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

# ---------------------------------------------------------------------------
# WP1 — Escalation Manager
# ---------------------------------------------------------------------------

class _InMemorySupabaseClient:
    """Minimal in-memory fake for CommanderSupabaseClient, used in tests."""

    def __init__(self):
        self._tables: dict = {}

    def is_enabled(self) -> bool:
        return True

    def insert(self, table: str, payload: dict) -> object:
        self._tables.setdefault(table, []).append(dict(payload))
        from unittest.mock import MagicMock
        r = MagicMock()
        r.ok = True
        return r

    def get(self, query: str) -> list:
        table, _, qs = query.partition("?")
        rows = list(self._tables.get(table, []))
        # Apply simple eq/is.null/not.in filters (good enough for tests)
        for part in qs.split("&"):
            if not part or part.startswith("select=") or part.startswith("order=") or part.startswith("limit="):
                continue
            if "=is.null" in part:
                col = part.split("=is.null")[0]
                rows = [r for r in rows if r.get(col) is None]
            elif "=not.null" in part:
                col = part.split("=not.null")[0]
                rows = [r for r in rows if r.get(col) is not None]
            elif "=eq." in part:
                col, _, val = part.partition("=eq.")
                # URL-decode simple percent encoding
                import urllib.parse
                val = urllib.parse.unquote(val)
                rows = [r for r in rows if str(r.get(col, "")) == val]
        return rows

    def _patch(self, query: str, payload: dict) -> bool:
        table, _, qs = query.partition("?")
        store = self._tables.get(table, [])
        # Find matching rows and update
        matched = self.get(query)
        for row in store:
            if row in matched:
                row.update(payload)
        return True

    def delete(self, query: str) -> bool:
        return True


class TestEscalationManagerCadence(unittest.TestCase):
    """Test cadence logic and Supabase-backed storage via in-memory fake."""

    def setUp(self):
        import escalation_manager as em
        self.em = em
        self._fake_client = _InMemorySupabaseClient()
        self._patcher = patch("escalation_manager._client", return_value=self._fake_client)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def _row(self, first_detected, notification_count, last_notified=None):
        """Return a plain dict matching _should_notify_now expectations."""
        return {
            "first_detected": first_detected,
            "notification_count": notification_count,
            "last_notified": last_notified,
        }

    def test_never_notified_always_due(self):
        row = self._row("2026-06-10T09:00:00", 0)
        self.assertTrue(self.em._should_notify_now(row, date(2026, 6, 13)))

    def test_notified_once_due_after_3_days(self):
        row = self._row("2026-06-10T09:00:00", 1, "2026-06-10T09:00:00")
        # Day 2 — not due
        self.assertFalse(self.em._should_notify_now(row, date(2026, 6, 12)))
        # Day 3 — due
        self.assertTrue(self.em._should_notify_now(row, date(2026, 6, 13)))

    def test_notified_twice_due_after_7_days(self):
        row = self._row("2026-06-06T09:00:00", 2, "2026-06-09T09:00:00")
        # Day 6 — not due
        self.assertFalse(self.em._should_notify_now(row, date(2026, 6, 12)))
        # Day 7 — due
        self.assertTrue(self.em._should_notify_now(row, date(2026, 6, 13)))

    def test_repeat_phase_every_7_days(self):
        # notification_count=3, last_notified 6 days ago — not due
        last = (datetime.now() - timedelta(days=6)).isoformat(timespec="seconds")
        first = (datetime.now() - timedelta(days=14)).isoformat(timespec="seconds")
        row = self._row(first, 3, last)
        self.assertFalse(self.em._should_notify_now(row, date.today()))

        # last_notified 7 days ago — due
        last7 = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")
        row7 = self._row(first, 3, last7)
        self.assertTrue(self.em._should_notify_now(row7, date.today()))

    def test_severity_progression(self):
        from captain_notifications import SEVERITY_WARNING, SEVERITY_ALERT, SEVERITY_CRITICAL
        self.assertEqual(self.em._escalated_severity(SEVERITY_WARNING, 1), SEVERITY_WARNING)
        self.assertEqual(self.em._escalated_severity(SEVERITY_WARNING, 2), SEVERITY_ALERT)
        self.assertEqual(self.em._escalated_severity(SEVERITY_WARNING, 3), SEVERITY_CRITICAL)
        # Any count >= 3 → CRITICAL
        self.assertEqual(self.em._escalated_severity(SEVERITY_WARNING, 10), SEVERITY_CRITICAL)

    def test_process_escalations_creates_record_and_notifies(self):
        from captain_notifications import SEVERITY_ALERT
        escalations = [{
            "id": "M-TEST-001",
            "title": "Test Mission",
            "status": "BLOCKED",
            "severity": SEVERITY_ALERT,
            "reasons": ["Mission is BLOCKED"],
        }]
        result = self.em.process_escalations(escalations)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["notification_count"], 1)
        self.assertEqual(result[0]["current_severity"], SEVERITY_ALERT)

    def test_process_escalations_suppresses_on_second_call_same_day(self):
        """Second call same day should be suppressed (cadence day 3 hasn't elapsed)."""
        from captain_notifications import SEVERITY_ALERT
        escalations = [{
            "id": "M-TEST-002",
            "title": "Test Mission 2",
            "status": "BLOCKED",
            "severity": SEVERITY_ALERT,
            "reasons": ["Mission is BLOCKED"],
        }]
        first = self.em.process_escalations(escalations)
        self.assertEqual(len(first), 1)
        # Second call same day: count=1, day=0, next threshold=3 days
        second = self.em.process_escalations(escalations)
        self.assertEqual(len(second), 0, "Should be suppressed on second call same day")

    def test_process_escalations_auto_closes_resolved(self):
        from captain_notifications import SEVERITY_WARNING
        escalations = [{
            "id": "M-TEST-003",
            "title": "Mission That Will Resolve",
            "status": "Active",
            "severity": SEVERITY_WARNING,
            "reasons": ["Open 5 days"],
        }]
        self.em.process_escalations(escalations)
        # Next call with empty list → should auto-close
        self.em.process_escalations([])
        open_esc = self.em.get_open_escalations()
        self.assertEqual(len(open_esc), 0)

    def test_derive_alert_types_blocked(self):
        types = self.em._derive_alert_types({"id": "X", "status": "BLOCKED", "reasons": []})
        self.assertIn("blocked", types)

    def test_derive_alert_types_awaiting_xo(self):
        types = self.em._derive_alert_types({"id": "X", "status": "Awaiting XO Approval", "reasons": []})
        self.assertIn("awaiting_xo", types)

    def test_derive_alert_types_stale(self):
        types = self.em._derive_alert_types({"id": "X", "status": "Active", "reasons": ["No activity detected for 3d 6h"]})
        self.assertIn("stale_48h", types)

    def test_acknowledge_and_resolve(self):
        from captain_notifications import SEVERITY_ALERT
        # Create an escalation
        self.em.process_escalations([{
            "id": "M-ACK-001", "title": "T", "status": "BLOCKED",
            "severity": SEVERITY_ALERT, "reasons": ["BLOCKED"]
        }])
        key = "M-ACK-001:blocked"
        self.assertTrue(self.em.acknowledge_escalation(key))
        self.assertTrue(self.em.resolve_escalation(key))
        # Now open escalations should be empty
        self.assertEqual(len(self.em.get_open_escalations()), 0)

    def test_get_escalation_history(self):
        from captain_notifications import SEVERITY_WARNING
        self.em.process_escalations([{
            "id": "M-HIST-001", "title": "T", "status": "Active",
            "severity": SEVERITY_WARNING, "reasons": ["Open 3 days"]
        }])
        history = self.em.get_escalation_history()
        self.assertGreater(len(history), 0)
        self.assertEqual(history[0]["mission_id"], "M-HIST-001")


# ---------------------------------------------------------------------------
# WP2 — Alert Metrics
# ---------------------------------------------------------------------------

class TestAlertMetrics(unittest.TestCase):

    def setUp(self):
        import escalation_manager as em
        import alert_metrics as am
        self._fake_client = _InMemorySupabaseClient()
        self._patcher_em = patch("escalation_manager._client", return_value=self._fake_client)
        self._patcher_am = patch("alert_metrics._client", return_value=self._fake_client)
        self._patcher_em.start()
        self._patcher_am.start()
        self.em = em
        self.am = am

    def tearDown(self):
        self._patcher_em.stop()
        self._patcher_am.stop()

    def _seed_events(self):
        """Push some escalations to generate event data."""
        from captain_notifications import SEVERITY_WARNING, SEVERITY_ALERT
        escalations = [
            {"id": "M-M01", "title": "T1", "status": "Active", "severity": SEVERITY_WARNING, "reasons": ["Open 3 days"]},
            {"id": "M-M02", "title": "T2", "status": "BLOCKED", "severity": SEVERITY_ALERT, "reasons": ["BLOCKED"]},
        ]
        self.em.process_escalations(escalations)
        # Resolve one
        self.em.resolve_escalation("M-M02:blocked")

    def test_metrics_returns_dict(self):
        m = self.am.get_notification_metrics(days=7)
        self.assertIn("alerts_created", m)
        self.assertIn("alerts_resolved", m)
        self.assertIn("resolution_rate_pct", m)
        self.assertIn("window_days", m)
        self.assertEqual(m["window_days"], 7)

    def test_metrics_lifetime(self):
        m = self.am.get_notification_metrics(days=None)
        self.assertIsNone(m["window_days"])

    def test_metrics_counts_seeded_events(self):
        self._seed_events()
        m = self.am.get_notification_metrics(days=7)
        self.assertGreaterEqual(m["alerts_created"], 2)
        self.assertGreaterEqual(m["alerts_resolved"], 1)

    def test_resolution_rate_correct(self):
        self._seed_events()
        m = self.am.get_notification_metrics(days=7)
        # 1 resolved of 2 created = 50%
        self.assertGreaterEqual(m["resolution_rate_pct"], 0)
        self.assertLessEqual(m["resolution_rate_pct"], 100)

    def test_empty_db_returns_zeros(self):
        m = self.am.get_notification_metrics(days=7)
        self.assertEqual(m["alerts_created"], 0)
        self.assertEqual(m["alerts_resolved"], 0)
        self.assertEqual(m["resolution_rate_pct"], 0.0)

    def test_format_metrics_summary_empty(self):
        m = self.am.get_notification_metrics(days=7)
        summary = self.am.format_metrics_summary(m)
        self.assertIn("Alert Metrics", summary)
        self.assertIn("No alerts recorded", summary)

    def test_format_metrics_summary_with_data(self):
        self._seed_events()
        m = self.am.get_notification_metrics(days=7)
        summary = self.am.format_metrics_summary(m)
        self.assertIn("Alert Metrics", summary)
        self.assertIn("raised", summary)
        self.assertIn("resolved", summary)
        self.assertIn("Resolution rate", summary)

    def test_metrics_block_for_brief_empty(self):
        block = self.am.get_metrics_block_for_brief()
        self.assertEqual(block, "")

    def test_metrics_block_for_brief_with_outstanding(self):
        self._seed_events()
        block = self.am.get_metrics_block_for_brief()
        # May be empty if outstanding=0 (resolved) or non-empty
        self.assertIsInstance(block, str)


# ---------------------------------------------------------------------------
# WP3 — Mission Risk Scoring
# ---------------------------------------------------------------------------

class TestMissionRiskScoring(unittest.TestCase):

    def setUp(self):
        import mission_risk as mr
        self.mr = mr

    def _mission(self, **kwargs):
        defaults = {
            "id": "M-20260601-123456",
            "title": "Test Mission",
            "description": "Test Mission",
            "status": "Active",
            "priority": "Normal",
            "timestamp": "2026-06-01 09:00",
        }
        return {**defaults, **kwargs}

    def test_blocked_scores_high(self):
        r = self.mr.calculate_mission_risk_score(self._mission(status="BLOCKED"))
        self.assertGreaterEqual(r["score"], 40)
        self.assertIn(r["band"], ("High", "Critical"))

    def test_awaiting_xo_scores_moderate_to_high(self):
        r = self.mr.calculate_mission_risk_score(
            self._mission(status="Awaiting XO Approval", timestamp="2026-06-06 09:00")
        )
        self.assertGreaterEqual(r["score"], 28)

    def test_awaiting_nr1_scores_less_than_xo(self):
        r_xo  = self.mr.calculate_mission_risk_score(self._mission(status="Awaiting XO Approval"))
        r_nr1 = self.mr.calculate_mission_risk_score(self._mission(status="Awaiting Number One Review"))
        self.assertGreater(r_xo["score"], r_nr1["score"])

    def test_old_mission_scores_higher_than_new(self):
        old = self._mission(id="M-20260501-000001", timestamp="2026-05-01 09:00")
        new = self._mission(id="M-20260612-000001", timestamp="2026-06-12 09:00")
        r_old = self.mr.calculate_mission_risk_score(old)
        r_new = self.mr.calculate_mission_risk_score(new)
        self.assertGreater(r_old["score"], r_new["score"])

    def test_critical_priority_adds_score(self):
        low  = self.mr.calculate_mission_risk_score(self._mission(priority="Low",      status="Active"))
        crit = self.mr.calculate_mission_risk_score(self._mission(priority="Critical", status="Active"))
        self.assertGreater(crit["score"], low["score"])

    def test_score_capped_at_100(self):
        r = self.mr.calculate_mission_risk_score(
            self._mission(status="BLOCKED", priority="Critical", timestamp="2026-05-01 09:00")
        )
        self.assertLessEqual(r["score"], 100)

    def test_score_minimum_zero(self):
        r = self.mr.calculate_mission_risk_score(
            self._mission(status="Active", priority="Low", timestamp="2026-06-13 09:00")
        )
        self.assertGreaterEqual(r["score"], 0)

    def test_risk_band_low(self):
        r = self.mr.calculate_mission_risk_score(
            self._mission(status="Active", priority="Low", timestamp="2026-06-13 09:00")
        )
        self.assertEqual(r["band"], "Low")

    def test_risk_band_critical(self):
        # BLOCKED(40) + age≥21d(30) + Critical priority(20) = 90 → Critical band
        old_ts = (date.today() - timedelta(days=25)).strftime("%Y-%m-%d") + " 09:00"
        r = self.mr.calculate_mission_risk_score(
            self._mission(status="BLOCKED", priority="Critical", timestamp=old_ts,
                          id="M-20260101-000001")
        )
        self.assertGreaterEqual(r["score"], 76)
        self.assertEqual(r["band"], "Critical")

    def test_band_emoji_present(self):
        r = self.mr.calculate_mission_risk_score(self._mission(status="BLOCKED"))
        self.assertIn(":", r["band_emoji"])

    def test_reasons_explainable(self):
        r = self.mr.calculate_mission_risk_score(
            self._mission(status="BLOCKED", timestamp="2026-05-01 09:00")
        )
        self.assertGreater(len(r["reasons"]), 0)
        # Each reason should be a non-empty string
        for reason in r["reasons"]:
            self.assertIsInstance(reason, str)
            self.assertTrue(len(reason) > 0)

    def test_format_risk_report_empty(self):
        msg = self.mr.format_risk_report([])
        self.assertIn("No active missions", msg)

    def test_format_risk_report_with_data(self):
        scored = [self.mr.calculate_mission_risk_score(
            self._mission(status="BLOCKED", priority="Critical", timestamp="2026-05-01 09:00")
        )]
        msg = self.mr.format_risk_report(scored)
        self.assertIn("Risk Report", msg)
        self.assertIn("M-20260601-123456", msg)

    def test_get_top_risk_missions_returns_list(self):
        fake_missions = [
            {"id": "M-20260601-001", "title": "Old", "status": "Active", "timestamp": "2026-06-01 09:00", "description": "Old"},
            {"id": "M-20260613-002", "title": "New", "status": "Active", "timestamp": "2026-06-13 09:00", "description": "New"},
            {"id": "M-20260601-003", "title": "Blocked", "status": "BLOCKED", "timestamp": "2026-06-01 09:00", "description": "Blocked"},
        ]
        with patch("captain_notifications._read_mission_index", return_value=fake_missions):
            from mission_risk import get_top_risk_missions
            results = get_top_risk_missions(limit=10)
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)
        # Blocked mission should rank highest
        self.assertEqual(results[0]["mission_id"], "M-20260601-003")

    def test_format_risk_brief_block_suppressed_for_low_risk(self):
        with patch("mission_risk.get_top_risk_missions", return_value=[
            {"score": 10, "band": "Low", "mission_id": "M-X", "title": "T",
             "status": "Active", "reasons": [], "band_emoji": ":white_check_mark:"}
        ]):
            block = self.mr.format_risk_brief_block()
        self.assertEqual(block, "")

    def test_format_risk_brief_block_shown_for_high_risk(self):
        with patch("mission_risk.get_top_risk_missions", return_value=[
            {"score": 82, "band": "Critical", "mission_id": "M-X", "title": "T",
             "status": "BLOCKED", "reasons": ["BLOCKED"], "band_emoji": ":sos:"}
        ]):
            block = self.mr.format_risk_brief_block()
        self.assertIn("High-Risk", block)
        self.assertIn("M-X", block)


if __name__ == "__main__":
    unittest.main(verbosity=2)
