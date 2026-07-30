"""Tests for HSF-002 — Captain Capacity Decision Engine.

Covers:
  WP1 allocate_capacity  — focus/defer scale with capacity + priorities
  WP2 assess_mission_load — overload detection vs. capacity band
  WP4 detect_friction    — recurring capacity-drain patterns
  WP3 weekly_capacity_review — drivers/drains + one change
  WP5 highest_leverage   — ONE primary (+ optional secondary), scored, escalation
  WP6 xo_decision        — cross-domain allocation + one recommendation
  command routing + the doctrine guarantee: no banned language anywhere.

Pure/offline: mission-load and Supabase access are constructed/mocked directly.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

from lib.human_systems import decision, framework, xo, safety  # noqa: E402
from lib.human_systems.mission_load import MissionLoad, Priority, load_priorities  # noqa: E402
import commands.human_systems as hs  # noqa: E402

GOOD = {"log_date": "2026-06-20", "energy": "high", "mood": "positive",
        "nervous_system_state": "calm", "sleep_hours": 8.0, "sleep_quality": "good",
        "pain_score": 2, "captain_capacity_rating": "Green", "movement_completed": True}
HARD = {"log_date": "2026-06-20", "energy": "low", "mood": "low",
        "nervous_system_state": "dysregulated", "sleep_hours": 4.5,
        "sleep_quality": "poor", "pain_score": 8, "captain_capacity_rating": "Red"}

LOAD_HEAVY = MissionLoad(
    open_count=8, open_titles=["ANZ prep", "Mission review"],
    priorities=[Priority("P1", "Memory Layer", "Active"), Priority("P2", "Medical Officer", "Planned")],
    data_available=True,
)
LOAD_LIGHT = MissionLoad(
    open_count=1, open_titles=["ANZ prep"],
    priorities=[Priority("P1", "Memory Layer", "Active")], data_available=True,
)


def _snap(row):
    return framework.interpret_capacity(row)


# ── WP1 ───────────────────────────────────────────────────────────────────────

class TestAllocation(unittest.TestCase):
    def test_low_capacity_focuses_recovery_and_defers(self):
        a = decision.allocate_capacity(_snap(HARD), LOAD_HEAVY)
        self.assertEqual(a.focus[0], "Recovery")
        self.assertTrue(a.defer)
        self.assertEqual(safety.check_language("\n".join(a.focus + a.defer + [a.note])), [])

    def test_good_capacity_focuses_priority(self):
        a = decision.allocate_capacity(_snap(GOOD), LOAD_LIGHT)
        self.assertIn("Memory Layer", " ".join(a.focus))

    def test_focus_dedupes(self):
        a = decision.allocate_capacity(_snap(GOOD), LOAD_LIGHT)
        self.assertEqual(len(a.focus), len(set(a.focus)))


# ── WP2 ───────────────────────────────────────────────────────────────────────

class TestMissionLoad(unittest.TestCase):
    def test_overload_when_low_capacity(self):
        a = decision.assess_mission_load(_snap(HARD), LOAD_HEAVY)
        self.assertTrue(a.overloaded)
        self.assertIn("pausing new mission intake", a.recommendation.lower())

    def test_within_capacity_when_good_and_light(self):
        a = decision.assess_mission_load(_snap(GOOD), LOAD_LIGHT)
        self.assertFalse(a.overloaded)

    def test_moderate_with_heavy_backlog_overloads(self):
        mod = {"log_date": "2026-06-20", "energy": "moderate", "mood": "stable",
               "nervous_system_state": "calm", "sleep_hours": 7, "sleep_quality": "fair",
               "captain_capacity_rating": "Amber"}
        a = decision.assess_mission_load(_snap(mod), LOAD_HEAVY)
        self.assertTrue(a.overloaded)

    def test_no_load_data_is_graceful(self):
        a = decision.assess_mission_load(_snap(GOOD), MissionLoad())
        self.assertIn("not available", a.headline.lower())


# ── WP4 ───────────────────────────────────────────────────────────────────────

class TestFriction(unittest.TestCase):
    def test_too_few_rows_no_findings(self):
        self.assertEqual(decision.detect_friction([GOOD]), [])

    def test_recovery_debt_detected(self):
        rows = [dict(HARD, log_date=f"2026-06-1{i}") for i in range(4)]
        findings = decision.detect_friction(rows)
        self.assertTrue(any(f.key == "recovery_debt" for f in findings))
        # findings are language-compliant
        for f in findings:
            self.assertEqual(safety.check_language(f.description + " " + f.lever), [])

    def test_sleep_debt_detected(self):
        rows = [dict(GOOD, log_date=f"2026-06-1{i}", sleep_hours=5.0) for i in range(4)]
        findings = decision.detect_friction(rows)
        self.assertTrue(any(f.key in ("sleep_debt_avg", "short_sleep_next_day") for f in findings))

    def test_findings_sorted_by_confidence(self):
        rows = [dict(HARD, log_date=f"2026-06-1{i}") for i in range(5)]
        findings = decision.detect_friction(rows)
        confs = [f.confidence for f in findings]
        self.assertEqual(confs, sorted(confs, reverse=True))


# ── WP5 ───────────────────────────────────────────────────────────────────────

class TestHighestLeverage(unittest.TestCase):
    def test_low_capacity_recommends_protection(self):
        rec = decision.highest_leverage(_snap(HARD), LOAD_HEAVY, [])
        self.assertIn("protect", rec.primary.lower())
        self.assertGreater(rec.confidence, 0.5)

    def test_single_primary_and_compliant(self):
        rec = decision.highest_leverage(_snap(GOOD), LOAD_LIGHT, [])
        self.assertTrue(rec.primary)
        self.assertEqual(safety.check_language(rec.render()), [])

    def test_red_flag_escalation_embedded(self):
        rec = decision.highest_leverage(_snap(HARD), LOAD_HEAVY, [],
                                        notes="I have new numbness in my legs")
        self.assertIsNotNone(rec.escalation)
        self.assertIn("professional", rec.render().lower())

    def test_good_capacity_applies_to_priority(self):
        rec = decision.highest_leverage(_snap(GOOD), LOAD_LIGHT, [])
        self.assertIn("Memory Layer", rec.render())

    def test_secondary_is_distinct_domain_or_none(self):
        rec = decision.highest_leverage(_snap(HARD), LOAD_HEAVY,
                                        decision.detect_friction(
                                            [dict(HARD, log_date=f"2026-06-1{i}") for i in range(4)]))
        # secondary, if present, must not duplicate the primary
        if rec.secondary:
            self.assertNotEqual(rec.secondary, rec.primary)


# ── WP3 ───────────────────────────────────────────────────────────────────────

class TestCapacityReview(unittest.TestCase):
    def test_empty(self):
        self.assertIn("No check-ins", decision.weekly_capacity_review([], MissionLoad()))

    def test_review_has_drivers_drains_one_change(self):
        rows = [dict(GOOD, log_date="2026-06-14"), dict(GOOD, log_date="2026-06-15"),
                dict(HARD, log_date="2026-06-18"), dict(HARD, log_date="2026-06-19")]
        out = decision.weekly_capacity_review(rows, LOAD_HEAVY)
        self.assertIn("Capacity drivers", out)
        self.assertIn("Capacity drains", out)
        self.assertIn("Recommended change", out)
        self.assertEqual(safety.check_language(out), [])


# ── WP6 ───────────────────────────────────────────────────────────────────────

class TestXO(unittest.TestCase):
    def test_new_initiative_low_capacity_defers(self):
        out = xo.xo_decision("make progress on the coaching business this week",
                             _snap(HARD), LOAD_HEAVY)
        self.assertIn("holding new initiatives", out.lower())
        self.assertEqual(safety.check_language(out), [])

    def test_new_initiative_good_capacity_allows_start(self):
        out = xo.xo_decision("start the coaching business", _snap(GOOD), LOAD_LIGHT)
        self.assertIn("room to make a start", out.lower())

    def test_allocation_shows_not_reporting_commands(self):
        out = xo.xo_decision("plan my week", _snap(GOOD), LOAD_LIGHT)
        self.assertIn("Not yet reporting", out)
        self.assertIn("Remaining", out)

    def test_scan_false_suppresses_internal_banner(self):
        out = xo.xo_decision("chest pain and coaching", _snap(GOOD), LOAD_LIGHT, scan=False)
        self.assertNotIn("emergency", out.lower())


# ── Command routing ───────────────────────────────────────────────────────────

class TestCommand(unittest.TestCase):
    def setUp(self):
        self._rows = patch.object(hs, "_fetch_rows", return_value=[HARD])
        self._rows.start()
        self._load = patch.object(hs.ml, "get_mission_load", return_value=LOAD_HEAVY)
        self._load.start()
        self._mem = patch.object(hs.memory, "record_recommendation", lambda **k: True)
        self._mem.start()

    def tearDown(self):
        self._rows.stop(); self._load.stop(); self._mem.stop()

    def test_decide(self):
        out = hs.handle_human_systems("decide")
        self.assertIn("Highest-Leverage Action", out)
        self.assertEqual(safety.check_language(out), [])

    def test_focus(self):
        out = hs.handle_human_systems("focus")
        self.assertIn("Recommended Focus", out)
        self.assertIn("Defer", out)

    def test_load(self):
        out = hs.handle_human_systems("load")
        self.assertIn("Mission Load", out)

    def test_friction(self):
        out = hs.handle_human_systems("friction")
        self.assertTrue("Friction" in out)

    def test_capacity_review(self):
        out = hs.handle_human_systems("capacity-review")
        self.assertIn("Capacity", out)

    def test_xo(self):
        out = hs.handle_human_systems("xo make progress on the coaching business")
        self.assertIn("XO Decision Support", out)
        self.assertEqual(safety.check_language(out), [])

    def test_natural_language_what_should_i_do(self):
        out = hs.handle_human_systems("what should I do today?")
        self.assertIn("Highest-Leverage Action", out)

    def test_natural_language_overloaded(self):
        out = hs.handle_human_systems("am I overloaded with missions?")
        self.assertIn("Mission Load", out)

    def test_red_flag_overrides_decision(self):
        out = hs.handle_human_systems("decide — also I have chest pain and can't breathe")
        self.assertTrue(out.startswith(":rotating_light:") or out.startswith(":warning:"))
        self.assertEqual(safety.check_language(out), [])

    def test_all_decision_outputs_compliant(self):
        for cmd in ("decide", "focus", "load", "friction", "capacity-review",
                    "xo grow the business"):
            out = hs.handle_human_systems(cmd)
            self.assertEqual(safety.check_language(out), [], f"{cmd!r} violated language rules")


# ── Mission-load parsing (real file, tolerant) ────────────────────────────────

class TestPriorityParsing(unittest.TestCase):
    def test_priorities_parse_does_not_raise(self):
        # Reads the real memory/Active-Priorities.md if present; must never raise.
        result = load_priorities()
        self.assertIsInstance(result, list)


if __name__ == "__main__":
    unittest.main(verbosity=2)
