"""
Unit tests for intelligence/classification/ori_enrichment.py (USS-TJR-MSN-0074 WP4).

Proves the rule-based extraction produces the structured intelligence records the
mission requires (themes, regulatory topic, organisation, watch status, executive
relevance), using the two worked examples from the mission brief.
"""

import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.models import IntelligenceItem
from intelligence.classification.classifier import classify
from intelligence.classification.ori_enrichment import (
    map_themes, map_regulatory_topic, extract_organisation,
    derive_watch_status, enrich,
)


def _classify(title: str, summary: str = ""):
    item = IntelligenceItem(
        source_id="00000000-0000-0000-0000-0000000000ff",
        source_name="Daily OR Briefs",
        source_priority=2,
        source_confidence_weight=0.75,
        source_category="resilience_brief",
        raw_title=title,
        collected_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
        raw_summary=summary,
        canonical_url="https://github.com/x/blob/main/b.md",
        published_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
    )
    return classify(item)


class TestThemeTaxonomy(unittest.TestCase):
    def test_telco_outage_themes(self):
        themes = map_themes(
            "Major Vodafone Australia network outage due to hub failure", "telecom_outage")
        self.assertIn("telco_resilience", themes)
        self.assertIn("single_point_of_failure", themes)
        self.assertIn("service_continuity", themes)

    def test_regulatory_themes(self):
        themes = map_themes("CPS 230 amendments effective July 2026", "regulatory")
        self.assertIn("regulatory_change", themes)

    def test_third_party_theme(self):
        themes = map_themes("Strengthen third-party and outsourcing risk testing", "other")
        self.assertIn("third_party_risk", themes)


class TestRegulatoryTopic(unittest.TestCase):
    def test_cps230(self):
        self.assertEqual(map_regulatory_topic("CPS 230 amendments effective July 2026"), "CPS230")

    def test_soci(self):
        self.assertEqual(map_regulatory_topic("SOCI Act obligations for critical infrastructure"), "SOCI_Act")

    def test_none(self):
        self.assertIsNone(map_regulatory_topic("A telco outage in Sydney"))


class TestOrganisation(unittest.TestCase):
    def test_known_org(self):
        self.assertEqual(extract_organisation("Major Vodafone Australia network outage"), "Vodafone")

    def test_regulator(self):
        self.assertEqual(extract_organisation("APRA reinforces CPS 230 expectations"), "APRA")


class TestWatchStatus(unittest.TestCase):
    def test_active_incident(self):
        self.assertEqual(
            derive_watch_status("Network outage affecting millions, investigating", "telecom_outage"),
            "active_incident")

    def test_regulatory_horizon(self):
        self.assertEqual(
            derive_watch_status("CPS 230 amendments effective July 2026", "regulatory"),
            "regulatory_horizon")

    def test_closed(self):
        # Closure language with no in-progress indicator -> closed.
        self.assertEqual(
            derive_watch_status("Outage fully restored and remediated", "telecom_outage"),
            "closed")


class TestEndToEndExtraction(unittest.TestCase):
    """The two worked examples from the mission brief (WP4)."""

    def test_telecommunications_outage_record(self):
        ev = _classify(
            "Major Vodafone Australia network outage on June 18 due to hub failure. "
            "Affected millions, services mostly restored by late morning.")
        ori = enrich(ev, in_implications=True)
        self.assertEqual(ev.event_type, "telecom_outage")
        self.assertEqual(ev.geography, "AU")
        self.assertEqual(ori["organisation"], "Vodafone")
        self.assertIn("third_party_risk", ori["resilience_themes"])
        self.assertIn("single_point_of_failure", ori["resilience_themes"])
        self.assertIn("service_continuity", ori["resilience_themes"])
        self.assertEqual(ori["executive_relevance"], "high")

    def test_regulatory_update_record(self):
        ev = _classify("CPS 230 amendments effective July 2026.")
        ori = enrich(ev, in_implications=False)
        self.assertEqual(ev.event_type, "regulatory")
        self.assertTrue(ev.cps230_relevance)
        self.assertEqual(ori["regulatory_topic"], "CPS230")
        self.assertEqual(ori["watch_item_status"], "regulatory_horizon")
        self.assertEqual(ori["executive_relevance"], "high")
        # Themes per mission example: CPS 230, outsourcing risk, material service providers
        self.assertIn("regulatory_change", ori["resilience_themes"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
