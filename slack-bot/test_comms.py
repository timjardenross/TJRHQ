"""Tests for USS-TJR-MSN-COMMS-001 — Communications & Presence Officer.

WP2 pillars · WP3 opportunity engine (classify/score/build) · WP4/WP8 format
scaffolding · WP6 weekly brief · WP5 daily presence line + command wiring. Pure/
offline (Supabase access is mocked or absent).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_BOT = Path(__file__).resolve().parent
if str(_BOT) not in sys.path:
    sys.path.insert(0, str(_BOT))

from lib import daily_brief  # noqa: E402
from lib.comms import pillars, opportunities as opp, formats, weekly, portfolio  # noqa: E402
from lib.human_systems import framework, decision, safety  # noqa: E402
from lib.human_systems.mission_load import MissionLoad, Priority  # noqa: E402
import commands.comms as comms_cmd  # noqa: E402

GOOD = {"energy": "high", "mood": "positive", "nervous_system_state": "calm",
        "sleep_hours": 8, "sleep_quality": "good", "captain_capacity_rating": "Green"}
LOAD = MissionLoad(open_count=1, open_titles=["X"],
                   priorities=[Priority("P1", "X", "Active")], data_available=True)


def _opp(kind="mission", title="Resilience shakedown", body="incident recovery and continuity"):
    return opp.build_opportunity(kind, ref="R1", title=title, body=body)


# ── WP2 pillars ───────────────────────────────────────────────────────────────

class TestPillars(unittest.TestCase):
    def test_eight_pillars(self):
        self.assertEqual(len(pillars.PILLARS), 8)

    def test_classify_resilience(self):
        p, s = pillars.classify_pillar("a major outage and incident recovery story")
        self.assertEqual(p.key, "operational_resilience")
        self.assertGreater(s, 0)

    def test_classify_wellness(self):
        p, _ = pillars.classify_pillar("sleep, movement and sustainable coaching habits")
        self.assertEqual(p.key, "wellness_sustainable_performance")

    def test_default_when_no_match(self):
        p, s = pillars.classify_pillar("zzz qqq")
        self.assertEqual(s, 0)
        self.assertEqual(p, pillars.DEFAULT_PILLAR)


# ── WP3 opportunity engine ────────────────────────────────────────────────────

class TestOpportunityEngine(unittest.TestCase):
    def test_sensitive_is_internal_only(self):
        self.assertEqual(opp.classify("rotate the exposed credential and secret", 2),
                         opp.INTERNAL_ONLY)

    def test_no_pillar_is_future(self):
        self.assertEqual(opp.classify("generic note", 0), opp.FUTURE_OPPORTUNITY)

    def test_normal_is_publishable(self):
        self.assertEqual(opp.classify("resilience and continuity lessons", 2), opp.PUBLISHABLE)

    def test_score_rewards_fit_and_quality(self):
        low = opp.score("decision", 0)
        high = opp.score("decision", 3, quality=5)
        self.assertGreater(high, low)
        self.assertLessEqual(high, 1.0)

    def test_build_opportunity_maps_pillar_and_format(self):
        o = _opp()
        self.assertEqual(o.pillar_key, "operational_resilience")
        self.assertEqual(o.suggested_format, "case_study")
        self.assertTrue(o.is_publishable)
        self.assertEqual(o.strategic_domain, "Career & Professional Impact")

    def test_gather_graceful_offline(self):
        with patch.object(opp, "_client", return_value=None):
            self.assertEqual(opp.gather_opportunities(), [])


# ── WP4/WP8 format scaffolding ────────────────────────────────────────────────

class TestFormats(unittest.TestCase):
    def test_all_formats_render(self):
        o = _opp()
        for f in formats.FORMATS:
            out = formats.render_format(o, f.key)
            self.assertIn("Draft scaffold", out)
            self.assertIn("Captain", out)
            self.assertEqual(safety.check_language(out), [])

    def test_repurpose_multiple(self):
        o = _opp()
        bundle = formats.repurpose(o)
        self.assertGreaterEqual(len(bundle), 2)
        self.assertIn(o.suggested_format, bundle)


# ── WP6 weekly brief + WP5 presence line ──────────────────────────────────────

class TestWeeklyBrief(unittest.TestCase):
    def test_weekly_brief_prioritised_and_evidenced(self):
        items = [_opp(title="Operational shakedown", body="incident recovery continuity"),
                 _opp("capability", title="Endeavour command system", body="personal operating system governance")]
        out = weekly.compose_weekly_brief(items)
        self.assertIn("What should I be talking about this week", out)
        self.assertIn("Operational shakedown", out)
        self.assertIn("Strategic alignment", out)
        self.assertEqual(safety.check_language(out), [])

    def test_weekly_brief_empty_graceful(self):
        out = weekly.compose_weekly_brief([])
        self.assertIn("No publishable opportunities", out)

    def test_presence_line(self):
        line = weekly.compose_presence_line([_opp()])
        self.assertIn("Presence", line)
        self.assertIsNone(weekly.compose_presence_line([]))


# ── WP5 daily brief integration ───────────────────────────────────────────────

class TestDailyBriefPresence(unittest.TestCase):
    def _pkg(self):
        snap = framework.interpret_capacity(GOOD)
        return snap, decision.recommendation_package(snap, LOAD, [])

    def test_brief_includes_presence(self):
        snap, pkg = self._pkg()
        out = daily_brief.compose_daily_brief(capacity=snap, recommendation=pkg, load=LOAD,
                                              comms=[_opp(title="Resilience case study")])
        self.assertIn("Presence", out)
        self.assertIn("Resilience case study", out)
        self.assertEqual(safety.check_language(out), [])

    def test_brief_without_comms(self):
        snap, pkg = self._pkg()
        out = daily_brief.compose_daily_brief(capacity=snap, recommendation=pkg, load=LOAD)
        self.assertNotIn("Presence", out)


# ── Command wiring (graceful) ─────────────────────────────────────────────────

class TestCommsCommand(unittest.TestCase):
    def test_weekly_default(self):
        with patch.object(comms_cmd.opp, "gather_opportunities", return_value=[_opp()]):
            out = comms_cmd.handle_comms("")
        self.assertIn("Weekly Thought Leadership Brief", out)

    def test_opportunities(self):
        with patch.object(comms_cmd.opp, "gather_opportunities", return_value=[_opp()]):
            out = comms_cmd.handle_comms("opportunities")
        self.assertIn("Content Opportunities", out)

    def test_draft_by_index(self):
        with patch.object(comms_cmd.opp, "gather_opportunities", return_value=[_opp()]), \
             patch.object(comms_cmd.portfolio, "record_content", lambda **k: True):
            out = comms_cmd.handle_comms("draft 1")
        self.assertIn("Draft scaffold", out)

    def test_draft_out_of_range(self):
        with patch.object(comms_cmd.opp, "gather_opportunities", return_value=[_opp()]):
            out = comms_cmd.handle_comms("draft 9")
        self.assertIn("isn't in range", out)

    def test_pillars(self):
        self.assertIn("Thought Leadership Pillars", comms_cmd.handle_comms("pillars"))

    def test_portfolio_graceful(self):
        with patch.object(comms_cmd.portfolio, "fetch_portfolio", return_value=[]), \
             patch.object(comms_cmd.portfolio, "pipeline_summary", return_value={}):
            out = comms_cmd.handle_comms("portfolio")
        self.assertIn("Reputation Portfolio", out)


# ── WP7 portfolio store graceful ──────────────────────────────────────────────

class TestPortfolioStore(unittest.TestCase):
    def test_record_content_graceful(self):
        with patch.object(portfolio, "_client", return_value=None):
            self.assertFalse(portfolio.record_content(content_id="c1", title="t"))

    def test_pipeline_summary_graceful(self):
        with patch.object(portfolio, "_client", return_value=None):
            self.assertEqual(portfolio.pipeline_summary(), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
