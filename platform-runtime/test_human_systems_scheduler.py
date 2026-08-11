"""Tests for WP7 — Human Systems proactive scheduler + delivery.

Covers:
  - delivery.deliver(): dry-run / no-client / no-channel return rendered text
    without sending; live path calls chat_postMessage with the rendered body.
  - run_job(): generates, records to memory, and delivers each job; threshold
    job skips cleanly when there is no actionable signal.
  - on-demand `/hs push` preview reuses the runner and stays language-compliant.

No live network: Supabase fetch, Slack client, and memory writes are mocked.

The "morning" job (and anything that previews it, e.g. `/hs push morning`)
calls commands.brief.build_brief() for real, which — independently of any
of the mocks above — polls core_events, may classify an INTERRUPT_NOW item,
and if so calls core.platform.interrupt_dispatcher.dispatch_interrupt_now(),
which sends a genuine Telegram push and writes a genuine core_events row via
event_bus.publish_event(). This bit the Captain in production: a routine
review run of this file fired several real "Protect capacity today" alerts
to his phone (2026-08-11). TestRunner/TestPushPreview.setUp patch these two
boundary functions module-wide so no test in this file can ever repeat that,
regardless of which code path inside build_brief() reaches them.
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
import core.platform.event_bus as event_bus  # noqa: E402
import core.platform.interrupt_dispatcher as interrupt_dispatcher  # noqa: E402

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


class TestTelegramDelivery(unittest.TestCase):
    _ENV = {"TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "555"}

    def _msg(self):
        return push.morning_readiness_pulse(GOOD)

    def test_fans_out_to_both_bots(self):
        client = MagicMock()
        with patch.dict("os.environ", self._ENV), \
             patch.object(delivery, "_send_telegram", return_value=(True, None)) as tg:
            r = delivery.deliver(self._msg(), client=client, channel="UCAP")
        self.assertTrue(r.delivered)
        client.chat_postMessage.assert_called_once()
        tg.assert_called_once()
        self.assertEqual(r.channel, "slack+telegram")

    def test_telegram_only_when_no_slack(self):
        with patch.dict("os.environ", self._ENV), \
             patch.object(delivery, "_send_telegram", return_value=(True, None)):
            r = delivery.deliver(self._msg(), client=None, channel=None)
        self.assertTrue(r.delivered)
        self.assertEqual(r.channel, "telegram")
        self.assertIsNone(r.error)

    def test_dry_run_lists_both_surfaces(self):
        with patch.dict("os.environ", self._ENV):
            r = delivery.deliver(self._msg(), client=MagicMock(), channel="UCAP", dry_run=True)
        self.assertFalse(r.delivered)
        self.assertTrue(r.dry_run)
        self.assertIn("telegram", r.channel)

    def test_to_telegram_strips_bold_and_truncates(self):
        self.assertNotIn("*", delivery._to_telegram("*bold* and _italic_"))
        long = "x" * 5000
        self.assertLessEqual(len(delivery._to_telegram(long)), delivery._TELEGRAM_MAX)


# ── Runner ────────────────────────────────────────────────────────────────────

class TestRunner(unittest.TestCase):
    def setUp(self):
        self._mem = patch.object(hss.memory, "record_recommendation", lambda **k: True)
        self._mem.start()
        # See module docstring: the "morning" job reaches these two real
        # side-effecting boundaries via commands.brief.build_brief(), not via
        # any mock above. Never let a test in this file send a real Telegram
        # push or write a real core_events row.
        self._publish = patch.object(event_bus, "publish_event", lambda *a, **k: None)
        self._publish.start()
        self._interrupt = patch.object(
            interrupt_dispatcher, "dispatch_interrupt_now", lambda *a, **k: []
        )
        self._interrupt.start()

    def tearDown(self):
        self._mem.stop()
        self._publish.stop()
        self._interrupt.stop()

    def test_each_job_dry_runs_and_is_compliant(self):
        rows = {"morning": [HARD], "evening": [HARD],
                "weekly": [GOOD, HARD], "degradation": [HARD]}
        for job in hss.JOBS:
            with patch.object(hss, "_fetch_rows", return_value=rows.get(job, [GOOD])):
                report = hss.run_job(job, dry_run=True)
            if report.get("skipped"):
                continue
            self.assertIn("text", report)
            self.assertEqual(safety.check_language(report["text"]), [], f"job {job}")

    def test_comms_weekly_delivers_when_opportunities_exist(self):
        from lib.comms import opportunities as copp
        from lib.comms.opportunities import build_opportunity
        opp = build_opportunity("mission", ref="M1", title="Resilience shakedown",
                                body="incident recovery and continuity lessons")
        with patch.object(copp, "gather_opportunities", return_value=[opp]):
            report = hss.run_job("comms_weekly", dry_run=True)
        self.assertFalse(report.get("skipped"))
        self.assertIn("Weekly Thought Leadership Brief", report["text"])

    def test_comms_weekly_skips_when_no_opportunities(self):
        from lib.comms import opportunities as copp
        with patch.object(copp, "gather_opportunities", return_value=[]):
            report = hss.run_job("comms_weekly", dry_run=True)
        self.assertTrue(report.get("skipped"))

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

    def test_morning_is_daily_operating_picture(self):
        # MSN-XO-002: the morning push is now the unified Daily Operating Picture,
        # which carries the highest-leverage action under "Decision".
        with patch.object(hss, "_fetch_rows", return_value=[HARD]):
            report = hss.run_job("morning", dry_run=True)
        self.assertIn("Daily Operating Picture", report["text"])
        self.assertIn("Decision", report["text"])

    def test_run_all_covers_every_job(self):
        with patch.object(hss, "_fetch_rows", return_value=[GOOD, HARD]):
            reports = hss.run_all(dry_run=True)
        self.assertEqual({r["job"] for r in reports}, set(hss.JOBS))


# ── On-demand /hs push preview ────────────────────────────────────────────────

class TestPushPreview(unittest.TestCase):
    def setUp(self):
        # `/hs push morning` runs the same real build_brief() path as
        # TestRunner — see module docstring.
        self._publish = patch.object(event_bus, "publish_event", lambda *a, **k: None)
        self._publish.start()
        self._interrupt = patch.object(
            interrupt_dispatcher, "dispatch_interrupt_now", lambda *a, **k: []
        )
        self._interrupt.start()

    def tearDown(self):
        self._publish.stop()
        self._interrupt.stop()

    def test_push_preview_renders(self):
        with patch.object(hs, "_fetch_rows", return_value=[HARD]):
            out = hs.handle_human_systems("push morning")
        # MSN-XO-002: morning preview is now the Daily Operating Picture.
        self.assertIn("Daily Operating Picture", out)
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
