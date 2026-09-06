"""
Unit tests for the Briefs canonical uplift's deterministic post-processing
and rendering modules:
  - intelligence/brief/comparison.py   (current-vs-prior diff, Section 13)
  - intelligence/brief/domain_picture.py (cross-domain grouping, Section 12)
  - intelligence/brief/render.py       (Section 29 testable guarantees:
    Telegram/Captain's Chair must not invent a posture or development the
    canonical brief doesn't already state)
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.brief.comparison import compute_comparison
from intelligence.brief.domain_picture import compute_domain_picture
from intelligence.brief.render import build_morning_intelligence_view, render_telegram_morning_text


def _event(title, event_type="cyber", risk="AMBER"):
    return {"title": title, "event_type": event_type, "risk_rating": risk}


class TestComparison(unittest.TestCase):

    def test_no_prior_brief_returns_none(self):
        self.assertIsNone(compute_comparison([_event("Outage at X")], None))
        self.assertIsNone(compute_comparison([_event("Outage at X")], []))

    def test_new_event_classified_new(self):
        result = compute_comparison([_event("Brand new incident")], [_event("Unrelated prior story")])
        self.assertEqual(len(result["new"]), 1)
        self.assertEqual(result["new"][0]["title"], "Brand new incident")

    def test_matching_title_same_risk_is_unchanged_but_material(self):
        prior = [_event("Cloudflare outage affecting APAC", risk="AMBER")]
        current = [_event("Cloudflare outage affecting APAC", risk="AMBER")]
        result = compute_comparison(current, prior)
        self.assertEqual(len(result["unchanged_but_material"]), 1)

    def test_matching_title_higher_risk_is_escalated(self):
        prior = [_event("Regional grid disruption", risk="AMBER")]
        current = [_event("Regional grid disruption", risk="RED")]
        result = compute_comparison(current, prior)
        self.assertEqual(len(result["escalated"]), 1)

    def test_matching_title_lower_risk_is_improved(self):
        prior = [_event("Payments outage ongoing", risk="RED")]
        current = [_event("Payments outage ongoing", risk="AMBER")]
        result = compute_comparison(current, prior)
        self.assertEqual(len(result["improved"]), 1)

    def test_prior_event_absent_today_is_no_longer_material(self):
        prior = [_event("Resolved last week incident", risk="AMBER")]
        current = [_event("Completely different story", risk="GREEN")]
        result = compute_comparison(current, prior)
        self.assertEqual(len(result["no_longer_material"]), 1)
        self.assertEqual(result["no_longer_material"][0]["title"], "Resolved last week incident")

    def test_never_fabricates_beyond_the_two_inputs(self):
        """Every title in the result must come from one of the two input lists."""
        prior = [_event("Prior A"), _event("Prior B")]
        current = [_event("Prior A"), _event("Current C")]
        result = compute_comparison(current, prior)
        all_titles = {
            item["title"]
            for bucket in result.values()
            for item in bucket
        }
        self.assertTrue(all_titles.issubset({"Prior A", "Prior B", "Current C"}))


class TestDomainPicture(unittest.TestCase):

    def test_empty_events_returns_none(self):
        self.assertIsNone(compute_domain_picture([]))
        self.assertIsNone(compute_domain_picture(None))

    def test_groups_by_known_domain(self):
        events = [_event("Ransomware attack", event_type="cyber", risk="RED"),
                  _event("Cyclone warning", event_type="severe_weather", risk="AMBER")]
        picture = compute_domain_picture(events)
        self.assertIn("technical", picture)
        self.assertIn("environmental", picture)
        self.assertEqual(picture["technical"]["worst_risk"], "RED")

    def test_unknown_event_type_buckets_as_other(self):
        picture = compute_domain_picture([_event("Something novel", event_type="mystery_domain")])
        self.assertIn("other", picture)

    def test_does_not_invent_domains_absent_from_input(self):
        picture = compute_domain_picture([_event("Cyber incident", event_type="cyber")])
        self.assertNotIn("environmental", picture)
        self.assertNotIn("payments", picture)


class TestRenderConsistency(unittest.TestCase):
    """Section 29: given canonical brief X, no delivery channel invents a
    posture or a development the brief doesn't already state."""

    def _brief(self, **overrides):
        base = {
            "brief_id": "b-1",
            "generated_at": "2026-09-06T06:31:00+10:00",
            "overall_risk": "AMBER",
            "executive_snapshot": "A regional cloud outage affected several providers.",
            "top_events": [
                {"title": "Cloud provider outage", "so_what": "Check dependency exposure.", "risk_rating": "AMBER"},
                {"title": "Regulatory update announced", "so_what": "Review obligations.", "risk_rating": "GREEN"},
            ],
            "forward_watch": ["Ongoing recovery efforts"],
            "comparison": {"new": [{"title": "Cloud provider outage"}], "escalated": [], "improved": []},
            "coverage": {"degraded": False, "missing_sources": []},
        }
        base.update(overrides)
        return base

    def test_no_brief_reports_not_generated_not_nothing_happened(self):
        view = build_morning_intelligence_view(None)
        self.assertFalse(view["has_brief"])
        text = render_telegram_morning_text(None)
        self.assertIn("has not been generated", text)
        self.assertNotIn("No intelligence", text)

    def test_posture_matches_canonical_brief(self):
        brief = self._brief()
        view = build_morning_intelligence_view(brief)
        self.assertEqual(view["overall_risk"], brief["overall_risk"])
        text = render_telegram_morning_text(brief)
        self.assertIn(brief["overall_risk"], text)

    def test_what_matters_titles_are_drawn_from_top_events(self):
        brief = self._brief()
        view = build_morning_intelligence_view(brief, max_items=3)
        rendered_titles = {item["title"] for item in view["what_matters"]}
        source_titles = {e["title"] for e in brief["top_events"]}
        self.assertTrue(rendered_titles.issubset(source_titles))

    def test_captains_excerpt_and_telegram_view_share_the_same_selection(self):
        from intelligence.brief.render import render_captains_excerpt
        brief = self._brief()
        telegram_view = build_morning_intelligence_view(brief)
        chair_view = render_captains_excerpt(brief)
        self.assertEqual(telegram_view["overall_risk"], chair_view["overall_risk"])
        self.assertEqual(telegram_view["what_matters"], chair_view["what_matters"])

    def test_degraded_coverage_is_disclosed_not_silent(self):
        brief = self._brief(coverage={"degraded": True, "missing_sources": ["ACSC Feed"]})
        view = build_morning_intelligence_view(brief)
        self.assertTrue(view["coverage_degraded"])
        self.assertIn("unavailable", view["coverage_note"])
        text = render_telegram_morning_text(brief)
        self.assertIn("unavailable", text)


class TestCaptainsBriefIntelligencePosture(unittest.TestCase):
    """The Telegram morning message's intelligence section must render the
    canonical brief deterministically (Section 26/29) — no independent LLM
    re-synthesis of posture/what-matters happens in this block."""

    def test_no_brief_is_honest_not_silent(self):
        from intelligence.captains_brief import _format_intelligence_posture_block
        lines = _format_intelligence_posture_block(None)
        joined = "\n".join(lines)
        self.assertIn("has not been generated yet", joined)

    def test_renders_posture_and_top_events_from_brief(self):
        from intelligence.captains_brief import _format_intelligence_posture_block
        brief = {
            "overall_risk": "RED",
            "top_events": [{"title": "Major cloud outage", "so_what": "Check dependencies.", "risk_rating": "RED"}],
            "forward_watch": [],
            "comparison": None,
            "coverage": {"degraded": False},
        }
        lines = _format_intelligence_posture_block(brief)
        joined = "\n".join(lines)
        self.assertIn("RED", joined)
        self.assertIn("Major cloud outage", joined)

    def test_degraded_coverage_note_surfaces(self):
        from intelligence.captains_brief import _format_intelligence_posture_block
        brief = {
            "overall_risk": "AMBER",
            "top_events": [],
            "forward_watch": [],
            "comparison": None,
            "coverage": {"degraded": True, "missing_sources": ["ACSC"]},
        }
        joined = "\n".join(_format_intelligence_posture_block(brief))
        self.assertIn("unavailable", joined)


if __name__ == "__main__":
    unittest.main()
