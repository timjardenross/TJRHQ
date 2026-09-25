"""
Tests for scripts/self_improvement/sources/firecrawl_search.py — the
budget-gated paid-search source (docs/self-improvement/
HQ-EVOLUTION-SOURCE-EXPANSION.md §2 Tier 2 / §11).

Same bare-sibling-import convention as tests/test_hq_evolution.py. Never
makes a real Firecrawl API call or a real Supabase call — everything the
budget gate depends on is mocked, so this suite spends zero real credits.
"""

import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
SELF_IMPROVEMENT_DIR = REPO_ROOT / "scripts" / "self_improvement"
sys.path.insert(0, str(SELF_IMPROVEMENT_DIR))

from sources import firecrawl_search

_FAKE_ENV = {"FIRECRAWL_API_KEY": "test-key-not-real"}  # pragma: allowlist secret


class _FakeResponse:
    def __init__(self, body):
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestFirecrawlSearch(unittest.TestCase):
    def setUp(self):
        self.topic = {"id": "t1", "why_relevant": "x", "gap_hypothesis": "g"}

    def test_no_api_key_returns_empty_list_without_a_budget_check(self):
        with patch.dict("os.environ", {}, clear=True), \
             patch("sources.firecrawl_search._budget_gate") as mocked_gate:
            candidates = firecrawl_search.search(query="q", topic=self.topic, max_per_search=3, timeout=8, retrieved_at="2026-09-26T00:00:00Z")
        mocked_gate.assert_not_called()
        self.assertEqual(candidates, [])

    def test_budget_module_unimportable_returns_empty_list(self):
        with patch.dict("os.environ", _FAKE_ENV, clear=True), \
             patch("sources.firecrawl_search._budget_gate", return_value=None), \
             patch("sources.common.urllib.request.urlopen") as mocked:
            candidates = firecrawl_search.search(query="q", topic=self.topic, max_per_search=3, timeout=8, retrieved_at="2026-09-26T00:00:00Z")
        mocked.assert_not_called()
        self.assertEqual(candidates, [])

    def test_budget_exceeded_returns_empty_list_without_a_request(self):
        fake_budget = MagicMock()
        fake_budget.check_and_increment.side_effect = RuntimeError("budget exceeded")
        with patch.dict("os.environ", _FAKE_ENV, clear=True), \
             patch("sources.firecrawl_search._budget_gate", return_value=fake_budget), \
             patch("sources.firecrawl_search.urllib.request.urlopen") as mocked:
            candidates = firecrawl_search.search(query="q", topic=self.topic, max_per_search=3, timeout=8, retrieved_at="2026-09-26T00:00:00Z")
        mocked.assert_not_called()
        self.assertEqual(candidates, [])

    def test_budget_allowed_makes_the_real_request_and_builds_candidates(self):
        fake_budget = MagicMock()
        fake_budget.check_and_increment.return_value = 1
        payload = {"success": True, "data": [
            {"url": "https://example.com/a", "title": "Result A", "description": "d"},
        ]}
        with patch.dict("os.environ", _FAKE_ENV, clear=True), \
             patch("sources.firecrawl_search._budget_gate", return_value=fake_budget), \
             patch("sources.firecrawl_search.urllib.request.urlopen", return_value=_FakeResponse(payload)):
            candidates = firecrawl_search.search(query="q", topic=self.topic, max_per_search=3, timeout=8, retrieved_at="2026-09-26T00:00:00Z")
        fake_budget.check_and_increment.assert_called_once_with("firecrawl")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["source"], "https://example.com/a")
        self.assertEqual(candidates[0]["provenance"][0]["source"], "firecrawl_search")

    def test_network_failure_degrades_to_empty_list(self):
        fake_budget = MagicMock()
        fake_budget.check_and_increment.return_value = 1
        with patch.dict("os.environ", _FAKE_ENV, clear=True), \
             patch("sources.firecrawl_search._budget_gate", return_value=fake_budget), \
             patch("sources.firecrawl_search.urllib.request.urlopen", side_effect=urllib.error.URLError("no network")):
            candidates = firecrawl_search.search(query="q", topic=self.topic, max_per_search=3, timeout=8, retrieved_at="2026-09-26T00:00:00Z")
        self.assertEqual(candidates, [])

    def test_result_missing_url_or_title_is_skipped(self):
        fake_budget = MagicMock()
        fake_budget.check_and_increment.return_value = 1
        payload = {"success": True, "data": [{"url": "https://example.com/a"}, {"title": "no url"}]}
        with patch.dict("os.environ", _FAKE_ENV, clear=True), \
             patch("sources.firecrawl_search._budget_gate", return_value=fake_budget), \
             patch("sources.firecrawl_search.urllib.request.urlopen", return_value=_FakeResponse(payload)):
            candidates = firecrawl_search.search(query="q", topic=self.topic, max_per_search=3, timeout=8, retrieved_at="2026-09-26T00:00:00Z")
        self.assertEqual(candidates, [])


if __name__ == "__main__":
    unittest.main()
