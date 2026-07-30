"""Tests for MSN-XO-002 — Captain's Daily Operating Picture (/brief)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

from lib import daily_brief  # noqa: E402
from lib.human_systems import framework, decision, safety  # noqa: E402
from lib.human_systems.mission_load import MissionLoad, Priority  # noqa: E402
import commands.brief as brief  # noqa: E402

HARD = {"energy": "low", "mood": "low", "nervous_system_state": "dysregulated",
        "sleep_hours": 4.5, "sleep_quality": "poor", "captain_capacity_rating": "Red"}
LOAD = MissionLoad(open_count=8, open_titles=["ANZ"],
                   priorities=[Priority("P1", "Memory Layer", "Active")], data_available=True)
TOWER = {"high_risk_count": 2, "open_count": 5,
         "bottleneck": {"constraint": "planned", "constraint_count": 5},
         "top_risks": [type("R", (), {"title": "VPS Migration", "score": 80})()]}


class TestCompose(unittest.TestCase):
    def _pkg(self, **kw):
        snap = framework.interpret_capacity(HARD)
        return snap, decision.recommendation_package(snap, LOAD, [], **kw)

    def test_brief_has_all_sections(self):
        snap, pkg = self._pkg(delivery=decision.DeliverySignal(open_missions=8, blocked=2, top_bottleneck="VPS"))
        out = daily_brief.compose_daily_brief(
            capacity=snap, recommendation=pkg, load=LOAD,
            delivery=decision.DeliverySignal(open_missions=8, blocked=2, top_bottleneck="VPS"),
            control_tower=TOWER, date_str="Fri 20 Jun 2026")
        for token in ("Daily Operating Picture", "Decision", "Capacity", "Mission load",
                      "Delivery", "blockers", "What can wait"):
            self.assertIn(token, out)

    def test_brief_is_language_compliant(self):
        snap, pkg = self._pkg()
        out = daily_brief.compose_daily_brief(capacity=snap, recommendation=pkg, load=LOAD)
        self.assertEqual(safety.check_language(out), [])

    def test_escalation_leads(self):
        snap = framework.interpret_capacity(HARD)
        pkg = decision.recommendation_package(snap, LOAD, [], notes="I have chest pain and can't breathe")
        out = daily_brief.compose_daily_brief(capacity=snap, recommendation=pkg, load=LOAD)
        self.assertTrue(out.startswith(":rotating_light:") or out.startswith(":warning:"))

    def test_officer_attribution(self):
        snap, pkg = self._pkg()
        out = daily_brief.compose_daily_brief(capacity=snap, recommendation=pkg, load=LOAD)
        self.assertIn("Human Systems Officer", out)


class TestCommand(unittest.TestCase):
    def setUp(self):
        self._rows = patch.object(brief, "_fetch_rows", return_value=[HARD])
        self._rows.start()
        self._load = patch("commands.brief.ml.get_mission_load", return_value=LOAD)
        self._load.start()
        self._deliv = patch.object(brief, "_delivery_context", return_value=(None, None))
        self._deliv.start()
        self._tower = patch.object(brief.ddata, "fetch_delivery_rows", return_value=[])
        self._tower.start()
        self._learn = patch.object(brief.learning, "learned_adjustments", return_value={})
        self._learn.start()
        self._mem = patch.object(brief.memory, "record_recommendation", lambda **k: True)
        self._mem.start()

    def tearDown(self):
        for p in (self._rows, self._load, self._deliv, self._tower, self._learn, self._mem):
            p.stop()

    def test_brief_renders(self):
        out = brief.handle_brief("")
        self.assertIn("Daily Operating Picture", out)
        self.assertEqual(safety.check_language(out), [])

    def test_brief_records_usage(self):
        calls = []
        with patch.object(brief.memory, "record_recommendation", lambda **k: calls.append(k) or True):
            brief.handle_brief("")
        self.assertTrue(any(c["kind"] == "daily_brief" for c in calls))

    def test_feedback_hint(self):
        self.assertIn("feedback", brief.handle_brief("feedback").lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
