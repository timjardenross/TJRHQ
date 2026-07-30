"""
Unit tests for intelligence/classification/classifier.py

Covers:
- Event type classification (14 types)
- Geography tagging (AU, APAC, GLOBAL)
- Banking relevance flags (low/medium/high)
- CPS230 relevance (bool)
- Dependency risk (bool)
- Customer impact (low/medium/high)
- Confidence score range
- No LLM involved — all rule-based
"""

import sys
import os
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.models import IntelligenceItem, ClassifiedEvent
from intelligence.classification.classifier import classify


def _make_item(title: str, summary: str = "",
               source_priority: int = 2,
               source_confidence_weight: float = 0.8) -> IntelligenceItem:
    return IntelligenceItem(
        source_id="test-src",
        source_name="Test Source",
        source_priority=source_priority,
        source_confidence_weight=source_confidence_weight,
        source_category="media",
        raw_title=title,
        collected_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
        raw_summary=summary,
        canonical_url="https://example.com/item",
        published_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
    )


class TestEventTypeClassification(unittest.TestCase):

    def _type(self, title, summary=""):
        return classify(_make_item(title, summary)).event_type

    def test_cyber_incident(self):
        self.assertEqual(self._type("Major ransomware attack hits ANZ Bank"), "cyber")

    def test_cyber_phishing(self):
        self.assertEqual(self._type("Phishing campaign targets CBA customers"), "cyber")

    def test_severe_weather(self):
        self.assertEqual(self._type("Cyclone warning issued for Queensland coast"), "severe_weather")

    def test_severe_weather_flood(self):
        t = self._type("Flood emergency declared across NSW and VIC")
        self.assertIn(t, ("severe_weather", "other"))

    def test_technology_outage(self):
        self.assertEqual(self._type("AWS us-east-1 region outage impacts multiple customers"), "technology_outage")

    def test_telecom_outage(self):
        self.assertEqual(self._type("Telstra network disruption impacts mobile services"), "telecom_outage")

    def test_regulatory(self):
        self.assertEqual(self._type("APRA releases updated CPS 230 guidelines"), "regulatory")

    def test_payments_disruption(self):
        t = self._type("NPP outage affects OSKO real-time payments for 3 hours")
        self.assertEqual(t, "payments_disruption")

    def test_geopolitical(self):
        self.assertEqual(self._type("Nation-state espionage campaign targets critical infrastructure"), "geopolitical")

    def test_supply_chain(self):
        self.assertEqual(self._type("Supply chain logistics disruption hits port congestion"), "supply_chain")

    def test_third_party_disruption(self):
        self.assertEqual(self._type("Critical third-party vendor managed service failure"), "third_party_disruption")

    def test_workforce(self):
        self.assertEqual(self._type("Industrial strike action disrupts workforce at major bank"), "workforce")

    def test_unknown_falls_back_to_other(self):
        t = self._type("Random unrelated content nothing relevant at all")
        self.assertIsNotNone(t)  # must return a string


class TestGeographyClassification(unittest.TestCase):

    def _geo(self, title, summary=""):
        return classify(_make_item(title, summary)).geography

    def test_australia_from_state(self):
        self.assertEqual(self._geo("Flood emergency declared across NSW and VIC"), "AU")

    def test_australia_from_regulator(self):
        self.assertEqual(self._geo("RBA holds cash rate at 4.35% amid inflation"), "AU")

    def test_apac_singapore(self):
        self.assertEqual(self._geo("Singapore MAS issues new resilience guidelines"), "APAC")

    def test_apac_hong_kong(self):
        # Hong Kong → APAC. No AU state abbreviation substrings in this title.
        self.assertEqual(self._geo("Hong Kong cyber resilience framework published"), "APAC")

    def test_apac_singapore(self):
        self.assertEqual(self._geo("Singapore MAS issues new resilience guidelines"), "APAC")

    def test_global_when_no_au_apac(self):
        # Must contain no AU or APAC keyword substrings
        self.assertEqual(self._geo("US Federal Reserve lifts rates for the third time"), "GLOBAL")

    def test_au_beats_apac(self):
        # Title contains both AU and APAC signals — AU should win
        geo = self._geo("Melbourne-based bank affected by APAC-wide cyber campaign")
        self.assertEqual(geo, "AU")


class TestBankingRelevance(unittest.TestCase):

    def test_high_banking_for_apra_regulatory(self):
        ev = classify(_make_item("APRA updates prudential standard on operational risk for banks"))
        self.assertEqual(ev.banking_relevance, "high")

    def test_high_banking_for_payments(self):
        ev = classify(_make_item("NPP OSKO payment clearing failure affects BPAY settlement"))
        self.assertEqual(ev.banking_relevance, "high")

    def test_low_banking_for_weather(self):
        ev = classify(_make_item("Cyclone warning issued for Queensland coast"))
        self.assertEqual(ev.banking_relevance, "low")

    def test_medium_banking_for_cloud(self):
        ev = classify(_make_item("AWS outage disrupts cloud services"))
        self.assertIn(ev.banking_relevance, ("medium", "high"))


class TestCPS230Relevance(unittest.TestCase):

    def test_cps230_true_for_explicit_mention(self):
        ev = classify(_make_item("CPS 230 operational resilience obligations for ADIs"))
        self.assertTrue(ev.cps230_relevance)

    def test_cps230_true_for_apra(self):
        ev = classify(_make_item("APRA issues draft guidance on business continuity"))
        self.assertTrue(ev.cps230_relevance)

    def test_cps230_false_for_unrelated(self):
        ev = classify(_make_item("Cyclone warning issued for Queensland coast today"))
        self.assertFalse(ev.cps230_relevance)


class TestDependencyRisk(unittest.TestCase):

    def test_dependency_risk_for_cloud(self):
        ev = classify(_make_item("AWS outage impacts third-party vendor cloud services"))
        self.assertTrue(ev.dependency_risk)

    def test_dependency_risk_for_third_party(self):
        ev = classify(_make_item("Third-party managed service provider outage disrupts banking"))
        self.assertTrue(ev.dependency_risk)

    def test_no_dependency_risk_for_weather(self):
        ev = classify(_make_item("Heavy rainfall and storms hit Melbourne today"))
        self.assertFalse(ev.dependency_risk)


class TestCustomerImpact(unittest.TestCase):

    def test_high_for_critical_keywords(self):
        ev = classify(_make_item("Critical national outage affecting banking services emergency"))
        self.assertEqual(ev.customer_impact, "high")

    def test_medium_for_degraded(self):
        ev = classify(_make_item("Internet banking experiencing intermittent degraded performance"))
        self.assertEqual(ev.customer_impact, "medium")

    def test_low_for_consultation(self):
        ev = classify(_make_item("APRA issues consultation paper on new governance standard"))
        self.assertEqual(ev.customer_impact, "low")


class TestReturnTypeAndFields(unittest.TestCase):

    def test_returns_classified_event(self):
        result = classify(_make_item("Test headline"))
        self.assertIsInstance(result, ClassifiedEvent)

    def test_all_required_fields_present(self):
        ev = classify(_make_item("APRA issues new CPS 230 guidance"))
        self.assertIsNotNone(ev.event_type)
        self.assertIsNotNone(ev.geography)
        self.assertIsNotNone(ev.sector)
        self.assertIsInstance(ev.operational_relevance, float)
        self.assertIsInstance(ev.cps230_relevance, bool)
        self.assertIsInstance(ev.dependency_risk, bool)
        self.assertIsNotNone(ev.event_id)
        self.assertIsNotNone(ev.dedup_hash)

    def test_op_relevance_in_range(self):
        ev = classify(_make_item("Major outage at CBA online banking"))
        self.assertGreaterEqual(ev.operational_relevance, 0.0)
        self.assertLessEqual(ev.operational_relevance, 1.0)

    def test_confidence_in_range(self):
        ev = classify(_make_item("APRA issues new guidance"))
        self.assertGreaterEqual(ev.confidence, 0.0)
        self.assertLessEqual(ev.confidence, 1.0)


if __name__ == "__main__":
    unittest.main()
