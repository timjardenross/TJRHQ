"""
Unit tests for intelligence/brief/external_domains.py — the decoupled
Health OSINT / Emergency Alert Hub integration (BRIEFS_CANONICAL_UPLIFT.md
§4.1).

Covers:
- "queried, found nothing" vs "could not query" must never be conflated
  (Section 30: no missing coverage is interpreted as nothing happened).
- Domain semantics/provenance are preserved (severity mapping, source
  attribution, verbatim official emergency wording).
- domain_picture.py buckets external signals without fabricating domains
  absent from the input.
- Cross-domain rendering consistency: render.py's canonical selection
  still can't drift once domain_picture/coverage carry health/emergency
  content — Telegram and Captain's Chair still agree with each other and
  with the brief.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.brief import external_domains
from intelligence.brief.domain_picture import compute_domain_picture
from intelligence.brief.render import build_morning_intelligence_view


class TestHealthSignalFetch(unittest.TestCase):

    def test_no_events_is_available_true_empty_list(self):
        """A genuinely quiet morning: the query succeeds and finds nothing."""
        with patch("intelligence.brief.external_domains.store.load_assessed_health_signals", return_value=[]):
            result = external_domains.fetch_health_signals()
        self.assertTrue(result.available)
        self.assertEqual(result.signals, [])
        self.assertIsNone(result.error)

    def test_fetch_failure_is_available_false_not_empty_list(self):
        """A fetch failure must never look identical to 'nothing happened'."""
        with patch("intelligence.brief.external_domains.store.load_assessed_health_signals",
                   side_effect=RuntimeError("Supabase down")):
            result = external_domains.fetch_health_signals()
        self.assertFalse(result.available)
        self.assertEqual(result.signals, [])
        self.assertIn("Supabase down", result.error)

    def test_severity_mapping_preserves_domain_semantics(self):
        rows = [
            {"title": "Adverse event cluster", "description": "desc", "severity": "critical",
             "confidence_level": "HIGH", "collected_at": "2026-09-06T01:00:00Z",
             "health_source_registry": {"source_name": "FDA MedWatch"}},
            {"title": "Minor supplement finding", "description": None, "severity": "mild",
             "confidence_level": "LOW", "collected_at": "2026-09-06T01:00:00Z",
             "health_source_registry": {}},
        ]
        with patch("intelligence.brief.external_domains.store.load_assessed_health_signals", return_value=rows):
            result = external_domains.fetch_health_signals()
        self.assertTrue(result.available)
        self.assertEqual(len(result.signals), 2)
        critical, mild = result.signals
        self.assertEqual(critical.risk_rating, "RED")
        self.assertEqual(critical.source_name, "FDA MedWatch")  # provenance preserved
        self.assertEqual(critical.domain, "health")
        self.assertEqual(mild.risk_rating, "GREEN")

    def test_unclassified_severity_does_not_silently_default_green(self):
        rows = [{"title": "Signal", "description": None, "severity": "",
                 "confidence_level": "HIGH", "collected_at": "2026-09-06T01:00:00Z"}]
        with patch("intelligence.brief.external_domains.store.load_assessed_health_signals", return_value=rows):
            result = external_domains.fetch_health_signals()
        self.assertEqual(result.signals[0].risk_rating, "AMBER")


class TestEmergencyAlertFetch(unittest.TestCase):

    def test_no_active_alerts_is_available_true_empty_list(self):
        with patch("intelligence.brief.external_domains.store.load_active_emergency_alerts", return_value=[]):
            result = external_domains.fetch_emergency_alerts()
        self.assertTrue(result.available)
        self.assertEqual(result.signals, [])

    def test_fetch_failure_is_available_false(self):
        with patch("intelligence.brief.external_domains.store.load_active_emergency_alerts",
                   side_effect=RuntimeError("timeout")):
            result = external_domains.fetch_emergency_alerts()
        self.assertFalse(result.available)
        self.assertIn("timeout", result.error)

    def test_official_wording_preserved_verbatim(self):
        """Section 30: no hidden replacement of official emergency wording."""
        rows = [{"headline": "Emergency Warning: Bushfire approaching Smithville",
                 "jurisdiction": "NSW", "severity": "emergency_warning",
                 "location": "Smithville", "last_seen_at": "2026-09-06T01:00:00Z",
                 "canonical_url": "https://example.gov.au/alert/1"}]
        with patch("intelligence.brief.external_domains.store.load_active_emergency_alerts", return_value=rows):
            result = external_domains.fetch_emergency_alerts()
        signal = result.signals[0]
        self.assertEqual(signal.title, "Emergency Warning: Bushfire approaching Smithville")
        self.assertEqual(signal.official_severity_label, "Emergency Warning")
        self.assertEqual(signal.risk_rating, "RED")
        self.assertEqual(signal.source_name, "NSW")

    def test_unknown_severity_is_amber_not_hidden_as_green(self):
        rows = [{"headline": "Unclassified incident", "jurisdiction": "VIC", "severity": "unknown",
                 "location": None, "last_seen_at": "2026-09-06T01:00:00Z"}]
        with patch("intelligence.brief.external_domains.store.load_active_emergency_alerts", return_value=rows):
            result = external_domains.fetch_emergency_alerts()
        self.assertEqual(result.signals[0].risk_rating, "AMBER")


class TestDomainPictureCrossDomain(unittest.TestCase):

    def _osint_event(self, title, event_type="cyber", risk="AMBER"):
        return {"title": title, "event_type": event_type, "risk_rating": risk}

    def _external(self, domain, title, risk):
        return {"domain": domain, "title": title, "risk_rating": risk}

    def test_no_input_at_all_returns_none(self):
        self.assertIsNone(compute_domain_picture([], []))
        self.assertIsNone(compute_domain_picture(None, None))

    def test_external_only_still_produces_a_picture(self):
        """OSINT can be empty while Health/Emergency still have material
        content — the picture must not disappear just because top_events did."""
        picture = compute_domain_picture([], [self._external("health", "Adverse event cluster", "RED")])
        self.assertIsNotNone(picture)
        self.assertIn("health", picture)
        self.assertEqual(picture["health"]["worst_risk"], "RED")

    def test_health_and_emergency_bucket_correctly_alongside_osint(self):
        picture = compute_domain_picture(
            [self._osint_event("Cyber incident", "cyber", "AMBER")],
            [
                self._external("health", "Adverse event cluster", "RED"),
                self._external("emergency", "Bushfire warning", "RED"),
            ],
        )
        self.assertEqual(set(picture.keys()), {"technical", "health", "emergency"})
        self.assertEqual(picture["health"]["label"], "Health")
        self.assertEqual(picture["emergency"]["label"], "Emergency Alerts")

    def test_does_not_fabricate_domains_absent_from_both_inputs(self):
        picture = compute_domain_picture([self._osint_event("Cyber incident")], [])
        self.assertNotIn("health", picture)
        self.assertNotIn("emergency", picture)


class TestCrossDomainRenderingConsistency(unittest.TestCase):
    """Section 29 extended: once a brief carries cross-domain content
    (domain_picture/coverage now spanning health/emergency), Telegram and
    Captain's Chair must still select identically from it and invent
    nothing beyond it."""

    def _brief_with_cross_domain_content(self):
        return {
            "brief_id": "b-1",
            "generated_at": "2026-09-06T06:31:00+10:00",
            "overall_risk": "RED",
            "executive_snapshot": "A bushfire emergency warning is active near Smithville.",
            "top_events": [
                {"title": "Cloud provider outage", "so_what": "Check dependency exposure.", "risk_rating": "AMBER"},
            ],
            "forward_watch": ["Bushfire containment progress"],
            "comparison": None,
            "coverage": {
                "degraded": False,
                "missing_sources": [],
                "domains": {"health": {"available": True, "count": 0}, "emergency": {"available": True, "count": 1}},
            },
            "domain_picture": {
                "technical": {"label": "Technical", "count": 1, "worst_risk": "AMBER", "events": []},
                "emergency": {"label": "Emergency Alerts", "count": 1, "worst_risk": "RED",
                              "events": [{"title": "Emergency Warning: Bushfire near Smithville", "risk_rating": "RED"}]},
            },
        }

    def test_telegram_and_captains_chair_agree_on_cross_domain_brief(self):
        from intelligence.brief.render import render_captains_excerpt
        brief = self._brief_with_cross_domain_content()
        telegram_view = build_morning_intelligence_view(brief)
        chair_view = render_captains_excerpt(brief)
        self.assertEqual(telegram_view, chair_view)
        self.assertEqual(telegram_view["overall_risk"], "RED")

    def test_render_view_never_reaches_into_domain_picture_to_invent_content(self):
        """render.py's selection is built only from top_events/comparison/
        coverage/forward_watch — it must not independently re-derive a
        narrative from domain_picture (that would be a second interpretive
        step; domain_picture is deterministic grouping for display, not a
        second source of truth for 'what matters')."""
        brief = self._brief_with_cross_domain_content()
        view = build_morning_intelligence_view(brief)
        rendered_titles = {item["title"] for item in view["what_matters"]}
        # Only the OSINT top_events title should surface in what_matters —
        # the emergency item lives in domain_picture, a separate detail-page
        # concern, not duplicated into the terse what-matters selection.
        self.assertEqual(rendered_titles, {"Cloud provider outage"})

    def test_degraded_domain_availability_surfaces_as_coverage_note(self):
        brief = self._brief_with_cross_domain_content()
        brief["coverage"] = {
            "degraded": True, "missing_sources": ["Health OSINT"],
            "domains": {"health": {"available": False, "count": 0, "error": "timeout"}},
        }
        view = build_morning_intelligence_view(brief)
        self.assertTrue(view["coverage_degraded"])
        self.assertIn("unavailable", view["coverage_note"])


if __name__ == "__main__":
    unittest.main()
