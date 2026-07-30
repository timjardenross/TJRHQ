"""Tests for MSN-EDO-002 — delivery maturity phase.

WP2 execution package generator (governance gates, no autonomous merge);
WP3 highest_leverage delivery signal; WP4 cross-domain Engineering allocation
+ recommended adjustment. Pure/offline.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

from lib.delivery import execution  # noqa: E402
from lib.human_systems import decision, xo, framework, safety  # noqa: E402
from lib.human_systems.mission_load import MissionLoad, Priority  # noqa: E402

GOOD = {"log_date": "2026-06-20", "energy": "high", "mood": "positive",
        "nervous_system_state": "calm", "sleep_hours": 8, "sleep_quality": "good",
        "captain_capacity_rating": "Green"}
HARD = {"log_date": "2026-06-20", "energy": "low", "mood": "low",
        "nervous_system_state": "dysregulated", "sleep_hours": 4.5,
        "sleep_quality": "poor", "pain_score": 8, "captain_capacity_rating": "Red"}


def _snap(r):
    return framework.interpret_capacity(r)


# ── WP2: execution package ────────────────────────────────────────────────────

class TestExecution(unittest.TestCase):
    def _mission(self, status="Designed"):
        return {"mission_id": "MSN-0099", "title": "Improve Medical Bay dashboard",
                "status": status, "description": "make it better"}

    def test_blocked_without_plan_approval(self):
        pkg, reason = execution.build_execution_package(self._mission(), plan_approved=False)
        self.assertIsNone(pkg)
        self.assertIn("plan not approved", reason)

    def test_blocked_when_not_eligible_state(self):
        pkg, reason = execution.build_execution_package(self._mission("Closed"), plan_approved=True)
        self.assertIsNone(pkg)
        self.assertIn("not eligible", reason)

    def test_builds_when_approved(self):
        pkg, reason = execution.build_execution_package(self._mission(), plan_approved=True)
        self.assertEqual(reason, "ok")
        self.assertEqual(pkg.target_state, "in_progress")
        self.assertTrue(pkg.branch.startswith("edo/"))

    def test_governance_invariants_non_bypassable(self):
        pkg, _ = execution.build_execution_package(self._mission(), plan_approved=True)
        self.assertTrue(pkg.governance["no_autonomous_merge"])
        self.assertTrue(pkg.governance["no_autonomous_closure"])
        self.assertTrue(pkg.governance["requires_xo_merge_approval"])
        # render must state the gates and never claim merge/close
        text = pkg.render()
        self.assertIn("No autonomous merge", text)
        self.assertNotIn("merged", text.lower())

    def test_missing_id(self):
        pkg, reason = execution.build_execution_package({"title": "x", "status": "Designed"}, plan_approved=True)
        self.assertIsNone(pkg)

    def test_dispatch_payload(self):
        pkg, _ = execution.build_execution_package(self._mission(), plan_approved=True)
        payload = execution.dispatch_payload(pkg)
        self.assertEqual(payload["inputs"]["mission_id"], "MSN-0099")


# ── WP3: highest_leverage delivery signal ─────────────────────────────────────

class TestDeliverySignal(unittest.TestCase):
    LOAD = MissionLoad(open_count=2, open_titles=["X"],
                       priorities=[Priority("P1", "Memory", "Active")], data_available=True)

    def test_blocked_delivery_becomes_candidate(self):
        sig = decision.DeliverySignal(open_missions=4, blocked=2, top_bottleneck="Foo")
        rec = decision.highest_leverage(_snap(GOOD), self.LOAD, [], delivery=sig)
        # On a good-capacity day, an unblock is a strong candidate.
        self.assertIn("blocked", rec.render().lower())
        self.assertEqual(safety.check_language(rec.render()), [])

    def test_bottleneck_candidate_when_no_block(self):
        sig = decision.DeliverySignal(open_missions=3, blocked=0, top_bottleneck="Stuck thing")
        rec = decision.highest_leverage(_snap(GOOD), self.LOAD, [], delivery=sig)
        text = rec.render().lower()
        self.assertTrue("stuck thing" in text or "bottleneck" in text or "memory" in text)

    def test_backward_compatible_without_delivery(self):
        rec = decision.highest_leverage(_snap(HARD), self.LOAD, [])
        self.assertTrue(rec.primary)

    def test_low_capacity_still_protects_over_delivery(self):
        sig = decision.DeliverySignal(open_missions=8, blocked=1)
        rec = decision.highest_leverage(_snap(HARD), self.LOAD, [], delivery=sig)
        # Depleted capacity protection should still win over an unblock.
        self.assertIn("protect", rec.primary.lower())


# ── WP4: cross-domain Engineering allocation ──────────────────────────────────

class TestCrossDomain(unittest.TestCase):
    LOAD = MissionLoad(open_count=3, open_titles=["X"], priorities=[], data_available=True)

    def test_engineering_becomes_reporting(self):
        view = xo.allocate(_snap(GOOD), self.LOAD, engineering_load=4)
        self.assertIn("Engineering", view.shares)
        self.assertNotIn("Engineering", view.not_reporting)

    def test_engineering_not_reporting_without_load(self):
        view = xo.allocate(_snap(GOOD), self.LOAD)
        self.assertIn("Engineering", view.not_reporting)

    def test_recommended_adjustment_present(self):
        out = xo.xo_decision("where should effort go this week", _snap(HARD),
                             self.LOAD, engineering_load=6)
        self.assertIn("Recommended adjustment", out)
        self.assertIn("Engineering", out)
        self.assertEqual(safety.check_language(out), [])

    def test_high_engineering_low_remaining_defers(self):
        view = xo.allocate(_snap(HARD), self.LOAD, engineering_load=6)
        adj = xo.recommended_adjustment(view)
        self.assertTrue("defer" in adj.lower() or "hold" in adj.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
