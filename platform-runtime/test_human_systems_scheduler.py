#!/usr/bin/env python3
"""Tests for WP7 — Human Systems proactive scheduler + delivery.

Covers:
  - delivery.deliver(): dry-run / no-client / no-channel return rendered text
    without sending; live path calls chat_postMessage with the rendered body.
  - run_job(): generates, records to memory, and delivers each job; threshold
    job skips cleanly when there is no actionable signal.
  - on-demand `/hs push` preview reuses the runner and stays language-compliant.

No live network: Supabase fetch, Telegram sends, and memory writes are mocked.

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
from typing import ClassVar
from unittest.mock import patch

_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

import commands.human_systems as hs
import human_systems_scheduler as hss
from lib.human_systems import delivery, push, safety

from core.platform import (
    event_bus,
    interrupt_dispatcher,
)

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
    _ENV: ClassVar[dict] = {"TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "555"}

    def _msg(self):
        return push.morning_readiness_pulse(GOOD)

    def test_dry_run_renders_without_sending(self):
        with patch.dict("os.environ", self._ENV):
            r = delivery.deliver(self._msg(), dry_run=True)
        self.assertFalse(r.delivered)
        self.assertTrue(r.dry_run)
        self.assertIn("Morning Readiness", r.text)

    def test_no_telegram_config_is_graceful(self):
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": "", "HUMAN_SYSTEMS_TELEGRAM_CHAT": ""}, clear=False):
            r = delivery.deliver(self._msg())
        self.assertFalse(r.delivered)
        self.assertEqual(r.error, "no_telegram_config")

    def test_live_path_sends_rendered_text(self):
        with patch.dict("os.environ", self._ENV), \
             patch.object(delivery, "_send_telegram", return_value=(True, None)) as tg:
            r = delivery.deliver(self._msg())
        self.assertTrue(r.delivered)
        self.assertEqual(r.channel, "telegram")
        tg.assert_called_once()
        args, _ = tg.call_args
        self.assertIn("Morning Readiness", args[0])

    def test_delivery_failure_captured_not_raised(self):
        with patch.dict("os.environ", self._ENV), \
             patch.object(delivery, "_send_telegram", return_value=(False, "telegram down")):
            r = delivery.deliver(self._msg())
        self.assertFalse(r.delivered)
        self.assertIn("telegram down", r.error or "")

    def test_dry_run_names_telegram_surface(self):
        with patch.dict("os.environ", self._ENV):
            r = delivery.deliver(self._msg(), dry_run=True)
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

    def test_run_job_delivers_via_telegram(self):
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "555"}), \
             patch.object(hss.delivery, "_send_telegram", return_value=(True, None)) as tg, \
             patch.object(hss, "_fetch_rows", return_value=[GOOD]):
            report = hss.run_job("morning")
        self.assertTrue(report["delivered"])
        tg.assert_called_once()

    def test_run_job_records_to_memory(self):
        calls = []
        with patch.object(hss.memory, "record_recommendation",
                          lambda **k: calls.append(k) or True), patch.object(hss, "_fetch_rows", return_value=[GOOD]):
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


class TestDisabledJobs(unittest.TestCase):
    """HS_DISABLED_JOBS holds individual daemon jobs without a code change."""

    def test_default_runs_every_job(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("HS_DISABLED_JOBS", None)
            self.assertEqual(hss._enabled_jobs(), hss.JOBS)

    def test_listed_jobs_are_held_case_and_space_insensitive(self):
        with patch.dict("os.environ", {"HS_DISABLED_JOBS": " Evening , midday "}):
            enabled = hss._enabled_jobs()
        self.assertNotIn("evening", enabled)
        self.assertNotIn("midday", enabled)
        for j in ("morning", "weekly", "degradation", "comms_weekly", "eod"):
            self.assertIn(j, enabled)

    def test_unknown_name_is_ignored_and_warned(self):
        with patch.dict("os.environ", {"HS_DISABLED_JOBS": "eveningg"}), \
                self.assertLogs("human-systems-scheduler", level="WARNING") as cm:
            enabled = hss._enabled_jobs()
        self.assertEqual(enabled, hss.JOBS)  # typo must not disable anything
        self.assertTrue(any("unknown" in m for m in cm.output))

    def test_manual_runs_ignore_the_setting(self):
        with patch.dict("os.environ", {"HS_DISABLED_JOBS": "evening"}):
            self.assertIn("evening", hss.JOBS)  # run_all()/--job iterate JOBS, not _enabled_jobs()


class TestScheduleTimezone(unittest.TestCase):
    """Jobs fire at their cron time in HS_SCHEDULE_TZ, not in UTC.

    Regression: the pgqueuer daemon registered each plain cron, which pgqueuer
    evaluates in UTC, so "evening" (0 20 * * *) fired at 07:00 Sydney and
    "eod" (30 17 * * 1-5) at 04:30 Sydney.
    """

    def setUp(self):
        import os
        from datetime import datetime
        from zoneinfo import ZoneInfo
        self.datetime, self.ZoneInfo = datetime, ZoneInfo
        self.syd = ZoneInfo("Australia/Sydney")
        self.utc = ZoneInfo("UTC")
        self._env = patch.dict("os.environ", {}, clear=False)
        self._env.start()
        for k in ("HS_SCHEDULE_TZ", "HS_MORNING_CRON", "HS_EVENING_CRON", "HS_EOD_CRON"):
            os.environ.pop(k, None)

    def tearDown(self):
        self._env.stop()

    def _due(self, y, m, d, hh, mm, tz):
        return hss._jobs_due(self.datetime(y, m, d, hh, mm, tzinfo=tz), hss.JOBS)

    def test_morning_is_0700_local_in_daylight_saving(self):
        # 2026-11-03 is AEDT (UTC+11)
        self.assertEqual(self._due(2026, 11, 3, 7, 0, self.syd), ["morning"])

    def test_0700_utc_is_not_morning(self):
        # 07:00 UTC is 18:00 Sydney: the old daemon fired the morning job here
        self.assertEqual(self._due(2026, 11, 3, 7, 0, self.utc), [])
        self.assertEqual(
            hss._jobs_due(self.datetime(2026, 11, 3, 7, 0, tzinfo=self.utc).astimezone(self.syd), hss.JOBS), [])

    def test_morning_is_0700_local_in_standard_time(self):
        # 2026-06-02 is AEST (UTC+10): same wall-clock time, different UTC instant
        self.assertEqual(self._due(2026, 6, 2, 7, 0, self.syd), ["morning"])

    def test_evening_and_midday_times(self):
        self.assertEqual(self._due(2026, 11, 3, 20, 0, self.syd), ["evening"])
        self.assertEqual(self._due(2026, 11, 3, 12, 0, self.syd), ["midday"])
        self.assertEqual(self._due(2026, 11, 3, 15, 0, self.syd), ["degradation"])

    def test_eod_is_weekdays_only_in_local_time(self):
        self.assertEqual(self._due(2026, 11, 6, 17, 30, self.syd), ["eod"])   # Friday
        self.assertEqual(self._due(2026, 11, 7, 17, 30, self.syd), [])        # Saturday

    def test_weekly_and_comms_are_monday_local(self):
        self.assertEqual(self._due(2026, 11, 2, 8, 0, self.syd), ["weekly"])        # Monday
        self.assertEqual(self._due(2026, 11, 2, 8, 30, self.syd), ["comms_weekly"])
        self.assertEqual(self._due(2026, 11, 3, 8, 0, self.syd), [])                # Tuesday

    def test_nothing_due_off_the_minute(self):
        self.assertEqual(self._due(2026, 11, 3, 7, 1, self.syd), [])
        self.assertEqual(self._due(2026, 11, 3, 6, 59, self.syd), [])

    def test_seconds_are_ignored(self):
        t = self.datetime(2026, 11, 3, 7, 0, 41, tzinfo=self.syd)
        self.assertEqual(hss._jobs_due(t, hss.JOBS), ["morning"])

    def test_cron_env_override_is_respected(self):
        with patch.dict("os.environ", {"HS_MORNING_CRON": "15 6 * * *"}):
            self.assertEqual(self._due(2026, 11, 3, 6, 15, self.syd), ["morning"])
            self.assertEqual(self._due(2026, 11, 3, 7, 0, self.syd), [])

    def test_timezone_defaults_to_sydney_and_can_be_overridden(self):
        self.assertEqual(str(hss._timezone()), "Australia/Sydney")
        with patch.dict("os.environ", {"HS_SCHEDULE_TZ": "Australia/Brisbane"}):
            self.assertEqual(str(hss._timezone()), "Australia/Brisbane")
            # Brisbane has no daylight saving: 07:00 local in January is 21:00 UTC the day before
            brisbane = hss._timezone()
            self.assertEqual(hss._jobs_due(self.datetime(2027, 1, 15, 7, 0, tzinfo=brisbane), hss.JOBS), ["morning"])

    def test_unknown_timezone_fails_loudly_not_silently_utc(self):
        with patch.dict("os.environ", {"HS_SCHEDULE_TZ": "Not/AZone"}):
            with self.assertRaises(Exception):
                hss._timezone()

    def test_a_job_starts_once_per_local_minute(self):
        started, fired = [], {}
        t = self.datetime(2026, 11, 3, 7, 0, 5, tzinfo=self.syd)
        self.assertEqual(hss._fire_due(t, hss.JOBS, fired, started.append), ["morning"])
        self.assertEqual(hss._fire_due(t.replace(second=40), hss.JOBS, fired, started.append), [])
        self.assertEqual(started, ["morning"])
        # the next day it fires again
        nxt = self.datetime(2026, 11, 4, 7, 0, 5, tzinfo=self.syd)
        self.assertEqual(hss._fire_due(nxt, hss.JOBS, fired, started.append), ["morning"])

    def test_held_jobs_are_not_started(self):
        started = []
        with patch.dict("os.environ", {"HS_DISABLED_JOBS": "evening"}):
            hss._fire_due(self.datetime(2026, 11, 3, 20, 0, tzinfo=self.syd), hss._enabled_jobs(), {}, started.append)
        self.assertEqual(started, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
