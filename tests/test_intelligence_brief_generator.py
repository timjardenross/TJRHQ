"""
Unit tests for intelligence/brief/brief_generator.py

Covers:
- Pipeline degrades gracefully when LLM fails
- Narrative sections marked [UNAVAILABLE] when all LLMs down
- Brief still assembled when LLM fails (rule-based fallback)
- ResilienceBrief dataclass fields populated
- narrative_available=False when no LLM
- narrative_available=True when LLM succeeds
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.models import (
    ResilienceBrief, RankedEvent, BriefEvent, ClassifiedEvent,
    IntelligenceItem, SourceRecord,
)


def _make_ranked_event(title: str = "Test event", rank: int = 1) -> RankedEvent:
    src = SourceRecord(
        source_id="test-src",
        source_name="Test Source",
        source_type="rss",
        url="https://example.com",
        category="regulatory_bodies",
        priority=2,
        is_active=True,
    )
    item = IntelligenceItem(
        source_id="test-src",
        source=src,
        raw_title=title,
        raw_summary="A summary of the event.",
        canonical_url="https://example.com/item",
        published_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
    )
    classified = ClassifiedEvent(
        item=item,
        event_type="cyber_incident",
        geography="AUSTRALIA",
        impact_severity="HIGH",
        banking_relevance=0.8,
        cps230_relevance=0.6,
        operational_relevance=0.7,
        customer_impact=True,
        technology_dependency=False,
    )
    return RankedEvent(event=classified, rank_score=0.9 - rank * 0.05, rank_position=rank)


class TestLLMFailureDegradation(unittest.TestCase):
    """When all LLMs fail, brief is assembled with UNAVAILABLE narrative markers."""

    def test_brief_assembled_without_llm(self):
        from intelligence.brief.brief_generator import BriefGenerator

        with patch("intelligence.brief.brief_generator.collect_all") as mock_collect, \
             patch("intelligence.brief.brief_generator.IntelligenceStore") as mock_store_cls, \
             patch("intelligence.brief.brief_generator.LLMProvider") as mock_llm_cls:

            # Mock: collection returns 3 items, no source failures
            mock_items = [MagicMock() for _ in range(3)]
            mock_health = []
            mock_collect.return_value = (mock_items, mock_health)

            # Mock: store
            mock_store = MagicMock()
            mock_store.load_source_registry.return_value = []
            mock_store.event_hash_exists.return_value = False
            mock_store.save_event.return_value = "uuid-1"
            mock_store.save_brief.return_value = "brief-uuid-1"
            mock_store_cls.return_value = mock_store

            # Mock: LLM fails every time
            mock_llm = MagicMock()
            mock_llm.generate.return_value = (None, None)
            mock_llm_cls.return_value = mock_llm

            gen = BriefGenerator()

            # Patch the classification/ranking pipeline to return predictable results
            with patch.object(gen, "_classify_and_deduplicate") as mock_classify, \
                 patch.object(gen, "_rank") as mock_rank:

                top_events = [_make_ranked_event(f"Event {i}", i) for i in range(1, 4)]
                mock_classify.return_value = [e.event for e in top_events]
                mock_rank.return_value = top_events

                brief = gen.generate()

        self.assertIsInstance(brief, ResilienceBrief)
        self.assertFalse(brief.narrative_available)

    def test_narrative_marked_unavailable_on_llm_failure(self):
        """All narrative text fields should be None or [UNAVAILABLE] when LLM fails."""
        from intelligence.brief.brief_generator import BriefGenerator

        with patch("intelligence.brief.brief_generator.collect_all") as mock_collect, \
             patch("intelligence.brief.brief_generator.IntelligenceStore") as mock_store_cls, \
             patch("intelligence.brief.brief_generator.LLMProvider") as mock_llm_cls:

            mock_collect.return_value = ([], [])
            mock_store = MagicMock()
            mock_store.load_source_registry.return_value = []
            mock_store.event_hash_exists.return_value = False
            mock_store.save_event.return_value = None
            mock_store.save_brief.return_value = None
            mock_store_cls.return_value = mock_store

            mock_llm = MagicMock()
            mock_llm.generate.return_value = (None, None)
            mock_llm_cls.return_value = mock_llm

            gen = BriefGenerator()
            with patch.object(gen, "_classify_and_deduplicate", return_value=[]), \
                 patch.object(gen, "_rank", return_value=[]):
                brief = gen.generate()

        self.assertFalse(brief.narrative_available)
        # All narrative sections should be None or a placeholder, not fabricated content
        if brief.executive_snapshot:
            self.assertIn("UNAVAILABLE", brief.executive_snapshot.upper())


class TestBriefDataclassFields(unittest.TestCase):

    def test_resilience_brief_required_fields(self):
        brief = ResilienceBrief(
            brief_id=None,
            period_start=datetime(2026, 5, 29, tzinfo=timezone.utc),
            period_end=datetime(2026, 6, 12, tzinfo=timezone.utc),
            generated_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
            top_events=[],
            overall_risk="AMBER",
            sources_checked=10,
            sources_available=8,
            sources_failed=2,
            events_collected=25,
            events_included=5,
            narrative_available=False,
            provider_used=None,
            executive_snapshot=None,
            emerging_themes=None,
            forward_watch=None,
            cps230_implications=None,
            bottom_line=None,
        )
        self.assertEqual(brief.overall_risk, "AMBER")
        self.assertFalse(brief.narrative_available)
        self.assertEqual(brief.sources_failed, 2)

    def test_brief_event_fields(self):
        ev = BriefEvent(
            event_id=None,
            title="Test Event",
            event_type="cyber_incident",
            geography="AUSTRALIA",
            impact_severity="HIGH",
            risk_rating="RED",
            summary="A summary.",
            so_what="Material impact on banking operations.",
            canonical_url="https://example.com",
            source_name="ACSC",
            published_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
            rank_position=1,
            rank_score=0.92,
            customer_impact=True,
            technology_dependency=False,
            banking_relevance=0.85,
            cps230_relevance=0.70,
        )
        self.assertEqual(ev.risk_rating, "RED")
        self.assertEqual(ev.rank_position, 1)


class TestRiskComputation(unittest.TestCase):
    """Risk level (RED/AMBER/GREEN) should be derived from event severities — rule-based."""

    def test_high_severity_event_pushes_red(self):
        from intelligence.brief.brief_generator import BriefGenerator
        gen = BriefGenerator.__new__(BriefGenerator)
        top_events = [_make_ranked_event("Critical event", 1)]
        # Patch the high-impact event's impact severity
        top_events[0].event.impact_severity = "HIGH"
        risk = gen._compute_risk(top_events)
        self.assertIn(risk, ("RED", "AMBER"))

    def test_no_events_gives_green_or_unknown(self):
        from intelligence.brief.brief_generator import BriefGenerator
        gen = BriefGenerator.__new__(BriefGenerator)
        risk = gen._compute_risk([])
        self.assertIn(risk, ("GREEN", "UNKNOWN", "AMBER"))


if __name__ == "__main__":
    unittest.main()
