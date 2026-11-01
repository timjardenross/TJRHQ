"""
Tests for Phase 3 of docs/self-improvement/HQ-EVOLUTION-SOURCE-EXPANSION.md:
the MCP registry adapter, the vendor-changelog reuse adapter (reads
intelligence_events rather than adding a second fetcher), and the
deps.dev/Scorecard/Semantic Scholar supply-chain evidence enrichment.

Same bare-sibling-import convention as tests/test_hq_evolution.py.
"""

import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
SELF_IMPROVEMENT_DIR = REPO_ROOT / "scripts" / "self_improvement"
sys.path.insert(0, str(SELF_IMPROVEMENT_DIR))

import external_enrichment
from sources import deps_dev as sources_deps_dev
from sources import mcp_registry as sources_mcp_registry
from sources import scorecard as sources_scorecard
from sources import semantic_scholar as sources_semantic_scholar
from sources import vendor_changelog as sources_vendor_changelog


class _FakeResponse:
    def __init__(self, body):
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestMCPRegistryAdapter(unittest.TestCase):
    def test_entry_with_repository_becomes_candidate(self):
        topic = {"id": "mcp-integrations", "why_relevant": "x", "gap_hypothesis": "g"}
        payload = {"servers": [{"server": {
            "name": "com.example/thing", "description": "does a thing",
            "repository": {"url": "https://github.com/example/thing"}, "version": "1.0.0",
        }}]}
        with patch("sources.common.urllib.request.urlopen", return_value=_FakeResponse(payload)):
            candidates = sources_mcp_registry.search(query="thing", topic=topic, max_per_search=5, timeout=8, retrieved_at="2026-09-26T00:00:00Z")
        self.assertEqual(len(candidates), 1)
        c = candidates[0]
        self.assertEqual(c["title"], "com.example/thing")
        self.assertEqual(c["source"], "https://github.com/example/thing")
        self.assertEqual(c["provenance"][0]["source"], "mcp_registry")

    def test_entry_without_repository_is_skipped(self):
        topic = {"id": "mcp-integrations", "why_relevant": "x"}
        payload = {"servers": [{"server": {"name": "com.example/thing", "description": "d"}}]}
        with patch("sources.common.urllib.request.urlopen", return_value=_FakeResponse(payload)):
            candidates = sources_mcp_registry.search(query="thing", topic=topic, max_per_search=5, timeout=8, retrieved_at="2026-09-26T00:00:00Z")
        self.assertEqual(candidates, [])

    def test_network_failure_degrades_to_empty_list(self):
        topic = {"id": "t1", "why_relevant": "x"}
        with patch("sources.common.urllib.request.urlopen", side_effect=urllib.error.URLError("no network")):
            candidates = sources_mcp_registry.search(query="q", topic=topic, max_per_search=5, timeout=8, retrieved_at="2026-09-26T00:00:00Z")
        self.assertEqual(candidates, [])


class TestVendorChangelogAdapter(unittest.TestCase):
    def test_missing_supabase_config_degrades_to_empty_list_without_a_request(self):
        topic = {"id": "t1", "why_relevant": "x"}
        with patch.dict("os.environ", {}, clear=True), patch("sources.common.urllib.request.urlopen") as mocked:
            candidates = sources_vendor_changelog.search(query="", topic=topic, max_per_search=5, timeout=8, retrieved_at="2026-09-26T00:00:00Z")
        mocked.assert_not_called()
        self.assertEqual(candidates, [])

    def test_returns_candidates_when_configured(self):
        topic = {"id": "t1", "why_relevant": "x"}
        payload = [{"title": "Supabase release notes", "url": "https://supabase.com/changelog", "summary": "s", "source_name": "Supabase Status", "published_at": "2026-09-20T00:00:00Z"}]
        env = {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "key"}
        with patch.dict("os.environ", env, clear=True), patch("sources.common.urllib.request.urlopen", return_value=_FakeResponse(payload)):
            candidates = sources_vendor_changelog.search(query="", topic=topic, max_per_search=5, timeout=8, retrieved_at="2026-09-26T00:00:00Z")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["provenance"][0]["source"], "vendor_changelog")
        self.assertEqual(candidates[0]["source"], "https://supabase.com/changelog")

    def test_non_list_response_degrades_to_empty_list(self):
        topic = {"id": "t1", "why_relevant": "x"}
        env = {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "key"}
        with patch.dict("os.environ", env, clear=True), patch("sources.common.urllib.request.urlopen", return_value=_FakeResponse({"error": "nope"})):
            candidates = sources_vendor_changelog.search(query="", topic=topic, max_per_search=5, timeout=8, retrieved_at="2026-09-26T00:00:00Z")
        self.assertEqual(candidates, [])


class TestDepsDevScorecardSemanticScholar(unittest.TestCase):
    def test_deps_dev_extracts_scorecard_score(self):
        payload = {"openIssuesCount": 5, "starsCount": 100, "forksCount": 10, "license": "MIT",
                   "scorecard": {"overallScore": 8.2}}
        with patch("sources.common.urllib.request.urlopen", return_value=_FakeResponse(payload)):
            evidence = sources_deps_dev.get_evidence("org", "repo", timeout=8)
        self.assertEqual(evidence["scorecard_score"], 8.2)
        self.assertEqual(evidence["license"], "MIT")

    def test_deps_dev_network_failure_returns_none(self):
        with patch("sources.common.urllib.request.urlopen", side_effect=urllib.error.URLError("no network")):
            self.assertIsNone(sources_deps_dev.get_evidence("org", "repo", timeout=8))

    def test_scorecard_extracts_score(self):
        with patch("sources.common.urllib.request.urlopen", return_value=_FakeResponse({"score": 7.5})):
            self.assertEqual(sources_scorecard.get_score("org", "repo", timeout=8), 7.5)

    def test_scorecard_network_failure_returns_none(self):
        with patch("sources.common.urllib.request.urlopen", side_effect=urllib.error.URLError("no network")):
            self.assertIsNone(sources_scorecard.get_score("org", "repo", timeout=8))

    def test_extract_arxiv_id_from_url(self):
        self.assertEqual(sources_semantic_scholar.extract_arxiv_id("http://arxiv.org/abs/2301.12345v2"), "2301.12345")
        self.assertIsNone(sources_semantic_scholar.extract_arxiv_id("https://github.com/org/repo"))

    def test_semantic_scholar_extracts_citation_count(self):
        with patch("sources.common.urllib.request.urlopen", return_value=_FakeResponse({"citationCount": 42})):
            self.assertEqual(sources_semantic_scholar.get_citation_count("2301.12345", timeout=8), 42)

    def test_semantic_scholar_rate_limit_returns_none(self):
        with patch("sources.common.urllib.request.urlopen", side_effect=urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)):
            self.assertIsNone(sources_semantic_scholar.get_citation_count("2301.12345", timeout=8))


class TestApplySupplyChainEvidence(unittest.TestCase):
    def _github_candidate(self, source="https://github.com/org/repo"):
        return {
            "title": "org/repo", "source": source, "discovery_source": "external", "summary": "s",
            "why_relevant": "y", "evidence_strength": "moderate", "confidence": 0.5, "fit": "moderate",
            "value": "medium", "complexity": "moderate",
            "provenance": [{"source": "github", "detail": json.dumps({})}],
        }

    def _arxiv_candidate(self, source="http://arxiv.org/abs/2301.12345"):
        return {
            "title": "A Paper", "source": source, "discovery_source": "external", "summary": "s",
            "why_relevant": "y", "evidence_strength": "weak", "confidence": 0.5, "fit": "moderate",
            "value": "low", "complexity": "high",
            "provenance": [{"source": "arxiv", "detail": json.dumps({})}],
        }

    def test_high_scorecard_score_sets_complexity_low(self):
        c = self._github_candidate()
        with patch("sources.deps_dev.common.get_json", return_value={"scorecard": {"overallScore": 9.0}}):
            external_enrichment.apply_supply_chain_evidence([c], {"max_supply_chain_evidence_per_cycle": 10})
        self.assertEqual(c["complexity"], "low")
        self.assertEqual(c["supply_chain_scorecard_score"], 9.0)

    def test_low_scorecard_score_sets_complexity_high(self):
        c = self._github_candidate()
        with patch("sources.deps_dev.common.get_json", return_value={"scorecard": {"overallScore": 2.0}}):
            external_enrichment.apply_supply_chain_evidence([c], {"max_supply_chain_evidence_per_cycle": 10})
        self.assertEqual(c["complexity"], "high")

    def test_deps_dev_failure_falls_back_to_scorecard_api(self):
        c = self._github_candidate()
        with patch("sources.deps_dev.common.get_json", return_value={"openIssuesCount": 1}), \
             patch("sources.scorecard.common.get_json", return_value={"score": 6.0}):
            external_enrichment.apply_supply_chain_evidence([c], {"max_supply_chain_evidence_per_cycle": 10})
        self.assertEqual(c["complexity"], "moderate")

    def test_deps_dev_total_failure_leaves_candidate_unchanged(self):
        c = self._github_candidate()
        original_complexity = c["complexity"]
        with patch("sources.deps_dev.common.get_json", return_value=None), \
             patch("sources.scorecard.common.get_json", return_value=None):
            external_enrichment.apply_supply_chain_evidence([c], {"max_supply_chain_evidence_per_cycle": 10})
        self.assertEqual(c["complexity"], original_complexity)
        self.assertNotIn("supply_chain_scorecard_score", c)

    def test_high_citation_count_sets_value_high(self):
        c = self._arxiv_candidate()
        with patch("sources.semantic_scholar.common.get_json", return_value={"citationCount": 500}):
            external_enrichment.apply_supply_chain_evidence([c], {"max_supply_chain_evidence_per_cycle": 10})
        self.assertEqual(c["value"], "high")
        self.assertEqual(c["supply_chain_citation_count"], 500)

    def test_low_citation_count_keeps_value_low(self):
        c = self._arxiv_candidate()
        with patch("sources.semantic_scholar.common.get_json", return_value={"citationCount": 2}):
            external_enrichment.apply_supply_chain_evidence([c], {"max_supply_chain_evidence_per_cycle": 10})
        self.assertEqual(c["value"], "low")

    def test_max_calls_bound_is_respected(self):
        candidates = [self._github_candidate(source=f"https://github.com/org/repo{i}") for i in range(5)]
        call_count = {"n": 0}

        def fake_get_json(*a, **k):
            call_count["n"] += 1
            return {"scorecard": {"overallScore": 9.0}}

        with patch("sources.deps_dev.common.get_json", side_effect=fake_get_json):
            external_enrichment.apply_supply_chain_evidence(candidates, {"max_supply_chain_evidence_per_cycle": 2})
        self.assertEqual(call_count["n"], 2)

    def test_dependency_release_candidate_is_skipped_entirely(self):
        c = {
            "title": "pkg 1.0 -> 2.0", "source": "https://pypi.org/project/pkg/", "discovery_source": "external",
            "summary": "s", "why_relevant": "y", "evidence_strength": "strong", "confidence": 0.5, "fit": "moderate",
            "value": "high", "complexity": "low",
            "provenance": [{"source": "dependency_release", "detail": json.dumps({})}],
        }
        with patch("sources.deps_dev.common.get_json") as mocked_deps, \
             patch("sources.semantic_scholar.common.get_json") as mocked_ss:
            external_enrichment.apply_supply_chain_evidence([c], {"max_supply_chain_evidence_per_cycle": 10})
        mocked_deps.assert_not_called()
        mocked_ss.assert_not_called()


class TestEnrichmentDispatchAdditions(unittest.TestCase):
    def _candidate(self, provenance_source: str, **overrides):
        base = {
            "title": "t", "source": "https://example.com/x", "discovery_source": "external",
            "summary": "s", "why_relevant": "y", "evidence_strength": "moderate", "confidence": 0.5,
            "fit": "moderate", "value": "medium", "complexity": "moderate",
            "provenance": [{"source": provenance_source, "detail": json.dumps({})}],
        }
        base.update(overrides)
        return base

    def test_mcp_registry_source_uses_readme_fetcher(self):
        c = self._candidate("mcp_registry", source="https://github.com/org/repo")
        with patch("external_enrichment._fetch_readme_excerpt", return_value="readme") as mocked:
            content = external_enrichment._fetch_content_excerpt(c, max_chars=100, timeout=8)
        mocked.assert_called_once()
        self.assertEqual(content, "readme")

    def test_vendor_changelog_source_returns_none(self):
        c = self._candidate("vendor_changelog")
        self.assertIsNone(external_enrichment._fetch_content_excerpt(c, max_chars=100, timeout=8))


if __name__ == "__main__":
    unittest.main()
