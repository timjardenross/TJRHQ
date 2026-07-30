"""
Unit tests for intelligence/classification/filter.py

Covers:
- Title too short → suppress
- Opinion/analysis signal → suppress
- Generic news → suppress
- Low operational relevance → suppress
- Media source (priority >= 4) + low relevance → suppress
- High-relevance events pass through
- Returns (bool, str) tuple
"""

import sys
import os
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.classification.filter import should_suppress, apply_filter
from intelligence.models import ClassifiedEvent


def _make_event(
    title: str = "APRA updates CPS 230 operational resilience guidelines",
    operational_relevance: float = 0.55,
    banking_relevance: str = "high",
    cps230_relevance: bool = True,
    source_priority: int = 2,
    suppressed: bool = False,
) -> ClassifiedEvent:
    return ClassifiedEvent(
        event_id="test-uuid",
        source_id="test-src",
        source_name="Test Source",
        source_priority=source_priority,
        source_confidence_weight=0.8,
        source_category="media",
        raw_title=title,
        raw_summary="",
        canonical_url="https://example.com/item",
        published_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
        collected_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
        dedup_hash="aabbcc",
        event_type="regulatory",
        geography="AU",
        sector="financial_services",
        operational_relevance=operational_relevance,
        customer_impact="low",
        banking_relevance=banking_relevance,
        cps230_relevance=cps230_relevance,
        dependency_risk=False,
        confidence=0.8,
        suppressed=suppressed,
    )


class TestReturnType(unittest.TestCase):

    def test_returns_tuple(self):
        result = should_suppress(_make_event())
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_first_element_bool(self):
        suppressed, _ = should_suppress(_make_event())
        self.assertIsInstance(suppressed, bool)

    def test_second_element_str(self):
        _, reason = should_suppress(_make_event())
        self.assertIsInstance(reason, str)


class TestTitleTooShort(unittest.TestCase):

    def test_short_title_suppressed(self):
        ev = _make_event(title="OK")
        suppressed, reason = should_suppress(ev)
        self.assertTrue(suppressed)
        self.assertIn("short", reason)

    def test_adequate_title_not_suppressed_on_length(self):
        ev = _make_event(title="APRA issues updated CPS 230 guidance for ADIs today")
        suppressed, reason = should_suppress(ev)
        if suppressed:
            self.assertNotIn("short", reason)


class TestOpinionSignal(unittest.TestCase):

    def test_opinion_prefix_suppressed(self):
        ev = _make_event(title="Opinion: Why the banks are wrong about CPS 230")
        suppressed, reason = should_suppress(ev)
        self.assertTrue(suppressed)
        self.assertIn("opinion", reason)

    def test_analysis_prefix_suppressed(self):
        ev = _make_event(title="Analysis: What rising rates mean for the housing market")
        suppressed, reason = should_suppress(ev)
        self.assertTrue(suppressed)


class TestGenericNews(unittest.TestCase):

    def test_podcast_suppressed(self):
        ev = _make_event(title="Listen: the podcast about banking regulation today")
        suppressed, reason = should_suppress(ev)
        self.assertTrue(suppressed)
        self.assertIn("generic_news", reason)

    def test_gallery_suppressed(self):
        ev = _make_event(title="Gallery: photos from the RBA press conference")
        suppressed, reason = should_suppress(ev)
        self.assertTrue(suppressed)


class TestLowOperationalRelevance(unittest.TestCase):

    def test_below_floor_suppressed(self):
        ev = _make_event(operational_relevance=0.10)
        suppressed, _ = should_suppress(ev)
        self.assertTrue(suppressed)

    def test_above_floor_not_suppressed(self):
        ev = _make_event(operational_relevance=0.55, banking_relevance="high", cps230_relevance=True)
        suppressed, _ = should_suppress(ev)
        self.assertFalse(suppressed)


class TestMediaSourceFilter(unittest.TestCase):

    def test_media_source_low_relevance_suppressed(self):
        ev = _make_event(source_priority=4, banking_relevance="low", cps230_relevance=False,
                         operational_relevance=0.25)
        suppressed, reason = should_suppress(ev)
        self.assertTrue(suppressed)
        self.assertIn("media_source", reason)

    def test_media_source_with_banking_relevance_passes(self):
        ev = _make_event(source_priority=4, banking_relevance="high", cps230_relevance=False,
                         operational_relevance=0.25)
        suppressed, _ = should_suppress(ev)
        self.assertFalse(suppressed)

    def test_media_source_with_cps230_passes(self):
        ev = _make_event(source_priority=4, banking_relevance="low", cps230_relevance=True,
                         operational_relevance=0.25)
        suppressed, _ = should_suppress(ev)
        self.assertFalse(suppressed)


class TestHighRelevancePasses(unittest.TestCase):

    def test_apra_regulatory_passes(self):
        ev = _make_event(
            title="APRA finalises CPS 230 operational resilience standard for ADIs",
            operational_relevance=0.80,
            banking_relevance="high",
            cps230_relevance=True,
        )
        suppressed, _ = should_suppress(ev)
        self.assertFalse(suppressed)

    def test_cyber_banking_passes(self):
        ev = _make_event(
            title="Ransomware attack disrupts CBA internet banking for 3 hours",
            operational_relevance=0.75,
            banking_relevance="high",
            cps230_relevance=False,
        )
        suppressed, _ = should_suppress(ev)
        self.assertFalse(suppressed)


class TestApplyFilter(unittest.TestCase):

    def test_apply_filter_updates_in_place(self):
        events = [
            _make_event(title="OK"),  # too short → suppressed
            _make_event(title="APRA finalises CPS 230 operational resilience standard"),  # passes
        ]
        result = apply_filter(events)
        self.assertTrue(result[0].suppressed)
        self.assertFalse(result[1].suppressed)

    def test_apply_filter_returns_full_list(self):
        events = [_make_event(), _make_event(title="X")]
        result = apply_filter(events)
        self.assertEqual(len(result), len(events))

    def test_already_suppressed_not_double_processed(self):
        ev = _make_event(suppressed=True)
        ev.suppression_reason = "already_set"
        events = apply_filter([ev])
        self.assertEqual(events[0].suppression_reason, "already_set")


if __name__ == "__main__":
    unittest.main()
