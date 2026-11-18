#!/usr/bin/env python3
"""Tests for MSN-XO-002 — Captain's Daily Operating Picture (/brief)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

from commands import brief
from lib import daily_brief
from lib.human_systems import decision, framework, safety
from lib.human_systems.mission_load import MissionLoad, Priority

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
        self.assertTrue(out.startswith((":rotating_light:", ":warning:")))

    def test_officer_attribution(self):
        snap, pkg = self._pkg()
        out = daily_brief.compose_daily_brief(capacity=snap, recommendation=pkg, load=LOAD)
        self.assertIn("Human Systems Officer", out)


GOOD = {"energy": "high", "mood": "good", "nervous_system_state": "regulated",
        "sleep_hours": 8, "sleep_quality": "good", "captain_capacity_rating": "Green"}


class _ORI:
    def __init__(self, risk="AMBER", trend="steady", action="Watch the situation closely."):
        self.overall_risk, self.trend, self.confidence = risk, trend, 0.59
        self.top_risk, self.recommended_action, self.data_available = "Data centre expansion", action, True


class _Hit:
    def __init__(self, title, kind="lesson"):
        self.title, self.kind = title, kind


class _Opp:
    title, pillar_name, is_publishable = "Learning Intelligence Visibility", "Leadership", True


class _Obj:
    priority, title, domain = "P1", "Mature Endeavour", "Starship"
    def progress_label(self):
        return "no missions linked yet"


class _Strat:
    active, active_domains, orphan_count, data_available = [_Obj()], ["Starship"], 8, True


class TestCard(unittest.TestCase):
    def _compose(self, row=HARD, mode="card", **kw):
        snap = framework.interpret_capacity(row)
        pkg = decision.recommendation_package(snap, LOAD, [])
        return daily_brief.compose_daily_brief(
            capacity=snap, recommendation=pkg, load=LOAD, date_str="Mon 16 Nov 2026", mode=mode, **kw)

    def test_card_is_short_and_has_one_decision(self):
        out = self._compose(ori=_ORI(), knowledge=[_Hit("x")], comms=[_Opp()], strategy=_Strat(),
                            control_tower={"high_risk_count": 0, "open_count": 3})
        self.assertIn("Daily Operating Picture", out)
        self.assertIn("Today:", out)
        self.assertIn("Can wait:", out)
        self.assertLess(len(out.splitlines()), 12)
        self.assertLess(len(out), len(self._compose(mode="all", ori=_ORI(), comms=[_Opp()])) )
        for noisy in ("Opportunity cost", "Mission load", "Presence", "prior knowledge", "Strategic Focus"):
            self.assertNotIn(noisy, out)

    def test_limited_capacity_gets_no_worth_a_look(self):
        out = self._compose(comms=[_Opp()], strategy=_Strat(), knowledge=[_Hit("x")])
        self.assertNotIn("Worth a look", out)

    def test_good_capacity_gets_worth_a_look(self):
        out = self._compose(row=GOOD, comms=[_Opp()], strategy=_Strat(), knowledge=[_Hit("Real lesson")])
        self.assertIn("Worth a look", out)
        self.assertIn("Learning Intelligence Visibility", out)

    def test_amber_steady_resilience_stays_quiet(self):
        out = self._compose(ori=_ORI("AMBER", "steady"))
        self.assertNotIn("Resilience:", out)
        self.assertIn("Quiet:", out)
        self.assertIn("resilience (AMBER steady)", out)

    def test_amber_worsening_and_red_resilience_surface(self):
        for risk, trend in (("AMBER", "worsening"), ("RED", "steady")):
            out = self._compose(ori=_ORI(risk, trend))
            self.assertIn("Resilience:", out)

    def test_delivery_surfaces_only_on_risk_or_blockers(self):
        quiet = self._compose(control_tower={"high_risk_count": 0, "open_count": 4})
        self.assertNotIn("Delivery:", quiet)
        loud = self._compose(control_tower={"high_risk_count": 2, "open_count": 4})
        self.assertIn("Delivery: 2 high-risk of 4 open", loud)
        blocked = self._compose(delivery=decision.DeliverySignal(open_missions=8, blocked=2, top_bottleneck="VPS"))
        self.assertIn("2 blocked", blocked)

    def test_interrupt_and_escalation_still_lead(self):
        snap = framework.interpret_capacity(HARD)
        pkg = decision.recommendation_package(snap, LOAD, [], notes="I have chest pain and can't breathe")
        out = daily_brief.compose_daily_brief(capacity=snap, recommendation=pkg, load=LOAD, mode="card")
        self.assertTrue(out.startswith((":rotating_light:", ":warning:")))

    def test_card_is_language_compliant(self):
        self.assertEqual(safety.check_language(self._compose(ori=_ORI("RED", "worsening"))), [])

    def test_unknown_mode_rejected(self):
        with self.assertRaises(ValueError):
            self._compose(mode="bogus")


class TestSectionsAndCleanups(unittest.TestCase):
    def _compose(self, mode, **kw):
        snap = framework.interpret_capacity(HARD)
        pkg = decision.recommendation_package(snap, LOAD, [])
        return daily_brief.compose_daily_brief(
            capacity=snap, recommendation=pkg, load=LOAD, date_str="Mon 16 Nov 2026", mode=mode, **kw)

    def test_section_views(self):
        self.assertIn("Resilience", self._compose("resilience", ori=_ORI()))
        self.assertIn("Presence", self._compose("comms", comms=[_Opp()]))
        self.assertIn("Delivery", self._compose("delivery", control_tower=TOWER))
        self.assertIn("Nothing to report", self._compose("learning"))

    def test_orphans_equal_to_open_missions_hidden(self):
        s = _Strat()
        s.orphan_count = LOAD.open_count
        self.assertNotIn("unaligned", self._compose("all", strategy=s))
        s.orphan_count = 1
        self.assertIn("unaligned", self._compose("all", strategy=s))

    def test_delivery_hidden_when_nothing_open(self):
        out = self._compose("all", control_tower={"high_risk_count": 0, "open_count": 0, "top_risks": []})
        self.assertNotIn("Delivery (", out)

    def test_internal_knowledge_titles_filtered(self):
        out = self._compose("all", knowledge=[
            _Hit("[OFFICER SCHEDULE] knowledge_monthly_cross_domain: Monthly"), _Hit("Manual Now, Automate Later")])
        self.assertNotIn("OFFICER SCHEDULE", out)
        self.assertIn("Manual Now", out)

    def test_clip_is_word_boundary(self):
        self.assertEqual(daily_brief._clip("Review exception router classification", 20), "Review exception…")
        self.assertEqual(daily_brief._clip("short", 20), "short")


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

    def test_routing_card_all_and_sections(self):
        card, full = brief.handle_brief(""), brief.handle_brief("all")
        self.assertIn("Today:", card)
        self.assertNotIn("Opportunity cost", card)
        self.assertIn("Opportunity cost", full)
        self.assertIn("Resilience", brief.handle_brief("resilience"))

    def test_section_view_not_counted_as_brief(self):
        calls = []
        with patch.object(brief.memory, "record_recommendation", lambda **k: calls.append(k) or True):
            brief.handle_brief("delivery")
        self.assertEqual(calls, [])

    def test_feedback_hint(self):
        self.assertIn("feedback", brief.handle_brief("feedback").lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
