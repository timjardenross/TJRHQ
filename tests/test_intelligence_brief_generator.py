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

from intelligence.brief.external_domains import DomainFetchResult
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
        # Briefs canonical uplift: generate() also asks for the prior brief
        # to compute a current-vs-prior comparison — None means "no prior
        # brief", same as a fresh Supabase table.
        mock_store.load_latest_brief.return_value = None
        return mock_store

    def test_brief_assembled_without_llm(self):
        from intelligence.brief.brief_generator import BriefGenerator

        top = [_make_ranked_event(f"Event {i}", i) for i in range(1, 4)]

        with patch("intelligence.brief.brief_generator.collect_all", return_value=([], [])), \
             patch("intelligence.brief.brief_generator.store", self._patch_store()), \
             patch("intelligence.brief.brief_generator.classify", side_effect=lambda x: x), \
             patch("intelligence.brief.brief_generator.rank", return_value=top), \
             patch("intelligence.brief.brief_generator.top_events", return_value=top), \
             patch("intelligence.brief.brief_generator.morning_cycle.get_status", return_value=None), \
             patch("intelligence.brief.brief_generator.external_domains.fetch_health_signals",
                   return_value=DomainFetchResult(domain="health", available=True, signals=[])), \
             patch("intelligence.brief.brief_generator.external_domains.fetch_emergency_alerts",
                   return_value=DomainFetchResult(domain="emergency", available=True, signals=[])), \
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
             patch("intelligence.brief.brief_generator.morning_cycle.get_status", return_value=None), \
             patch("intelligence.brief.brief_generator.external_domains.fetch_health_signals",
                   return_value=DomainFetchResult(domain="health", available=True, signals=[])), \
             patch("intelligence.brief.brief_generator.external_domains.fetch_emergency_alerts",
                   return_value=DomainFetchResult(domain="emergency", available=True, signals=[])), \
             patch("intelligence.brief.brief_generator.LLMProvider") as mock_llm_cls:

            mock_llm = MagicMock()
            mock_llm.generate.return_value = (None, None)
            mock_llm_cls.return_value = mock_llm

            brief = BriefGenerator().generate()

        self.assertFalse(brief.narrative_available)
        if brief.executive_snapshot:
            self.assertIn("UNAVAILABLE", brief.executive_snapshot.upper())


class TestCrossDomainIntegration(unittest.TestCase):
    """Full generate() pipeline coverage for BRIEFS_CANONICAL_UPLIFT.md §4.1
    — Health OSINT / Emergency Alert Hub folded into the one synthesis
    step, without a second LLM call or coupling to either pipeline."""

    def _patch_store(self):
        mock_store = MagicMock()
        mock_store.event_hash_exists.return_value = False
        mock_store.event_canonical_url_exists.return_value = False
        mock_store.event_title_date_exists.return_value = False
        mock_store.save_event.return_value = "uuid-1"
        mock_store.save_brief.return_value = "brief-uuid-1"
        mock_store.load_latest_brief.return_value = None
        return mock_store

    def test_coverage_distinguishes_no_signals_from_unavailable_domain(self):
        """One domain genuinely quiet (available, zero signals), the other
        genuinely unreachable (unavailable) — coverage must tell them apart,
        never treat a fetch failure as if nothing happened."""
        from intelligence.brief.brief_generator import BriefGenerator
        from intelligence.brief.external_domains import DomainFetchResult

        with patch("intelligence.brief.brief_generator.collect_all", return_value=([], [])), \
             patch("intelligence.brief.brief_generator.store", self._patch_store()), \
             patch("intelligence.brief.brief_generator.rank", return_value=[]), \
             patch("intelligence.brief.brief_generator.top_events", return_value=[]), \
             patch("intelligence.brief.brief_generator.morning_cycle.get_status", return_value=None), \
             patch("intelligence.brief.brief_generator.external_domains.fetch_health_signals",
                   return_value=DomainFetchResult(domain="health", available=True, signals=[])), \
             patch("intelligence.brief.brief_generator.external_domains.fetch_emergency_alerts",
                   return_value=DomainFetchResult(domain="emergency", available=False, signals=[],
                                                   error="timeout")), \
             patch("intelligence.brief.brief_generator.LLMProvider") as mock_llm_cls:

            mock_llm = MagicMock()
            mock_llm.generate.return_value = (None, None)
            mock_llm_cls.return_value = mock_llm

            brief = BriefGenerator().generate()

        self.assertTrue(brief.coverage["domains"]["health"]["available"])
        self.assertEqual(brief.coverage["domains"]["health"]["count"], 0)
        self.assertFalse(brief.coverage["domains"]["emergency"]["available"])
        self.assertTrue(brief.coverage["degraded"])
        self.assertIn("Emergency Alert Hub", brief.coverage["missing_sources"])
        self.assertNotIn("Health OSINT", brief.coverage["missing_sources"])

    def test_overall_risk_floors_to_external_signal_when_osint_empty(self):
        """No OSINT events today, but an active RED emergency alert — the
        brief must not report UNKNOWN and hide it."""
        from intelligence.brief.brief_generator import BriefGenerator
        from intelligence.brief.external_domains import DomainFetchResult, ExternalDomainSignal

        red_alert = ExternalDomainSignal(
            domain="emergency", title="Emergency Warning: Bushfire", summary=None,
            risk_rating="RED", source_name="NSW", assessed_at="2026-09-06T01:00:00Z",
            official_severity_label="Emergency Warning",
        )

        with patch("intelligence.brief.brief_generator.collect_all", return_value=([], [])), \
             patch("intelligence.brief.brief_generator.store", self._patch_store()), \
             patch("intelligence.brief.brief_generator.rank", return_value=[]), \
             patch("intelligence.brief.brief_generator.top_events", return_value=[]), \
             patch("intelligence.brief.brief_generator.morning_cycle.get_status", return_value=None), \
             patch("intelligence.brief.brief_generator.external_domains.fetch_health_signals",
                   return_value=DomainFetchResult(domain="health", available=True, signals=[])), \
             patch("intelligence.brief.brief_generator.external_domains.fetch_emergency_alerts",
                   return_value=DomainFetchResult(domain="emergency", available=True, signals=[red_alert])), \
             patch("intelligence.brief.brief_generator.LLMProvider") as mock_llm_cls:

            mock_llm = MagicMock()
            mock_llm.generate.return_value = (None, None)
            mock_llm_cls.return_value = mock_llm

            brief = BriefGenerator().generate()

        self.assertEqual(brief.overall_risk, "RED")
        self.assertIn("emergency", brief.domain_picture)

    def test_narrative_still_generated_when_only_external_domains_have_content(self):
        """The narrative gate must not skip generation just because OSINT's
        top_events list is empty — a single synthesis call still runs."""
        from intelligence.brief.brief_generator import BriefGenerator
        from intelligence.brief.external_domains import DomainFetchResult, ExternalDomainSignal

        signal = ExternalDomainSignal(
            domain="health", title="Adverse event cluster", summary="desc",
            risk_rating="AMBER", source_name="FDA", assessed_at="2026-09-06T01:00:00Z",
        )

        with patch("intelligence.brief.brief_generator.collect_all", return_value=([], [])), \
             patch("intelligence.brief.brief_generator.store", self._patch_store()), \
             patch("intelligence.brief.brief_generator.rank", return_value=[]), \
             patch("intelligence.brief.brief_generator.top_events", return_value=[]), \
             patch("intelligence.brief.brief_generator.morning_cycle.get_status", return_value=None), \
             patch("intelligence.brief.brief_generator.external_domains.fetch_health_signals",
                   return_value=DomainFetchResult(domain="health", available=True, signals=[signal])), \
             patch("intelligence.brief.brief_generator.external_domains.fetch_emergency_alerts",
                   return_value=DomainFetchResult(domain="emergency", available=True, signals=[])), \
             patch("intelligence.brief.brief_generator.LLMProvider") as mock_llm_cls:

            mock_llm = MagicMock()
            mock_llm.generate.return_value = (None, None)
            mock_llm_cls.return_value = mock_llm

            BriefGenerator().generate()

        # The one synthesis call (_generate_narrative -> self.llm.generate)
        # must have run — not skipped — even with zero OSINT top_events.
        # (_generate_so_whats also calls .generate but only when `top` is
        # non-empty, which it isn't here, so any call recorded is the
        # narrative step.)
        self.assertTrue(mock_llm.generate.called)
        prompt_arg = mock_llm.generate.call_args[0][0]
        self.assertIn("Adverse event cluster", prompt_arg)
        self.assertIn("(none collected this period)", prompt_arg)


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


class TestMistralPipelineStages(unittest.TestCase):
    """Stage 1 (Research Scout) and Stage 1b (Engineering Officer) run in
    parallel — they both read the same pre-Stage-1 input, not each other's
    output, so there's no reason to force them sequential. Verifies the
    concurrency doesn't change the pipeline's observable behavior."""

    def _provider_with_agents_configured(self, *, engineering: bool):
        from intelligence.brief import llm_provider as lp
        provider = lp.LLMProvider()
        patches = [
            patch.object(lp, "MISTRAL_API_KEY", "fake-key"),
            patch.object(lp, "MISTRAL_RESEARCH_AGENT_ID", "research-agent"),
            patch.object(lp, "MISTRAL_RESEARCH_AGENT_VERSION", "1"),
            patch.object(lp, "MISTRAL_BRIEFING_AGENT_ID", "briefing-agent"),
            patch.object(lp, "MISTRAL_BRIEFING_AGENT_VERSION", "1"),
            patch.object(lp, "MISTRAL_DECOMPOSITION_AGENT_ID", ""),
            patch.object(lp, "MISTRAL_TAO_AGENT_ID", ""),
            patch.object(lp, "MISTRAL_ENGINEERING_AGENT_ID", "engineering-agent" if engineering else ""),
            patch.object(lp, "MISTRAL_ENGINEERING_AGENT_VERSION", "1"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return provider

    def test_stage1_and_stage1b_both_run_and_merge_when_engineering_present(self):
        provider = self._provider_with_agents_configured(engineering=True)

        def fake_call_agent(stage, agent_id, agent_version, prompt, client=None):
            return {
                "stage1-research": "research findings",
                "stage1b-engineering": "engineering notes",
                "stage4-briefing": "final brief",
            }[stage]

        with patch.object(provider, "_call_agent", side_effect=fake_call_agent) as mock_call:
            result = provider._mistral_pipeline("Engineering: something broke")

        self.assertEqual(result, "final brief")
        called_stages = {c.kwargs["stage"] for c in mock_call.call_args_list}
        self.assertIn("stage1-research", called_stages)
        self.assertIn("stage1b-engineering", called_stages)
        # Stage 4's prompt must have received both Stage 1's and Stage 1b's output.
        stage4_call = next(c for c in mock_call.call_args_list if c.kwargs["stage"] == "stage4-briefing")
        self.assertIn("research findings", stage4_call.kwargs["prompt"])
        self.assertIn("engineering notes", stage4_call.kwargs["prompt"])

    def test_stage1b_skipped_without_engineering_content(self):
        provider = self._provider_with_agents_configured(engineering=True)

        def fake_call_agent(stage, agent_id, agent_version, prompt, client=None):
            return {"stage1-research": "research findings", "stage4-briefing": "final brief"}[stage]

        with patch.object(provider, "_call_agent", side_effect=fake_call_agent) as mock_call:
            result = provider._mistral_pipeline("no engineering content here")

        self.assertEqual(result, "final brief")
        called_stages = {c.kwargs["stage"] for c in mock_call.call_args_list}
        self.assertNotIn("stage1b-engineering", called_stages)

    def test_stage1b_failure_does_not_block_pipeline(self):
        provider = self._provider_with_agents_configured(engineering=True)

        def fake_call_agent(stage, agent_id, agent_version, prompt, client=None):
            return {
                "stage1-research": "research findings",
                "stage1b-engineering": None,  # simulates the agent failing
                "stage4-briefing": "final brief",
            }[stage]

        with patch.object(provider, "_call_agent", side_effect=fake_call_agent):
            result = provider._mistral_pipeline("Engineering: something broke")

        self.assertEqual(result, "final brief")


if __name__ == "__main__":
    unittest.main()
