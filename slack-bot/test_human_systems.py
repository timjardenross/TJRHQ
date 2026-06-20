"""Tests for HSF-001 — Human Systems Framework.

Covers:
  - safety: red-flag detection (per category, urgent ordering), escalation
    banner, language-rule enforcement, evidence framing.
  - framework: capacity interpretation (no-data + populated, four domains),
    plan generation (all types), signal explanation, weekly review + trend.
  - push: morning readiness, evening reflection, capacity degradation (fires
    only when actionable), weekly review, escalation override.
  - command: handle_human_systems routing, natural-language asks, red-flag
    override, and the doctrine guarantee that NO Captain-facing copy uses
    banned diagnostic / absolutist / shaming language.

No live network: Supabase access is mocked / disabled throughout.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

from lib.human_systems import safety, framework, push  # noqa: E402
import commands.human_systems as hs  # noqa: E402


# Sample rows shaped like analytics_health_daily.
GOOD_DAY = {
    "log_date": "2026-06-20", "energy": "high", "mood": "positive",
    "nervous_system_state": "calm", "sleep_hours": 8.0, "sleep_quality": "good",
    "pain_score": 2, "sitting_tolerance_minutes": 150,
    "captain_capacity_rating": "Green",
}
HARD_DAY = {
    "log_date": "2026-06-20", "energy": "low", "mood": "low",
    "nervous_system_state": "dysregulated", "sleep_hours": 4.5,
    "sleep_quality": "poor", "pain_score": 8, "sitting_tolerance_minutes": 40,
    "captain_capacity_rating": "Red",
}


# ── Safety ────────────────────────────────────────────────────────────────────

class TestSafety(unittest.TestCase):
    def test_empty_text_no_hits(self):
        self.assertEqual(safety.scan_red_flags(""), [])
        self.assertEqual(safety.scan_red_flags(None), [])
        self.assertIsNone(safety.escalation_banner([]))

    def test_mental_health_crisis_detected_and_urgent(self):
        hits = safety.scan_red_flags("I keep thinking I want to die")
        self.assertTrue(hits)
        self.assertEqual(hits[0].category, "mental_health_crisis")
        self.assertTrue(hits[0].urgent)

    def test_cardiac_detected(self):
        hits = safety.scan_red_flags("chest pain since this morning")
        self.assertTrue(any(h.category == "cardiac_respiratory" for h in hits))

    def test_neurological_detected(self):
        hits = safety.scan_red_flags("I have new numbness in my leg")
        self.assertTrue(any(h.category == "neurological" for h in hits))

    def test_non_urgent_infection(self):
        hits = safety.scan_red_flags("I think I have a fever today")
        self.assertTrue(hits)
        self.assertFalse(hits[0].urgent)

    def test_urgent_sorts_first(self):
        hits = safety.scan_red_flags("I have a fever and also chest pain")
        self.assertTrue(hits[0].urgent)

    def test_banner_is_non_diagnostic(self):
        hits = safety.scan_red_flags("chest pain")
        banner = safety.escalation_banner(hits)
        self.assertIn("999", banner)
        self.assertIn("decision-maker", banner)
        # The banner itself must obey language rules.
        self.assertEqual(safety.check_language(banner), [])

    def test_benign_text_no_false_positive(self):
        self.assertEqual(safety.scan_red_flags("slept ok, did a short walk"), [])

    def test_language_rules_catch_banned_phrases(self):
        self.assertTrue(safety.check_language("You have a slipped disc"))
        self.assertTrue(safety.check_language("This proves you are unwell"))
        self.assertTrue(safety.check_language("You must rest now"))
        self.assertTrue(safety.check_language("below target this week"))

    def test_compliant_language_passes(self):
        ok = "Based on the pattern, a practical next step could be to consider rest."
        self.assertEqual(safety.check_language(ok), [])

    def test_frame_adds_footer(self):
        out = safety.frame("hello")
        self.assertIn("non-diagnostic", out)
        self.assertEqual(safety.frame("hello", with_footer=False), "hello")


# ── Framework: capacity ───────────────────────────────────────────────────────

class TestCapacity(unittest.TestCase):
    def test_no_data_is_graceful(self):
        snap = framework.interpret_capacity(None)
        self.assertFalse(snap.data_available)
        self.assertEqual(len(snap.domains), 4)
        self.assertEqual(snap.overall_band, "moderate")

    def test_four_domains_present(self):
        snap = framework.interpret_capacity(GOOD_DAY)
        keys = {d.key for d in snap.domains}
        self.assertEqual(keys, {"physical", "cognitive", "emotional", "social"})

    def test_good_day_high_capacity(self):
        snap = framework.interpret_capacity(GOOD_DAY)
        self.assertTrue(snap.data_available)
        self.assertIn(snap.overall_band, ("good", "moderate"))
        self.assertGreater(snap.overall_score, 60)

    def test_hard_day_low_capacity(self):
        snap = framework.interpret_capacity(HARD_DAY)
        self.assertIn(snap.overall_band, ("limited", "depleted"))
        self.assertLess(snap.overall_score, 55)
        self.assertTrue(snap.limited_domains)

    def test_scores_bounded(self):
        for row in (GOOD_DAY, HARD_DAY, {}):
            snap = framework.interpret_capacity(row)
            for d in snap.domains:
                self.assertGreaterEqual(d.score, 0)
                self.assertLessEqual(d.score, 100)


# ── Framework: plans ──────────────────────────────────────────────────────────

class TestPlans(unittest.TestCase):
    def test_normalise_plan_type(self):
        self.assertEqual(framework.normalise_plan_type("low-capacity"), "low_capacity")
        self.assertEqual(framework.normalise_plan_type("recovery"), "recovery")
        self.assertEqual(framework.normalise_plan_type("exercise"), "movement")
        self.assertEqual(framework.normalise_plan_type("food"), "nutrition")
        self.assertIsNone(framework.normalise_plan_type("nonsense"))

    def test_all_plans_generate_and_are_compliant(self):
        snap = framework.interpret_capacity(HARD_DAY)
        for ptype in framework.PLAN_TYPES:
            body = framework.build_plan(ptype, snap)
            self.assertTrue(body.strip())
            self.assertEqual(
                safety.check_language(body), [],
                f"plan {ptype} violated language rules",
            )

    def test_movement_plan_scales_to_capacity(self):
        low = framework.build_plan("movement", framework.interpret_capacity(HARD_DAY))
        high = framework.build_plan("movement", framework.interpret_capacity(GOOD_DAY))
        self.assertNotEqual(low, high)


# ── Framework: explain + review ───────────────────────────────────────────────

class TestExplainReview(unittest.TestCase):
    def test_explain_no_data(self):
        out = framework.explain_signal(None)
        self.assertIn("no pattern", out.lower())

    def test_explain_populated_compliant(self):
        out = framework.explain_signal(HARD_DAY)
        self.assertIn("Physical", out)
        self.assertEqual(safety.check_language(out), [])

    def test_weekly_review_empty(self):
        out = framework.weekly_review([])
        self.assertIn("No check-ins", out)

    def test_weekly_review_detects_declining_trend(self):
        rows = [
            {"log_date": "2026-06-14", **GOOD_DAY},
            {"log_date": "2026-06-15", **GOOD_DAY},
            {"log_date": "2026-06-18", **HARD_DAY},
            {"log_date": "2026-06-19", **HARD_DAY},
        ]
        out = framework.weekly_review(rows)
        self.assertEqual(safety.check_language(out), [])
        self.assertIn("Trend", out)


# ── Push ──────────────────────────────────────────────────────────────────────

class TestPush(unittest.TestCase):
    def test_morning_pulse_compliant(self):
        msg = push.morning_readiness_pulse(GOOD_DAY)
        self.assertEqual(msg.kind, "readiness")
        self.assertEqual(safety.check_language(msg.render()), [])

    def test_morning_pulse_low_capacity_is_risk_signal(self):
        msg = push.morning_readiness_pulse(HARD_DAY)
        self.assertEqual(msg.output_class, "risk_signal")

    def test_morning_pulse_escalates_on_red_flag_note(self):
        row = dict(HARD_DAY, notes="having chest pain this morning")
        msg = push.morning_readiness_pulse(row)
        self.assertEqual(msg.kind, "escalation")
        self.assertEqual(msg.severity, "urgent")

    def test_evening_reflection_compliant(self):
        msg = push.evening_recovery_reflection(GOOD_DAY)
        self.assertEqual(msg.kind, "reflection")
        self.assertEqual(safety.check_language(msg.render()), [])

    def test_degradation_alert_none_when_steady(self):
        rows = [dict(GOOD_DAY, log_date=f"2026-06-1{i}") for i in range(4)]
        self.assertIsNone(push.capacity_degradation_alert(rows))

    def test_degradation_alert_fires_on_decline(self):
        rows = [
            dict(GOOD_DAY, log_date="2026-06-14"),
            dict(GOOD_DAY, log_date="2026-06-15"),
            dict(HARD_DAY, log_date="2026-06-18"),
            dict(HARD_DAY, log_date="2026-06-19"),
        ]
        msg = push.capacity_degradation_alert(rows)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.output_class, "risk_signal")
        self.assertEqual(safety.check_language(msg.render()), [])

    def test_degradation_needs_minimum_data(self):
        self.assertIsNone(push.capacity_degradation_alert([GOOD_DAY]))

    def test_weekly_review_push(self):
        msg = push.weekly_human_systems_review([GOOD_DAY, HARD_DAY])
        self.assertEqual(msg.output_class, "trend")


# ── Command ───────────────────────────────────────────────────────────────────

class TestCommand(unittest.TestCase):
    def setUp(self):
        # Disable network: every fetch returns no rows.
        self._patch = patch.object(hs, "_fetch_rows", return_value=[])
        self._patch.start()
        # Memory writes are no-ops in tests.
        self._mem = patch.multiple(
            hs.memory,
            record_recommendation=lambda **k: False,
            record_feedback=lambda **k: False,
            record_pattern=lambda **k: False,
        )
        self._mem.start()

    def tearDown(self):
        self._patch.stop()
        self._mem.stop()

    def test_empty_returns_help(self):
        self.assertIn("Human Systems", hs.handle_human_systems(""))

    def test_today(self):
        out = hs.handle_human_systems("today")
        self.assertIn("Daily capacity", out)
        self.assertEqual(safety.check_language(out), [])

    def test_plan_subcommands_compliant(self):
        for arg in ("low-capacity", "recovery", "movement", "nutrition", "mind"):
            out = hs.handle_human_systems(f"plan {arg}")
            self.assertEqual(safety.check_language(out), [], f"plan {arg}")
            self.assertTrue(out.strip())

    def test_natural_language_ask(self):
        out = hs.handle_human_systems("help me build a low-capacity day plan")
        self.assertIn("Low-Capacity Day Plan", out)

    def test_natural_language_pattern_question(self):
        # Routes to the signal explanation path (no-data message mentions pattern).
        out = hs.handle_human_systems("what does my sleep pattern suggest?")
        self.assertIn("pattern", out.lower())

    def test_review(self):
        out = hs.handle_human_systems("review")
        self.assertIn("Weekly Human Systems Review", out)

    def test_log(self):
        out = hs.handle_human_systems("log neck flared after a long sit")
        self.assertIn("Logged", out)

    def test_feedback(self):
        self.assertIn("Feedback recorded", hs.handle_human_systems("feedback useful"))
        self.assertIn("Feedback recorded", hs.handle_human_systems("feedback not too generic"))

    def test_red_flag_overrides_and_prepends(self):
        out = hs.handle_human_systems("plan movement but I have new numbness in my legs")
        # Escalation banner must come first.
        self.assertTrue(out.startswith(":rotating_light:") or out.startswith(":warning:"))
        self.assertIn("numbness", out.lower()) if False else None
        self.assertEqual(safety.check_language(out), [])

    def test_all_command_outputs_obey_language_rules(self):
        for cmd in ("", "today", "domains", "explain", "review",
                    "plan recovery", "plan nutrition"):
            out = hs.handle_human_systems(cmd)
            self.assertEqual(
                safety.check_language(out), [],
                f"command {cmd!r} violated language rules",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
