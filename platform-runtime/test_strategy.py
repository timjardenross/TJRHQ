"""Tests for MSN-SPC-001 — Strategic Planning Command MVP.

WP1/WP2 domain model + objective ranking · WP3 mission alignment / orphans ·
WP4 strategic focus in the Daily Operating Picture · WP6 gentle prioritisation
signal into the decision engine. Pure/offline.
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
from lib.strategy import objectives as obj, alignment as align  # noqa: E402
from lib.human_systems import framework, decision, safety  # noqa: E402
from lib.human_systems.mission_load import MissionLoad, Priority  # noqa: E402
import commands.brief as brief  # noqa: E402

GOOD = {"energy": "high", "mood": "positive", "nervous_system_state": "calm",
        "sleep_hours": 8, "sleep_quality": "good", "captain_capacity_rating": "Green"}
LOAD = MissionLoad(open_count=2, open_titles=["Memory Layer"],
                   priorities=[Priority("P1", "Memory Layer", "Active")], data_available=True)


def _objective(domain, title, priority="P1", status="active", linked=0, done=0):
    rate = round(done / linked, 2) if linked else None
    return obj.Objective(objective_id=f"OBJ-{title[:4]}", domain=domain, title=title,
                         status=status, priority=priority, linked_missions=linked,
                         open_missions=linked - done, completed_missions=done,
                         completion_rate=rate)


# ── WP1/WP2 domain model + ranking ────────────────────────────────────────────

class TestDomainModel(unittest.TestCase):
    def test_six_closed_domains(self):
        self.assertEqual(len(obj.STRATEGIC_DOMAINS), 6)
        self.assertIn("Starship Endeavour", obj.STRATEGIC_DOMAINS)

    def test_rank_active_orders_by_priority(self):
        objs = [_objective("Starship Endeavour", "Ship", "P2"),
                _objective("Health & Human Systems", "Health", "P0"),
                _objective("Learning & Growth", "Learn", "P3", status="paused")]
        ranked = obj.rank_active(objs)
        self.assertEqual([o.title for o in ranked], ["Health", "Ship"])  # paused excluded

    def test_top_per_domain_one_each(self):
        objs = [_objective("Starship Endeavour", "ShipA", "P2"),
                _objective("Starship Endeavour", "ShipB", "P1"),
                _objective("Coaching Enterprise", "Coach", "P1")]
        tops = obj.top_per_domain(objs)
        self.assertEqual(len(tops), 2)
        self.assertEqual([o.title for o in tops if o.domain == "Starship Endeavour"], ["ShipB"])

    def test_progress_label(self):
        o = _objective("Health & Human Systems", "Recover", linked=4, done=1)
        self.assertIn("1/4", o.progress_label())
        self.assertIn("no missions", _objective("Coaching Enterprise", "New").progress_label())


# ── WP3 mission alignment / orphan detection ──────────────────────────────────

class TestAlignment(unittest.TestCase):
    ROWS = [
        {"mission_id": "M1", "title": "Aligned", "status": "open", "strategic_objective_id": "OBJ-1"},
        {"mission_id": "M2", "title": "Orphan", "status": "in_progress", "strategic_objective_id": None},
        {"mission_id": "M3", "title": "Done", "status": "closed", "strategic_objective_id": None},
    ]

    def test_detect_orphans(self):
        rep = align.detect_orphans(self.ROWS)
        self.assertEqual(rep.orphan_count, 1)
        self.assertEqual(rep.aligned, 1)
        self.assertEqual(rep.total_open, 2)          # terminal mission excluded
        self.assertEqual(rep.alignment_rate, 0.5)

    def test_to_signal_weight_by_priority(self):
        snap = obj.StrategicSnapshot(objectives=[_objective("Starship Endeavour", "Ship", "P0")],
                                     data_available=True)
        sig = align.to_signal(snap)
        self.assertEqual(sig.top_objective, "Ship")
        self.assertAlmostEqual(sig.alignment_weight, 1.15)

    def test_to_signal_empty(self):
        sig = align.to_signal(obj.StrategicSnapshot())
        self.assertEqual(sig.alignment_weight, 1.0)
        self.assertIsNone(sig.top_objective)


# ── WP4 strategic focus in the Daily Operating Picture ────────────────────────

class TestStrategicFocusBrief(unittest.TestCase):
    def _pkg(self, strategic=None):
        snap = framework.interpret_capacity(GOOD)
        return snap, decision.recommendation_package(snap, LOAD, [], strategic=strategic)

    def test_brief_includes_strategic_focus(self):
        snap, pkg = self._pkg()
        strat = obj.StrategicSnapshot(
            objectives=[_objective("Starship Endeavour", "Unified intelligence layer", "P1", linked=3, done=2),
                        _objective("Health & Human Systems", "Stabilise capacity", "P2")],
            orphan_count=1, data_available=True)
        out = daily_brief.compose_daily_brief(capacity=snap, recommendation=pkg, load=LOAD,
                                              strategy=strat)
        self.assertIn("Strategic Focus", out)
        self.assertIn("Unified intelligence layer", out)
        self.assertIn("unaligned mission", out)
        self.assertEqual(safety.check_language(out), [])

    def test_brief_without_strategy_still_works(self):
        snap, pkg = self._pkg()
        out = daily_brief.compose_daily_brief(capacity=snap, recommendation=pkg, load=LOAD)
        self.assertNotIn("Strategic Focus", out)
        self.assertIn("Daily Operating Picture", out)


# ── WP6 gentle prioritisation signal into the decision engine ─────────────────

class TestPrioritisationSignal(unittest.TestCase):
    def test_strategy_boosts_priority_focus(self):
        snap = framework.interpret_capacity(GOOD)
        base = decision.highest_leverage(snap, LOAD, [])
        sig = decision.StrategicSignal(active_objectives=2, top_objective="Memory Layer",
                                       top_domain="Starship Endeavour", alignment_weight=1.10)
        boosted = decision.highest_leverage(snap, LOAD, [], strategic=sig)
        self.assertEqual(base.leverage, "priority focus")
        self.assertGreater(boosted.confidence, base.confidence)

    def test_package_names_the_objective(self):
        snap = framework.interpret_capacity(GOOD)
        sig = decision.StrategicSignal(active_objectives=1, top_objective="Coaching launch",
                                       top_domain="Coaching Enterprise", alignment_weight=1.10)
        pkg = decision.recommendation_package(snap, LOAD, [], strategic=sig)
        self.assertIn("Serves objective: Coaching launch", pkg.strategic_alignment)
        self.assertEqual(safety.check_language(pkg.render()), [])

    def test_backward_compatible(self):
        snap = framework.interpret_capacity(GOOD)
        self.assertTrue(decision.highest_leverage(snap, LOAD, []).primary)
        self.assertTrue(decision.recommendation_package(snap, LOAD, []).primary)


# ── Command wiring (graceful when strategy unavailable) ───────────────────────

class TestBriefCommandStrategy(unittest.TestCase):
    def test_strategy_view_graceful_no_data(self):
        with patch.object(brief._strategy, "fetch_snapshot",
                          return_value=obj.StrategicSnapshot()):
            out = brief.handle_brief("strategy")
        self.assertIn("Strategic Focus", out)
        self.assertIn("No active objectives", out)

    def test_strategy_view_lists_objectives(self):
        snap = obj.StrategicSnapshot(
            objectives=[_objective("Coaching Enterprise", "Coaching launch", "P1", linked=2, done=1)],
            orphan_count=0, data_available=True)
        with patch.object(brief._strategy, "fetch_snapshot", return_value=snap):
            out = brief.handle_brief("objectives")
        self.assertIn("Coaching launch", out)
        self.assertEqual(safety.check_language(out), [])

    def test_build_brief_with_strategy_graceful(self):
        snap = obj.StrategicSnapshot(
            objectives=[_objective("Starship Endeavour", "Ship", "P1")], data_available=True)
        with patch.object(brief, "_fetch_rows", return_value=[GOOD]), \
             patch("commands.brief.ml.get_mission_load", return_value=LOAD), \
             patch.object(brief, "_delivery_context", return_value=(None, None)), \
             patch.object(brief.ddata, "fetch_delivery_rows", return_value=[]), \
             patch.object(brief.learning, "learned_adjustments", return_value={}), \
             patch.object(brief._ori, "fetch_ori_signal", return_value=None), \
             patch.object(brief._knowledge, "relevant_knowledge", return_value=None), \
             patch.object(brief._strategy, "fetch_snapshot", return_value=snap), \
             patch.object(brief.memory, "record_recommendation", lambda **k: True):
            out = brief.handle_brief("")
        self.assertIn("Strategic Focus", out)
        self.assertEqual(safety.check_language(out), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
