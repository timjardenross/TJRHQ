"""
Tests for scripts/self_improvement/external_enrichment.py and
router_client.ModelRouterClient.assess_external_candidate.

external_discovery.discover() sets every candidate's fit/evidence_strength
to hardcoded "moderate"/"moderate" constants (metadata-only at discovery
time); relevance.py's RelevanceGate.score_candidate() then weighs those
two fields at 65% of the total gate score. This suite verifies
external_enrichment.enrich() replaces those constants with a real,
README-grounded assessment for a bounded top-N of candidates, and — just
as importantly — that every failure mode (no router, README fetch
failure, model failure, invalid/unparseable assessment) leaves a
candidate's fields completely untouched rather than partially written or
guessed.

Same bare-sibling-import convention as tests/test_hq_evolution.py (this
package runs with scripts/self_improvement as sys.path[0], not as a
`scripts.self_improvement.X` package import).
"""
from __future__ import annotations

import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
SELF_IMPROVEMENT_DIR = REPO_ROOT / "scripts" / "self_improvement"
sys.path.insert(0, str(SELF_IMPROVEMENT_DIR))

import external_enrichment
from router_client import ModelRouterClient


def _candidate(**overrides) -> dict:
    base = {
        "title": "org/repo",
        "source": "https://github.com/org/repo",
        "discovery_source": "external",
        "summary": "A thing that does stuff",
        "why_relevant": "Might close gap X",
        "evidence_strength": "moderate",
        "confidence": 0.5,
        "fit": "moderate",
        "value": "medium",
        "complexity": "moderate",
        "provenance": [{
            "source": "github",
            "detail": json.dumps({"watchlist_gap_hypothesis": "core/model-router has no evaluated alternative"}),
        }],
    }
    base.update(overrides)
    return base


class _FakeResponse:
    def __init__(self, body: bytes | str):
        self._body = body if isinstance(body, bytes) else body.encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# ── _repo_full_name_from_source ──────────────────────────────────────────────

class TestRepoFullName(unittest.TestCase):
    def test_extracts_owner_repo(self):
        self.assertEqual(external_enrichment._repo_full_name_from_source("https://github.com/org/repo"), "org/repo")

    def test_trailing_slash_and_extra_path_segments(self):
        self.assertEqual(
            external_enrichment._repo_full_name_from_source("https://github.com/org/repo/"), "org/repo"
        )
        self.assertEqual(
            external_enrichment._repo_full_name_from_source("https://github.com/org/repo/issues/1"), "org/repo"
        )

    def test_non_github_url_returns_none(self):
        self.assertIsNone(external_enrichment._repo_full_name_from_source("https://gitlab.com/org/repo"))

    def test_empty_or_malformed_returns_none(self):
        self.assertIsNone(external_enrichment._repo_full_name_from_source(""))
        self.assertIsNone(external_enrichment._repo_full_name_from_source("https://github.com/onlyorg"))


# ── _fetch_readme_excerpt ─────────────────────────────────────────────────────

class TestFetchReadme(unittest.TestCase):
    def test_returns_excerpt_truncated_to_max_chars(self):
        with patch("external_enrichment.urllib.request.urlopen", return_value=_FakeResponse("x" * 10000)):
            result = external_enrichment._fetch_readme_excerpt(
                "https://github.com/org/repo", max_chars=100, timeout=5,
            )
        self.assertEqual(len(result), 100)

    def test_network_failure_returns_none_not_exception(self):
        with patch("external_enrichment.urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            result = external_enrichment._fetch_readme_excerpt(
                "https://github.com/org/repo", max_chars=100, timeout=5,
            )
        self.assertIsNone(result)

    def test_unrecognisable_source_returns_none_without_a_request(self):
        with patch("external_enrichment.urllib.request.urlopen") as mocked:
            result = external_enrichment._fetch_readme_excerpt("not-a-url", max_chars=100, timeout=5)
        mocked.assert_not_called()
        self.assertIsNone(result)


# ── _gap_hypothesis_from_provenance ───────────────────────────────────────────

class TestGapHypothesisExtraction(unittest.TestCase):
    def test_extracts_from_valid_provenance(self):
        candidate = _candidate()
        self.assertEqual(
            external_enrichment._gap_hypothesis_from_provenance(candidate),
            "core/model-router has no evaluated alternative",
        )

    def test_missing_provenance_returns_none(self):
        self.assertIsNone(external_enrichment._gap_hypothesis_from_provenance({"provenance": []}))

    def test_malformed_detail_json_does_not_raise(self):
        candidate = _candidate(provenance=[{"source": "github", "detail": "{not json"}])
        self.assertIsNone(external_enrichment._gap_hypothesis_from_provenance(candidate))


# ── _apply_assessment ─────────────────────────────────────────────────────────

class TestApplyAssessment(unittest.TestCase):
    def test_valid_assessment_overwrites_fit_and_evidence_strength(self):
        candidate = _candidate()
        applied = external_enrichment._apply_assessment(candidate, {
            "fit": "strong", "evidence_strength": "conclusive", "confidence": 0.85, "rationale": "README confirms it",
        })
        self.assertTrue(applied)
        self.assertEqual(candidate["fit"], "strong")
        self.assertEqual(candidate["evidence_strength"], "conclusive")
        self.assertEqual(candidate["confidence"], 0.85)
        self.assertEqual(candidate["readme_assessed_rationale"], "README confirms it")
        self.assertTrue(candidate["readme_assessed"])

    def test_invalid_fit_leaves_candidate_completely_unchanged(self):
        candidate = _candidate()
        original = dict(candidate)
        applied = external_enrichment._apply_assessment(candidate, {"fit": "extremely good", "evidence_strength": "strong"})
        self.assertFalse(applied)
        self.assertEqual(candidate, original)

    def test_empty_assessment_leaves_candidate_unchanged(self):
        candidate = _candidate()
        original = dict(candidate)
        applied = external_enrichment._apply_assessment(candidate, {})
        self.assertFalse(applied)
        self.assertEqual(candidate, original)

    def test_out_of_range_confidence_is_ignored_but_fit_still_applies(self):
        candidate = _candidate()
        external_enrichment._apply_assessment(candidate, {"fit": "weak", "evidence_strength": "weak", "confidence": 5.0})
        self.assertEqual(candidate["fit"], "weak")
        self.assertEqual(candidate["confidence"], 0.5)  # unchanged from _candidate()'s default


# ── enrich() — orchestration, bounding, fail-open behaviour ──────────────────

class TestEnrich(unittest.TestCase):
    def setUp(self):
        self.config = {"max_external_enrichments_per_cycle": 2, "external_readme_max_chars": 4000, "external_readme_timeout_seconds": 8}

    def test_no_router_returns_candidates_unchanged(self):
        candidates = [_candidate(title="a"), _candidate(title="b")]
        result = external_enrichment.enrich(candidates, self.config, router=None)
        self.assertEqual(result, candidates)
        self.assertEqual(result[0]["fit"], "moderate")  # untouched

    def test_max_enrichments_zero_skips_entirely(self):
        router = MagicMock()
        candidates = [_candidate()]
        external_enrichment.enrich(candidates, {**self.config, "max_external_enrichments_per_cycle": 0}, router=router)
        router.assess_external_candidate.assert_not_called()

    def test_bounded_to_max_enrichments_per_cycle(self):
        router = MagicMock()
        router.assess_external_candidate.return_value = {
            "success": True, "assessment": {"fit": "strong", "evidence_strength": "strong", "confidence": 0.8},
        }
        candidates = [_candidate(title=f"repo{i}", source=f"https://github.com/org/repo{i}") for i in range(5)]
        with patch("external_enrichment._fetch_readme_excerpt", return_value="some readme text"):
            external_enrichment.enrich(candidates, self.config, router=router)
        self.assertEqual(router.assess_external_candidate.call_count, 2)  # max_external_enrichments_per_cycle

    def test_enrichment_prioritises_higher_ranked_candidates(self):
        router = MagicMock()
        router.assess_external_candidate.return_value = {
            "success": True, "assessment": {"fit": "strong", "evidence_strength": "strong", "confidence": 0.9},
        }
        low = _candidate(title="low-value", value="low", complexity="high")
        high = _candidate(title="high-value", value="medium", complexity="low")
        with patch("external_enrichment._fetch_readme_excerpt", return_value="readme"):
            external_enrichment.enrich([low, high], {**self.config, "max_external_enrichments_per_cycle": 1}, router=router)
        self.assertEqual(high["fit"], "strong")  # enriched
        self.assertEqual(low["fit"], "moderate")  # left at discover()'s default — budget went to the higher-ranked one

    def test_custom_score_fn_used_for_ranking(self):
        router = MagicMock()
        router.assess_external_candidate.return_value = {
            "success": True, "assessment": {"fit": "strong", "evidence_strength": "strong", "confidence": 0.9},
        }
        a = _candidate(title="a")
        b = _candidate(title="b")
        with patch("external_enrichment._fetch_readme_excerpt", return_value="readme"):
            external_enrichment.enrich(
                [a, b], {**self.config, "max_external_enrichments_per_cycle": 1}, router=router,
                score_fn=lambda c: 1 if c["title"] == "b" else 0,
            )
        self.assertEqual(b["fit"], "strong")
        self.assertEqual(a["fit"], "moderate")

    def test_router_exception_for_one_candidate_does_not_abort_the_rest(self):
        router = MagicMock()
        router.assess_external_candidate.side_effect = [
            RuntimeError("router down"),
            {"success": True, "assessment": {"fit": "strong", "evidence_strength": "strong", "confidence": 0.9}},
        ]
        a = _candidate(title="a", value="medium")
        b = _candidate(title="b", value="medium")
        with patch("external_enrichment._fetch_readme_excerpt", return_value="readme"):
            external_enrichment.enrich([a, b], self.config, router=router)
        # One of the two got the exception, the other succeeded — order
        # depends on sort stability for equal ranks, so check aggregate state.
        fits = {c["title"]: c["fit"] for c in (a, b)}
        self.assertIn("strong", fits.values())
        self.assertIn("moderate", fits.values())

    def test_failed_router_call_leaves_candidate_unchanged(self):
        router = MagicMock()
        router.assess_external_candidate.return_value = {"success": False, "error": "timeout"}
        candidate = _candidate()
        with patch("external_enrichment._fetch_readme_excerpt", return_value="readme"):
            external_enrichment.enrich([candidate], self.config, router=router)
        self.assertEqual(candidate["fit"], "moderate")
        self.assertNotIn("readme_assessed", candidate)

    def test_invalid_assessment_leaves_candidate_unchanged(self):
        router = MagicMock()
        router.assess_external_candidate.return_value = {"success": True, "assessment": {"fit": "not-a-real-value"}}
        candidate = _candidate()
        with patch("external_enrichment._fetch_readme_excerpt", return_value="readme"):
            external_enrichment.enrich([candidate], self.config, router=router)
        self.assertEqual(candidate["fit"], "moderate")


# ── router_client.assess_external_candidate ──────────────────────────────────

class TestAssessExternalCandidate(unittest.TestCase):
    def test_success_parses_assessment(self):
        client = ModelRouterClient()
        router_response = json.dumps({
            "success": True,
            "response": json.dumps({"fit": "strong", "evidence_strength": "strong", "confidence": 0.8, "rationale": "r"}),
        })
        with patch.object(client, "_call_router", return_value=json.loads(router_response)) as call_mock:
            result = client.assess_external_candidate(_candidate(), "readme text", "gap hypothesis")
        call_mock.assert_called_once()
        task_type = call_mock.call_args.args[0]
        self.assertEqual(task_type, "hq-evolution-external-fit")
        self.assertEqual(result["assessment"]["fit"], "strong")

    def test_failure_never_populates_assessment_key(self):
        client = ModelRouterClient()
        with patch.object(client, "_call_router", return_value={"success": False, "error": "down"}):
            result = client.assess_external_candidate(_candidate(), None, None)
        self.assertNotIn("assessment", result)

    def test_prompt_includes_gap_hypothesis_and_readme(self):
        client = ModelRouterClient()
        prompt = client._build_external_fit_prompt(_candidate(), "THE README TEXT", "THE GAP HYPOTHESIS")
        self.assertIn("THE README TEXT", prompt)
        self.assertIn("THE GAP HYPOTHESIS", prompt)

    def test_prompt_handles_missing_readme_gracefully(self):
        client = ModelRouterClient()
        prompt = client._build_external_fit_prompt(_candidate(), None, "hypothesis")
        self.assertIn("no README could be fetched", prompt)


if __name__ == "__main__":
    unittest.main()
