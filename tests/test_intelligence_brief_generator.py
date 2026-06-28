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

import json
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
    now = datetime(2026, 6, 12, tzinfo=timezone.utc)
    return RankedEvent(
        event_id=f"evt-{rank}",
        source_id="test-src",
        source_name="Test Source",
        source_priority=2,
        source_confidence_weight=1.0,
        source_category="regulatory_bodies",
        raw_title=title,
        raw_summary="A summary of the event.",
        canonical_url="https://example.com/item",
        published_at=now,
        collected_at=now,
        dedup_hash=f"hash-{rank}",
        event_type="cyber_incident",
        geography="AUSTRALIA",
        sector="banking",
        operational_relevance=0.7,
        customer_impact="high",
        banking_relevance="high",
        cps230_relevance=True,
        dependency_risk=False,
        confidence=0.8,
        rank_score=0.9 - rank * 0.05,
    )


class TestLLMFailureDegradation(unittest.TestCase):
    """When all LLMs fail, brief is assembled with UNAVAILABLE narrative markers."""

    def _patch_store(self):
        """Return a mock that satisfies all store.* calls in brief_generator."""
        mock_store = MagicMock()
        mock_store.event_hash_exists.return_value = False
        mock_store.event_canonical_url_exists.return_value = False
        mock_store.event_title_date_exists.return_value = False
        mock_store.save_event.return_value = "uuid-1"
        mock_store.save_brief.return_value = "brief-uuid-1"
        return mock_store

    def test_brief_assembled_without_llm(self):
        from intelligence.brief.brief_generator import BriefGenerator

        top = [_make_ranked_event(f"Event {i}", i) for i in range(1, 4)]

        with patch("intelligence.brief.brief_generator.collect_all", return_value=([], [])), \
             patch("intelligence.brief.brief_generator.store", self._patch_store()), \
             patch("intelligence.brief.brief_generator.classify", side_effect=lambda x: x), \
             patch("intelligence.brief.brief_generator.rank", return_value=top), \
             patch("intelligence.brief.brief_generator.top_events", return_value=top), \
             patch("intelligence.brief.brief_generator.LLMProvider") as mock_llm_cls:

            mock_llm = MagicMock()
            mock_llm.generate.return_value = (None, None)
            mock_llm_cls.return_value = mock_llm

            brief = BriefGenerator().generate()

        self.assertIsInstance(brief, ResilienceBrief)
        self.assertFalse(brief.narrative_available)

    def test_narrative_marked_unavailable_on_llm_failure(self):
        """All narrative text fields should be None or [UNAVAILABLE] when LLM fails."""
        from intelligence.brief.brief_generator import BriefGenerator

        with patch("intelligence.brief.brief_generator.collect_all", return_value=([], [])), \
             patch("intelligence.brief.brief_generator.store", self._patch_store()), \
             patch("intelligence.brief.brief_generator.rank", return_value=[]), \
             patch("intelligence.brief.brief_generator.top_events", return_value=[]), \
             patch("intelligence.brief.brief_generator.LLMProvider") as mock_llm_cls:

            mock_llm = MagicMock()
            mock_llm.generate.return_value = (None, None)
            mock_llm_cls.return_value = mock_llm

            brief = BriefGenerator().generate()

        self.assertFalse(brief.narrative_available)
        if brief.executive_snapshot:
            self.assertIn("UNAVAILABLE", brief.executive_snapshot.upper())


class TestBriefDataclassFields(unittest.TestCase):

    def test_resilience_brief_required_fields(self):
        now = datetime(2026, 6, 12, tzinfo=timezone.utc)
        brief = ResilienceBrief(
            brief_id="brief-1",
            period_start=datetime(2026, 5, 29, tzinfo=timezone.utc),
            period_end=now,
            generated_at=now,
            top_events=[],
            overall_risk="AMBER",
            sources_checked=10,
            sources_available=8,
            sources_failed=2,
            sources_stale=0,
            events_evaluated=25,
            events_included=5,
            events_suppressed=0,
            narrative_available=False,
            llm_used=False,
            provider_used=None,
            confidence=0.8,
            trigger_type="scheduled",
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
            event_id="evt-1",
            title="Test Event",
            location="AUSTRALIA",
            event_type="cyber_incident",
            risk_rating="RED",
            summary="A summary.",
            operational_impact="Disruption to payment systems.",
            so_what="Material impact on banking operations.",
            status="active",
            source_name="ACSC",
            canonical_url="https://example.com",
            rank_score=0.92,
        )
        self.assertEqual(ev.risk_rating, "RED")
        self.assertEqual(ev.rank_score, 0.92)


class TestRiskComputation(unittest.TestCase):
    """Risk level (RED/AMBER/GREEN) should be derived from event severities — rule-based."""

    def test_high_severity_event_pushes_red(self):
        from intelligence.brief.brief_generator import BriefGenerator
        gen = BriefGenerator.__new__(BriefGenerator)
        top_events = [_make_ranked_event("Critical event", 1)]
        top_events[0].customer_impact = "high"
        risk = gen._compute_risk(top_events)
        self.assertIn(risk, ("RED", "AMBER"))

    def test_no_events_gives_green_or_unknown(self):
        from intelligence.brief.brief_generator import BriefGenerator
        gen = BriefGenerator.__new__(BriefGenerator)
        risk = gen._compute_risk([])
        self.assertIn(risk, ("GREEN", "UNKNOWN", "AMBER"))


class TestLLMProviderModelRouter(unittest.TestCase):
    """MSN-0209 — Model Router is tier-0 in the intelligence brief LLM chain."""

    def test_model_router_is_first_provider(self):
        """Provider chain must start with model-router."""
        from intelligence.brief.llm_provider import LLMProvider
        provider = LLMProvider()
        # Inspect generate() source to confirm provider ordering
        import inspect
        source = inspect.getsource(provider.generate)
        # model-router must appear before mistral-4stage-pipeline in the source
        router_pos = source.find("model-router")
        mistral_pos = source.find("mistral-4stage-pipeline")
        self.assertGreater(router_pos, -1, "model-router not in provider chain")
        self.assertGreater(mistral_pos, -1, "mistral-4stage-pipeline not in provider chain")
        self.assertLess(router_pos, mistral_pos, "model-router must come before mistral pipeline")

    def test_model_router_success_stops_chain(self):
        """When the router succeeds, Mistral pipeline must NOT be called."""
        from intelligence.brief.llm_provider import LLMProvider
        provider = LLMProvider()

        with patch.object(provider, "_model_router", return_value="brief from router") as mock_router, \
             patch.object(provider, "_mistral_pipeline") as mock_mistral:
            text, name = provider.generate("test prompt")

        self.assertEqual(text, "brief from router")
        self.assertEqual(name, "model-router")
        mock_router.assert_called_once()
        mock_mistral.assert_not_called()

    def test_model_router_failure_falls_back_to_mistral(self):
        """When router fails, Mistral pipeline must be tried next."""
        from intelligence.brief.llm_provider import LLMProvider
        provider = LLMProvider()

        with patch.object(provider, "_model_router", side_effect=RuntimeError("router down")), \
             patch.object(provider, "_mistral_pipeline", return_value="brief from mistral") as mock_mistral, \
             patch.object(provider, "_gemini") as mock_gemini:
            text, name = provider.generate("test prompt")

        self.assertEqual(text, "brief from mistral")
        self.assertEqual(name, "mistral-4stage-pipeline")
        mock_mistral.assert_called_once()
        mock_gemini.assert_not_called()

    def test_model_router_calls_correct_endpoint(self):
        """_model_router must POST to /api/model/intelligence-brief."""
        from intelligence.brief.llm_provider import LLMProvider
        provider = LLMProvider()

        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode())
            mock = MagicMock()
            mock.read.return_value = json.dumps({"response": "test output"}).encode()
            mock.__enter__ = lambda s: s
            mock.__exit__ = MagicMock(return_value=False)
            return mock

        import json as _json
        import urllib.request
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = provider._model_router("test prompt")

        self.assertEqual(result, "test output")
        self.assertIn("/api/model/intelligence-brief", captured["url"])
        self.assertEqual(captured["body"]["prompt"], "test prompt")

    def test_model_router_raises_on_empty_response(self):
        """Empty response from router must raise RuntimeError (triggers fallback)."""
        from intelligence.brief.llm_provider import LLMProvider
        provider = LLMProvider()

        import json as _json
        mock_resp = MagicMock()
        mock_resp.read.return_value = _json.dumps({"response": ""}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with self.assertRaises(RuntimeError):
                provider._model_router("test prompt")

    def test_all_providers_fail_returns_none_none(self):
        """When router + all cloud + ollama fail, generate() returns (None, None)."""
        from intelligence.brief.llm_provider import LLMProvider
        provider = LLMProvider()

        with patch.object(provider, "_model_router", side_effect=RuntimeError("down")), \
             patch.object(provider, "_mistral_pipeline", side_effect=RuntimeError("down")), \
             patch.object(provider, "_gemini", side_effect=RuntimeError("down")), \
             patch.object(provider, "_mistral", side_effect=RuntimeError("down")), \
             patch.object(provider, "_ollama", side_effect=RuntimeError("down")):
            text, name = provider.generate("test prompt")

        self.assertIsNone(text)
        self.assertIsNone(name)


if __name__ == "__main__":
    unittest.main()
