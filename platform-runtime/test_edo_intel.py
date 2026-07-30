"""Tests for MSN-EDO-003 — Autonomous Delivery & Decision Intelligence.

WP1 execution telemetry/backends/rollback; WP2 control tower (risk, throughput,
cycle, bottleneck, capacity); WP3 recommendation package. Pure/offline.
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

from lib.delivery import execution, forecast, lifecycle  # noqa: E402
from lib.human_systems import decision, framework, safety  # noqa: E402
from lib.human_systems.mission_load import MissionLoad, Priority  # noqa: E402
import edo_execute  # noqa: E402
import commands.delivery as dlv  # noqa: E402

MISSION = {"mission_id": "MSN-0099", "title": "Improve dashboard", "status": "Designed",
           "description": "x", "plan_steps": ["a", "b"]}


def _d(n):
    return (date.today() - timedelta(days=n)).isoformat()


def _row(title, state_status, age, **kw):
    r = {"title": title, "status": state_status, "age_days": age,
         "delivery_state": lifecycle.canonical_state(state_status),
         "created_at": _d(age)}
    r.update(kw)
    return r


ROWS = [
    _row("Blocked P0", "Blocked", 6, priority_norm="p0"),
    _row("Stuck plan", "Designed", 12),
    _row("Building eng", "Implemented", 9, task_type_norm="engineering"),
    _row("Review no pr", "Tested", 4, task_type_norm="engineering"),
    _row("Fresh", "Designed", 1),
    _row("Done1", "Closed", 20, cycle_days=2.0, closed_at=_d(3)),
    _row("Done2", "Closed", 30, cycle_days=6.0, closed_at=_d(10)),
]


# ── WP1 ───────────────────────────────────────────────────────────────────────

class TestExecutionTelemetry(unittest.TestCase):
    def test_backend_default_and_validation(self):
        art, reason = execution.prepare_dispatch(MISSION, plan_approved=True)
        self.assertEqual(art["backend"], "claude_code")
        self.assertIn("rollback", art)
        bad, why = execution.prepare_dispatch(MISSION, plan_approved=True, backend="nope")
        self.assertIsNone(bad)
        self.assertIn("unknown execution backend", why)

    def test_rollback_records_event(self):
        calls = []
        with patch.object(edo_execute.data, "record_execution_event",
                          lambda **k: calls.append(k) or True):
            art, _ = edo_execute.run("MSN-0099", plan_approved=True, mission=MISSION)
            plan = edo_execute.rollback(art, reason="ci failed")
        self.assertEqual(plan["delete_branch"], art["branch"])
        self.assertEqual(calls[0]["status"], "rolled_back")

    def test_runner_backend_passthrough(self):
        art, _ = edo_execute.run("MSN-0099", plan_approved=True, mission=MISSION, backend="manual")
        self.assertEqual(art["backend"], "manual")

    def test_main_records_dispatch_event_live(self):
        events = []
        with patch.object(edo_execute.data, "fetch_delivery_rows", return_value=[MISSION]), \
             patch.object(edo_execute.data, "record_transition", lambda **k: True), \
             patch.object(edo_execute.data, "record_execution_event", lambda **k: events.append(k) or True):
            rc = edo_execute.main(["--mission", "MSN-0099", "--plan-approved"])
        self.assertEqual(rc, 0)
        self.assertTrue(any(e["status"] == "dispatched" for e in events))


# ── WP2 ───────────────────────────────────────────────────────────────────────

class TestControlTower(unittest.TestCase):
    def test_blocked_is_high_risk(self):
        r = forecast.delivery_risk(ROWS[0])
        self.assertEqual(r.level, "high")

    def test_fresh_is_low_risk(self):
        r = forecast.delivery_risk(ROWS[4])
        self.assertEqual(r.level, "low")

    def test_no_pr_in_review_adds_risk(self):
        r = forecast.delivery_risk(ROWS[3])
        self.assertTrue(any("no PR" in x for x in r.reasons))

    def test_risk_sorted_desc(self):
        scored = forecast.risk_scored_missions(ROWS)
        self.assertEqual(scored, sorted(scored, key=lambda r: -r.score))
        # closed rows excluded
        self.assertFalse(any("Done" in r.title for r in scored))

    def test_throughput_counts_recent_closures(self):
        tp = forecast.throughput(ROWS, weeks=4)
        self.assertGreaterEqual(sum(tp["per_week_recent_first"]), 1)

    def test_cycle_time_stats(self):
        ct = forecast.cycle_time_stats(ROWS)
        self.assertEqual(ct["count"], 2)
        self.assertEqual(ct["avg"], 4.0)

    def test_bottleneck_constraint(self):
        bn = forecast.bottleneck_forecast(ROWS)
        self.assertIn(bn["constraint"], lifecycle.OPEN_STATES)

    def test_engineering_capacity(self):
        cap = forecast.engineering_capacity(ROWS, wip_limit=1)
        # one engineering in in_progress + one in in_review = 2 WIP > 1
        self.assertEqual(cap["status"], "over")

    def test_control_tower_rollup(self):
        t = forecast.control_tower(ROWS)
        for k in ("throughput", "cycle_time", "bottleneck", "capacity", "top_risks"):
            self.assertIn(k, t)


# ── WP3 ───────────────────────────────────────────────────────────────────────

class TestRecommendationPackage(unittest.TestCase):
    LOAD = MissionLoad(open_count=2, open_titles=["X"],
                       priorities=[Priority("P1", "Memory", "Active")], data_available=True)
    HARD = {"energy": "low", "mood": "low", "nervous_system_state": "dysregulated",
            "sleep_hours": 4.5, "sleep_quality": "poor", "captain_capacity_rating": "Red"}
    GOOD = {"energy": "high", "mood": "positive", "nervous_system_state": "calm",
            "sleep_hours": 8, "sleep_quality": "good", "captain_capacity_rating": "Green"}

    def _snap(self, r):
        return framework.interpret_capacity(r)

    def test_package_has_all_fields(self):
        pkg = decision.recommendation_package(self._snap(self.HARD), self.LOAD, [])
        for attr in ("primary", "confidence", "expected_impact", "opportunity_cost",
                     "recommended_deferral", "strategic_alignment"):
            self.assertTrue(getattr(pkg, attr) not in (None, ""))

    def test_render_contains_sections_and_compliant(self):
        pkg = decision.recommendation_package(self._snap(self.HARD), self.LOAD, [])
        out = pkg.render()
        for label in ("Expected impact", "Opportunity cost", "Recommended deferral", "Strategic alignment"):
            self.assertIn(label, out)
        self.assertEqual(safety.check_language(out), [])

    def test_alignment_strong_for_low_capacity(self):
        pkg = decision.recommendation_package(self._snap(self.HARD), self.LOAD, [])
        self.assertIn("Strong", pkg.strategic_alignment)

    def test_delivery_signal_flows_through(self):
        sig = decision.DeliverySignal(open_missions=4, blocked=2, top_bottleneck="Foo")
        pkg = decision.recommendation_package(self._snap(self.GOOD), self.LOAD, [], delivery=sig)
        self.assertEqual(safety.check_language(pkg.render()), [])

    def test_backward_compatible_highest_leverage(self):
        rec = decision.highest_leverage(self._snap(self.GOOD), self.LOAD, [])
        self.assertTrue(rec.primary)  # still returns a Recommendation


# ── Commands ──────────────────────────────────────────────────────────────────

class TestDeliveryCommands(unittest.TestCase):
    def setUp(self):
        self._p = patch.object(dlv, "_rows", return_value=ROWS)
        self._p.start()

    def tearDown(self):
        self._p.stop()

    def test_forecast(self):
        out = dlv.handle_delivery("forecast")
        self.assertIn("Control Tower", out)

    def test_risk(self):
        out = dlv.handle_delivery("risk")
        self.assertIn("Delivery risk", out)
        self.assertIn("Blocked P0", out)

    def test_capacity(self):
        out = dlv.handle_delivery("capacity")
        self.assertIn("Engineering capacity", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
