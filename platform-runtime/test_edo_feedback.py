"""Tests for MSN-EDO-003 (consolidation) WP3 — delivery feedback loop / learning."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

from lib.human_systems import learning, decision, framework, safety  # noqa: E402
from lib.human_systems.mission_load import MissionLoad, Priority  # noqa: E402
import commands.human_systems as hs  # noqa: E402
import commands.delivery as dlv  # noqa: E402

GOOD = {"energy": "high", "mood": "positive", "nervous_system_state": "calm",
        "sleep_hours": 8, "sleep_quality": "good", "captain_capacity_rating": "Green"}
LOAD = MissionLoad(open_count=2, open_titles=["X"],
                   priorities=[Priority("P1", "Memory Layer", "Active")], data_available=True)

EFF_ROWS = [
    {"domain": "resilience", "total": 10, "helpful": 9, "neutral": 1, "not_helpful": 0, "helpful_rate": 0.9},
    {"domain": "movement", "total": 2, "helpful": 0, "neutral": 0, "not_helpful": 2, "helpful_rate": 0.0},
]


class TestLearning(unittest.TestCase):
    def test_multiplier_bounds(self):
        self.assertEqual(learning._multiplier(1.0), 1.15)
        self.assertEqual(learning._multiplier(0.0), 0.85)
        self.assertTrue(0.85 <= learning._multiplier(0.5) <= 1.15)

    def test_learned_adjustments_filters_low_signal(self):
        adj = learning.learned_adjustments(EFF_ROWS)
        self.assertIn("resilience", adj)        # n=10 ≥ MIN_SIGNAL
        self.assertNotIn("movement", adj)       # n=2 < MIN_SIGNAL
        self.assertIn("_global", adj)
        self.assertGreater(adj["resilience"], 1.0)  # 90% helpful → tilt up

    def test_no_rows_no_adjustment(self):
        self.assertEqual(learning.learned_adjustments([]), {})

    def test_effectiveness_report_empty(self):
        self.assertIn("No feedback", learning.effectiveness_report([]))

    def test_effectiveness_report_populated(self):
        out = learning.effectiveness_report(EFF_ROWS)
        self.assertIn("resilience", out)
        self.assertIn("helpful", out)


class TestLearnedIntoDecision(unittest.TestCase):
    def _snap(self):
        return framework.interpret_capacity(GOOD)

    def test_backward_compatible_without_learned(self):
        rec = decision.highest_leverage(self._snap(), LOAD, [])
        self.assertTrue(rec.primary)

    def test_learned_tilts_confidence(self):
        base = decision.highest_leverage(self._snap(), LOAD, [])
        # tilt the winning domain up
        boosted = decision.highest_leverage(self._snap(), LOAD, [],
                                            learned={base.leverage and "priority": 1.15, "_global": 1.15})
        self.assertGreaterEqual(boosted.confidence, base.confidence)

    def test_package_accepts_learned_and_compliant(self):
        pkg = decision.recommendation_package(self._snap(), LOAD, [], learned={"_global": 1.1})
        self.assertEqual(safety.check_language(pkg.render()), [])


class TestCommands(unittest.TestCase):
    def test_hs_effectiveness(self):
        with patch.object(hs.learning, "fetch_effectiveness", return_value=EFF_ROWS):
            out = hs.handle_human_systems("effectiveness")
        self.assertIn("effectiveness", out.lower())
        self.assertIn("resilience", out)

    def test_delivery_dispatch(self):
        health = {"missions_dispatched": 1, "dispatched": 1, "pr_opened": 1, "failed": 0, "rolled_back": 0}
        with patch.object(dlv.data, "fetch_dispatch_health", return_value=health):
            out = dlv.handle_delivery("dispatch")
        self.assertIn("Dispatch health", out)
        self.assertIn("PRs opened: 1", out)

    def test_delivery_dispatch_empty(self):
        with patch.object(dlv.data, "fetch_dispatch_health", return_value=None):
            out = dlv.handle_delivery("dispatch")
        self.assertIn("No execution dispatches", out)


class TestMorningDeliveryNote(unittest.TestCase):
    def test_delivery_note_appended(self):
        from lib.human_systems import push
        msg = push.morning_readiness_pulse(GOOD, recommendation="Do X",
                                           delivery_note="2 open · 1 blocked")
        self.assertIn("Delivery:", msg.render())
        self.assertIn("1 blocked", msg.render())


if __name__ == "__main__":
    unittest.main(verbosity=2)
