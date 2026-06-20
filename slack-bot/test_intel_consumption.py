"""Tests for MSN-XO-003 — Unified Intelligence Consumption Layer.

WP2 ORI surfacing · WP3 Knowledge surfacing · WP1 composer integration ·
WP4 ORI influences the recommendation. Pure/offline.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

from lib import daily_brief  # noqa: E402
from lib.intel import ori, knowledge  # noqa: E402
from lib.human_systems import framework, decision, safety  # noqa: E402
from lib.human_systems.mission_load import MissionLoad, Priority  # noqa: E402
import commands.brief as brief  # noqa: E402

GOOD = {"energy": "high", "mood": "positive", "nervous_system_state": "calm",
        "sleep_hours": 8, "sleep_quality": "good", "captain_capacity_rating": "Green"}
LOAD = MissionLoad(open_count=2, open_titles=["X"],
                   priorities=[Priority("P1", "Memory Layer", "Active")], data_available=True)


# ── WP2 ORI ───────────────────────────────────────────────────────────────────

class TestORI(unittest.TestCase):
    BRIEF = {"overall_risk": "AMBER",
             "top_events": [{"title": "Major cloud provider outage in APAC"}],
             "bottom_line": "Watch dependency on the affected provider this week.",
             "forward_watch": ["Regulator guidance expected"], "confidence": 0.7}

    def test_top_risk_from_events(self):
        self.assertIn("cloud provider outage", ori._top_risk(self.BRIEF))

    def test_recommended_action_from_bottom_line(self):
        self.assertIn("Watch dependency", ori._recommended_action(self.BRIEF))

    def test_top_risk_falls_back_to_themes(self):
        b = {"emerging_themes": ["Supply chain stress"]}
        self.assertEqual(ori._top_risk(b), "Supply chain stress")


# ── WP3 Knowledge ─────────────────────────────────────────────────────────────

class TestKnowledge(unittest.TestCase):
    def test_best_hit_overlap(self):
        q = knowledge._tokens("improve the medical bay dashboard")
        rows = [{"name": "Medical Bay Dashboard", "purpose": "recovery dashboard"},
                {"name": "Slack Commander", "purpose": "bot"}]
        hit = knowledge.best_hit(q, rows, "capability", ["name", "purpose"])
        self.assertIsNotNone(hit)
        self.assertIn("Medical Bay", hit.title)

    def test_best_hit_none_when_no_overlap(self):
        q = knowledge._tokens("quantum warp core")
        rows = [{"name": "Medical Bay Dashboard", "purpose": "recovery"}]
        self.assertIsNone(knowledge.best_hit(q, rows, "capability", ["name", "purpose"]))


# ── WP1 composer integration ──────────────────────────────────────────────────

class TestComposer(unittest.TestCase):
    def _pkg(self):
        snap = framework.interpret_capacity(GOOD)
        return snap, decision.recommendation_package(snap, LOAD, [])

    def test_brief_includes_ori_and_knowledge(self):
        snap, pkg = self._pkg()
        sig = ori.ORISignal(overall_risk="AMBER", top_risk="Cloud outage", trend="worsening",
                            confidence=0.7, recommended_action="Watch provider dependency.")
        hits = [knowledge.KnowledgeHit("decision", "Adopt dual-region hosting", 3),
                knowledge.KnowledgeHit("lesson", "Single-provider risk", 2)]
        out = daily_brief.compose_daily_brief(capacity=snap, recommendation=pkg, load=LOAD,
                                              ori=sig, knowledge=hits)
        self.assertIn("Resilience (Operational Resilience Intelligence)", out)
        self.assertIn("Cloud outage", out)
        self.assertIn("Relevant prior knowledge", out)
        self.assertIn("Adopt dual-region hosting", out)
        self.assertEqual(safety.check_language(out), [])

    def test_brief_without_intel_still_works(self):
        snap, pkg = self._pkg()
        out = daily_brief.compose_daily_brief(capacity=snap, recommendation=pkg, load=LOAD)
        self.assertIn("Daily Operating Picture", out)


# ── WP4 ORI influences the recommendation ─────────────────────────────────────

class TestORIInfluence(unittest.TestCase):
    def test_red_ori_competes_on_good_day(self):
        snap = framework.interpret_capacity(GOOD)
        rec = decision.highest_leverage(snap, LOAD, [], ori_risk="RED",
                                        ori_headline="Critical regulator action")
        # On a good-capacity day a RED external risk should surface.
        self.assertIn("resilience risk", rec.render().lower())

    def test_green_ori_does_not_inject(self):
        snap = framework.interpret_capacity(GOOD)
        rec = decision.highest_leverage(snap, LOAD, [], ori_risk="GREEN")
        self.assertNotIn("emerging resilience risk", rec.primary.lower())

    def test_package_passes_ori_and_compliant(self):
        snap = framework.interpret_capacity(GOOD)
        pkg = decision.recommendation_package(snap, LOAD, [], ori_risk="AMBER",
                                              ori_headline="Provider outage")
        self.assertEqual(safety.check_language(pkg.render()), [])

    def test_backward_compatible(self):
        snap = framework.interpret_capacity(GOOD)
        self.assertTrue(decision.highest_leverage(snap, LOAD, []).primary)


# ── Command wires it together (graceful when intel unavailable) ───────────────

class TestBriefCommand(unittest.TestCase):
    def test_brief_builds_with_intel_graceful(self):
        with patch.object(brief, "_fetch_rows", return_value=[GOOD]), \
             patch("commands.brief.ml.get_mission_load", return_value=LOAD), \
             patch.object(brief, "_delivery_context", return_value=(None, None)), \
             patch.object(brief.ddata, "fetch_delivery_rows", return_value=[]), \
             patch.object(brief.learning, "learned_adjustments", return_value={}), \
             patch.object(brief._ori, "fetch_ori_signal", return_value=None), \
             patch.object(brief._knowledge, "relevant_knowledge", return_value=None), \
             patch.object(brief.memory, "record_recommendation", lambda **k: True):
            out = brief.handle_brief("")
        self.assertIn("Daily Operating Picture", out)
        self.assertEqual(safety.check_language(out), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
