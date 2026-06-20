"""Tests for WP7 — Human Systems proactive scheduler + delivery.

Covers:
  - delivery.deliver(): dry-run / no-client / no-channel return rendered text
    without sending; live path calls chat_postMessage with the rendered body.
  - run_job(): generates, records to memory, and delivers each job; threshold
    job skips cleanly when there is no actionable signal.
  - on-demand `/hs push` preview reuses the runner and stays language-compliant.

No live network: Supabase fetch, Slack client, and memory writes are mocked.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

from lib.human_systems import delivery, push, safety  # noqa: E402
import human_systems_scheduler as hss  # noqa: E402
import commands.human_systems as hs  # noqa: E402

GOOD = {
    "log_date": "2026-06-20", "energy": "high", "mood": "positive",
    "nervous_system_state": "calm", "sleep_hours": 8.0, "sleep_quality": "good",
    "pain_score": 2, "captain_capacity_rating": "Green",
}
HARD = {
    "log_date": "2026-06-20", "energy": "low", "mood": "low",
    "nervous_system_state": "dysregulated", "sleep_hours": 4.5,
    "sleep_quality": "poor", "pain_score": 8, "captain_capacity_rating": "Red",
}


# ── Delivery ──────────────────────────────────────────────────────────────────

class TestDelivery(unittest.TestCase):
    def _msg(self):
        return push.morning_readiness_pulse(GOOD)

    def test_dry_run_renders_without_sending(self):
        r = delivery.deliver(self._msg(), client=MagicMock(), channel="U1", dry_run=True)
        self.assertFalse(r.delivered)
        self.assertTrue(r.dry_run)
        self.assertIn("Morning Readiness", r.text)

    def test_no_client_is_graceful(self):
        r = delivery.deliver(self._msg(), client=None, channel="U1")
        self.assertFalse(r.delivered)
        self.assertEqual(r.error, "no_client")

    def test_no_channel_is_graceful(self):
        r = delivery.deliver(self._msg(), client=MagicMock(), channel=None)
        self.assertFalse(r.delivered)
        self.assertEqual(r.error, "no_channel")

    def test_live_path_posts_rendered_text(self):
        client = MagicMock()
        r = delivery.deliver(self._msg(), client=client, channel="UCAPTAIN")
        self.assertTrue(r.delivered)
        client.chat_postMessage.assert_called_once()
        _, kwargs = client.chat_postMessage.call_args
        self.assertEqual(kwargs["channel"], "UCAPTAIN")
        self.assertIn("Morning Readiness", kwargs["text"])

    def test_delivery_failure_captured_not_raised(self):
        client = MagicMock()
        client.chat_postMessage.side_effect = RuntimeError("slack down")
        r = delivery.deliver(self._msg(), client=client, channel="U1")
        self.assertFalse(r.delivered)
        self.assertIn("slack down", r.error or "")


# ── Runner ────────────────────────────────────────────────────────────────────

class TestRunner(unittest.TestCase):
    def setUp(self):
        self._mem = patch.object(hss.memory, "record_recommendation", lambda **k: True)
        self._mem.start()

    def tearDown(self):
        self._mem.stop()

    def test_each_job_dry_runs_and_is_compliant(self):
        rows = {"morning": [HARD], "evening": [HARD],
                "weekly": [GOOD, HARD], "degradation": [HARD]}
        for job in hss.JOBS:
            with patch.object(hss, "_fetch_rows", return_value=rows[job]):
                report = hss.run_job(job, dry_run=True)
            if report.get("skipped"):
                continue
            self.assertIn("text", report)
            self.assertEqual(safety.check_language(report["text"]), [], f"job {job}")

    def test_degradation_skips_when_steady(self):
        steady = [dict(GOOD, log_date=f"2026-06-1{i}") for i in range(4)]
        with patch.object(hss, "_fetch_rows", return_value=steady):
            report = hss.run_job("degradation", dry_run=True)
        self.assertTrue(report.get("skipped"))
        self.assertEqual(report["reason"], "no_actionable_signal")

    def test_degradation_fires_on_decline(self):
        rows = [
            dict(GOOD, log_date="2026-06-14"), dict(GOOD, log_date="2026-06-15"),
            dict(HARD, log_date="2026-06-18"), dict(HARD, log_date="2026-06-19"),
        ]
        with patch.object(hss, "_fetch_rows", return_value=rows):
            report = hss.run_job("degradation", dry_run=True)
        self.assertFalse(report.get("skipped"))
        self.assertIn("Capacity Degradation", report["text"])

    def test_run_job_delivers_via_client(self):
        client = MagicMock()
        with patch.object(hss, "_fetch_rows", return_value=[GOOD]):
            report = hss.run_job("morning", client=client, channel="UCAP")
        self.assertTrue(report["delivered"])
        client.chat_postMessage.assert_called_once()

    def test_run_job_records_to_memory(self):
        calls = []
        with patch.object(hss.memory, "record_recommendation",
                          lambda **k: calls.append(k) or True):
            with patch.object(hss, "_fetch_rows", return_value=[GOOD]):
                hss.run_job("weekly", dry_run=True)
        self.assertTrue(calls)
        self.assertEqual(calls[0]["source"], "scheduler")

    def test_unknown_job_handled(self):
        self.assertIn("error", hss.run_job("bogus", dry_run=True))

    def test_morning_includes_highest_leverage(self):
        # HSF-002: the morning pulse now carries the single highest-leverage action.
        with patch.object(hss, "_fetch_rows", return_value=[HARD]):
            report = hss.run_job("morning", dry_run=True)
        self.assertIn("Highest-leverage today", report["text"])

    def test_run_all_covers_every_job(self):
        with patch.object(hss, "_fetch_rows", return_value=[GOOD, HARD]):
            reports = hss.run_all(dry_run=True)
        self.assertEqual({r["job"] for r in reports}, set(hss.JOBS))


# ── On-demand /hs push preview ────────────────────────────────────────────────

class TestPushPreview(unittest.TestCase):
    def test_push_preview_renders(self):
        with patch.object(hs, "_fetch_rows", return_value=[HARD]):
            out = hs.handle_human_systems("push morning")
        self.assertIn("Morning Readiness", out)
        self.assertEqual(safety.check_language(out), [])

    def test_push_preview_skip_message(self):
        steady = [dict(GOOD, log_date=f"2026-06-1{i}") for i in range(4)]
        with patch.object(hs, "_fetch_rows", return_value=steady):
            out = hs.handle_human_systems("push degradation")
        self.assertIn("no actionable signal", out.lower())

    def test_push_preview_usage(self):
        out = hs.handle_human_systems("push")
        self.assertIn("preview", out.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
