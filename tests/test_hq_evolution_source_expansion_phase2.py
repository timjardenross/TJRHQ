"""
Tests for Phase 2 of docs/self-improvement/HQ-EVOLUTION-SOURCE-EXPANSION.md:
the sources/ adapter registry (arxiv, hn, hf, github), the `queries`
schema + `github_query` alias, per-source search caps, and per-source
enrichment content fetchers.

Same bare-sibling-import convention as tests/test_hq_evolution.py.
"""

import json
import sys
import unittest
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
SELF_IMPROVEMENT_DIR = REPO_ROOT / "scripts" / "self_improvement"
sys.path.insert(0, str(SELF_IMPROVEMENT_DIR))

import external_discovery
import external_enrichment
from sources import arxiv as sources_arxiv
from sources import hf as sources_hf
from sources import hn as sources_hn

ARXIV_ATOM_NS = "http://www.w3.org/2005/Atom"


def _arxiv_feed(entries: list[dict[str, str]]) -> bytes:
    feed = ET.Element("feed", {"xmlns": ARXIV_ATOM_NS})
    for e in entries:
        entry = ET.SubElement(feed, "entry")
        ET.SubElement(entry, "id").text = e["id"]
        ET.SubElement(entry, "title").text = e["title"]
        ET.SubElement(entry, "summary").text = e.get("summary", "")
    return ET.tostring(feed)


class _FakeResponse:
    def __init__(self, body):
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestArxivAdapter(unittest.TestCase):
    def test_sanitize_query_rewrites_quoted_phrase_as_and(self):
        self.assertEqual(sources_arxiv._sanitize_query('ti:"LLM routing"'), 'ti:(LLM AND routing)')

    def test_sanitize_query_strips_stray_quotes(self):
        self.assertNotIn('"', sources_arxiv._sanitize_query('abs:"model cascade" OR ti:"x"'))

    def test_sanitize_query_leaves_unquoted_query_unchanged(self):
        self.assertEqual(sources_arxiv._sanitize_query("all:electron"), "all:electron")

    def test_search_builds_candidate_from_atom_entry_with_provenance_source_arxiv(self):
        topic = {"id": "model-routing", "class": "architecture", "why_relevant": "x", "gap_hypothesis": "g"}
        feed = _arxiv_feed([{"id": "http://arxiv.org/abs/1234.5678", "title": "  A Great\n  Paper  ", "summary": "An abstract."}])
        with patch("sources.common.urllib.request.urlopen", return_value=_FakeResponse(feed)):
            candidates = sources_arxiv.search(query="ti:routing", topic=topic, max_per_search=5, timeout=8, retrieved_at="2026-09-26T00:00:00Z")
        self.assertEqual(len(candidates), 1)
        c = candidates[0]
        self.assertEqual(c["title"], "A Great Paper")
        self.assertEqual(c["source"], "http://arxiv.org/abs/1234.5678")
        self.assertEqual(c["provenance"][0]["source"], "arxiv")
        self.assertEqual(c["evidence_strength"], "weak")
        self.assertEqual(c["complexity"], "high")
        self.assertEqual(json.loads(c["provenance"][0]["detail"])["abstract"], "An abstract.")

    def test_search_network_failure_degrades_to_empty_list(self):
        topic = {"id": "t1", "why_relevant": "x"}
        with patch("sources.common.urllib.request.urlopen", side_effect=urllib.error.URLError("no network")):
            candidates = sources_arxiv.search(query="q", topic=topic, max_per_search=5, timeout=8, retrieved_at="2026-09-26T00:00:00Z")
        self.assertEqual(candidates, [])

    def test_search_malformed_xml_degrades_to_empty_list(self):
        topic = {"id": "t1", "why_relevant": "x"}
        with patch("sources.common.urllib.request.urlopen", return_value=_FakeResponse(b"not xml <<<")):
            candidates = sources_arxiv.search(query="q", topic=topic, max_per_search=5, timeout=8, retrieved_at="2026-09-26T00:00:00Z")
        self.assertEqual(candidates, [])


class TestHNAdapter(unittest.TestCase):
    def test_value_from_points_thresholds(self):
        self.assertEqual(sources_hn._value_from_points(500), "high")
        self.assertEqual(sources_hn._value_from_points(200), "medium")
        self.assertEqual(sources_hn._value_from_points(199), "low")
        self.assertEqual(sources_hn._value_from_points(0), "low")

    def test_search_uses_story_url_as_canonical_source_for_dedup(self):
        topic = {"id": "t1", "why_relevant": "x"}
        payload = {"hits": [{"objectID": "123", "title": "RouteLLM", "url": "https://github.com/org/routellm", "points": 250, "num_comments": 10}]}
        with patch("sources.common.urllib.request.urlopen", return_value=_FakeResponse(payload)):
            candidates = sources_hn.search(query="router", topic=topic, max_per_search=5, timeout=8, retrieved_at="2026-09-26T00:00:00Z")
        self.assertEqual(candidates[0]["source"], "https://github.com/org/routellm")
        self.assertEqual(candidates[0]["value"], "medium")
        self.assertEqual(candidates[0]["provenance"][0]["source"], "hn")

    def test_search_falls_back_to_hn_thread_url_when_no_story_url(self):
        topic = {"id": "t1", "why_relevant": "x"}
        payload = {"hits": [{"objectID": "999", "title": "Ask HN: routers?", "url": None, "points": 60, "num_comments": 3}]}
        with patch("sources.common.urllib.request.urlopen", return_value=_FakeResponse(payload)):
            candidates = sources_hn.search(query="router", topic=topic, max_per_search=5, timeout=8, retrieved_at="2026-09-26T00:00:00Z")
        self.assertEqual(candidates[0]["source"], "https://news.ycombinator.com/item?id=999")

    def test_fetch_top_comment_strips_html_and_truncates(self):
        payload = {"children": [{"text": "<p>Great point about <i>routing</i></p>"}]}
        with patch("sources.common.urllib.request.urlopen", return_value=_FakeResponse(payload)):
            comment = sources_hn.fetch_top_comment("123", max_chars=100, timeout=8)
        self.assertEqual(comment, "Great point about routing")

    def test_fetch_top_comment_none_when_no_children(self):
        with patch("sources.common.urllib.request.urlopen", return_value=_FakeResponse({"children": []})):
            self.assertIsNone(sources_hn.fetch_top_comment("123", max_chars=100, timeout=8))


class TestHFAdapter(unittest.TestCase):
    def test_value_from_downloads_thresholds(self):
        self.assertEqual(sources_hf._value_from_downloads(100_000), "high")
        self.assertEqual(sources_hf._value_from_downloads(10_000), "medium")
        self.assertEqual(sources_hf._value_from_downloads(1), "low")

    def test_license_from_tags_extracts_license_id(self):
        self.assertEqual(sources_hf._license_from_tags(["onnx", "license:mit"]), "mit")
        self.assertIsNone(sources_hf._license_from_tags(["onnx"]))

    def test_permissive_license_is_low_complexity_restrictive_is_moderate(self):
        topic = {"id": "t1", "why_relevant": "x"}
        payload = [{"id": "org/model-a", "downloads": 5, "likes": 1, "tags": ["license:mit"]}]
        with patch("sources.common.urllib.request.urlopen", return_value=_FakeResponse(payload)):
            candidates = sources_hf.search(query="q", topic=topic, max_per_search=5, timeout=8, retrieved_at="2026-09-26T00:00:00Z")
        self.assertEqual(candidates[0]["complexity"], "low")

    def test_local_inference_topic_overrides_change_class_to_cost_optimisation(self):
        topic = {"id": "local-inference", "class": "cost_optimisation", "why_relevant": "x"}
        payload = [{"id": "org/model-a", "downloads": 5, "likes": 1, "tags": []}]
        with patch("sources.common.urllib.request.urlopen", return_value=_FakeResponse(payload)):
            candidates = sources_hf.search(query="q", topic=topic, max_per_search=5, timeout=8, retrieved_at="2026-09-26T00:00:00Z")
        self.assertEqual(candidates[0]["change_class"], "cost_optimisation")

    def test_non_list_response_degrades_to_empty_list(self):
        topic = {"id": "t1", "why_relevant": "x"}
        with patch("sources.common.urllib.request.urlopen", return_value=_FakeResponse({"error": "not a list"})):
            candidates = sources_hf.search(query="q", topic=topic, max_per_search=5, timeout=8, retrieved_at="2026-09-26T00:00:00Z")
        self.assertEqual(candidates, [])

    def test_fetch_model_card_network_failure_returns_none(self):
        with patch("sources.hf.urllib.request.urlopen", side_effect=urllib.error.URLError("no network")):
            self.assertIsNone(sources_hf.fetch_model_card("org/model-a", max_chars=100, timeout=8))


class TestTopicQueriesSchema(unittest.TestCase):
    def test_github_query_alias_maps_to_queries_github(self):
        topic = {"id": "t1", "github_query": "q", "why_relevant": "x"}
        self.assertEqual(external_discovery._topic_queries(topic), {"github": "q"})

    def test_explicit_queries_dict_takes_precedence_over_alias(self):
        topic = {"id": "t1", "github_query": "old", "queries": {"github": "new", "arxiv": "a"}, "why_relevant": "x"}
        self.assertEqual(external_discovery._topic_queries(topic), {"github": "new", "arxiv": "a"})

    def test_queries_dict_alone_with_no_github_key_gets_no_github_entry(self):
        topic = {"id": "t1", "queries": {"arxiv": "a"}, "why_relevant": "x"}
        self.assertEqual(external_discovery._topic_queries(topic), {"arxiv": "a"})

    def test_no_queries_or_github_query_returns_empty(self):
        self.assertEqual(external_discovery._topic_queries({"id": "t1", "why_relevant": "x"}), {})


class TestPerSourceCaps(unittest.TestCase):
    def test_per_source_cap_bounds_requests_to_one_source_across_multiple_topics(self):
        topics = [
            {"id": f"t{i}", "queries": {"arxiv": "q"}, "why_relevant": "x"} for i in range(5)
        ]
        config = {"max_external_searches_per_cycle": 9, "max_external_candidates_per_search": 1,
                  "max_external_candidates_per_cycle": 40, "external_request_timeout_seconds": 8,
                  "per_source_search_caps": {"arxiv": 2}}
        call_count = {"n": 0}

        def fake_search(**kwargs):
            call_count["n"] += 1
            return []

        with patch.dict("sources.SOURCES", {"arxiv": fake_search}):
            external_discovery.discover(topics, config)
        self.assertEqual(call_count["n"], 2)

    def test_unknown_source_name_is_skipped_without_raising(self):
        topics = [{"id": "t1", "queries": {"nonexistent-source": "q"}, "why_relevant": "x"}]
        config = {"max_external_searches_per_cycle": 9, "max_external_candidates_per_cycle": 40, "external_request_timeout_seconds": 8}
        candidates = external_discovery.discover(topics, config)
        self.assertEqual(candidates, [])

    def test_multiple_sources_on_one_topic_each_get_called(self):
        topic = {"id": "t1", "queries": {"github": "gq", "arxiv": "aq", "hn": "hq", "hf": "fq"}, "why_relevant": "x"}
        config = {"max_external_searches_per_cycle": 9, "max_external_candidates_per_cycle": 40, "external_request_timeout_seconds": 8}
        called_sources = []

        def make_fake(name):
            def fake(**kwargs):
                called_sources.append(name)
                return []
            return fake

        with patch.dict("sources.SOURCES", {n: make_fake(n) for n in ("github", "arxiv", "hn", "hf")}):
            external_discovery.discover([topic], config)
        self.assertEqual(set(called_sources), {"github", "arxiv", "hn", "hf"})


class TestEnrichmentContentDispatch(unittest.TestCase):
    def _candidate(self, source: str, **detail_overrides):
        detail = {"watchlist_gap_hypothesis": "g", **detail_overrides}
        return {
            "title": "some-title", "source": "https://example.com/x", "discovery_source": "external",
            "summary": "s", "why_relevant": "y", "evidence_strength": "moderate", "confidence": 0.5,
            "fit": "moderate", "value": "medium", "complexity": "moderate",
            "provenance": [{"source": source, "detail": json.dumps(detail)}],
        }

    def test_github_source_uses_readme_fetcher(self):
        c = self._candidate("github")
        c["source"] = "https://github.com/org/repo"
        with patch("external_enrichment._fetch_readme_excerpt", return_value="readme content") as mocked:
            content = external_enrichment._fetch_content_excerpt(c, max_chars=100, timeout=8)
        mocked.assert_called_once()
        self.assertEqual(content, "readme content")

    def test_arxiv_source_uses_stored_abstract_no_network_call(self):
        c = self._candidate("arxiv", abstract="A pre-fetched abstract.")
        with patch("sources.common.urllib.request.urlopen") as mocked:
            content = external_enrichment._fetch_content_excerpt(c, max_chars=100, timeout=8)
        mocked.assert_not_called()
        self.assertEqual(content, "A pre-fetched abstract.")

    def test_hn_source_fetches_top_comment(self):
        c = self._candidate("hn", hn_object_id="123")
        with patch("sources.hn.fetch_top_comment", return_value="top comment") as mocked:
            content = external_enrichment._fetch_content_excerpt(c, max_chars=100, timeout=8)
        mocked.assert_called_once_with("123", max_chars=100, timeout=8)
        self.assertEqual(content, "top comment")

    def test_huggingface_source_fetches_model_card(self):
        c = self._candidate("huggingface")
        with patch("sources.hf.fetch_model_card", return_value="model card") as mocked:
            content = external_enrichment._fetch_content_excerpt(c, max_chars=100, timeout=8)
        mocked.assert_called_once()
        self.assertEqual(content, "model card")

    def test_unrecognised_source_returns_none(self):
        c = self._candidate("dependency_release")
        self.assertIsNone(external_enrichment._fetch_content_excerpt(c, max_chars=100, timeout=8))


if __name__ == "__main__":
    unittest.main()
