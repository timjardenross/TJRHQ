"""
Unit tests for pr_health.py — Number One's PR CI/review status check.

Never touches real GitHub — urllib.request.urlopen is mocked throughout.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pr_health


def _json_response(payload):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    return _Resp()


class TestParsePrUrl(unittest.TestCase):
    def test_parses_standard_url(self):
        self.assertEqual(
            pr_health.parse_pr_url("https://github.com/acme/repo/pull/42"),
            ("acme", "repo", 42),
        )

    def test_none_on_non_pr_url(self):
        self.assertIsNone(pr_health.parse_pr_url("https://github.com/acme/repo"))

    def test_none_on_empty(self):
        self.assertIsNone(pr_health.parse_pr_url(""))
        self.assertIsNone(pr_health.parse_pr_url(None))


class TestCheckPrHealth(unittest.TestCase):
    def test_no_token_returns_not_ok(self):
        # token="" alone isn't enough to prove this — an ambient GITHUB_TOKEN
        # in the environment (e.g. this sandbox's git-proxy tooling) would
        # still be picked up by the `token or os.environ.get(...)` fallback,
        # which is the intended behaviour. Isolate the environment too.
        with patch.dict("os.environ", {}, clear=True):
            result = pr_health.check_pr_health("https://github.com/acme/repo/pull/1", token="")
        self.assertFalse(result["ok"])
        self.assertIn("GITHUB_TOKEN", result["reason"])

    def test_unparseable_url_returns_not_ok(self):
        result = pr_health.check_pr_health("not a url", token="fake-token")
        self.assertFalse(result["ok"])

    def test_closed_pr_short_circuits(self):
        with patch("urllib.request.urlopen", return_value=_json_response({"state": "closed"})):
            result = pr_health.check_pr_health("https://github.com/acme/repo/pull/1", token="fake")
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "closed")
        self.assertIsNone(result["ci_conclusion"])

    def test_open_pr_with_failing_ci_and_changes_requested(self):
        responses = [
            {"state": "open", "head": {"sha": "abc123"}, "mergeable_state": "blocked"},
            {"state": "failure"},
            [{"state": "COMMENTED"}, {"state": "CHANGES_REQUESTED"}],
        ]
        with patch("urllib.request.urlopen", side_effect=[_json_response(r) for r in responses]):
            result = pr_health.check_pr_health("https://github.com/acme/repo/pull/7", token="fake")
        self.assertTrue(result["ok"])
        self.assertEqual(result["ci_conclusion"], "failure")
        self.assertEqual(result["review_state"], "CHANGES_REQUESTED")
        self.assertEqual(result["mergeable_state"], "blocked")

    def test_open_pr_with_passing_ci_and_approval(self):
        responses = [
            {"state": "open", "head": {"sha": "def456"}, "mergeable_state": "clean"},
            {"state": "success"},
            [{"state": "APPROVED"}],
        ]
        with patch("urllib.request.urlopen", side_effect=[_json_response(r) for r in responses]):
            result = pr_health.check_pr_health("https://github.com/acme/repo/pull/8", token="fake")
        self.assertEqual(result["ci_conclusion"], "success")
        self.assertEqual(result["review_state"], "APPROVED")

    def test_pr_fetch_failure_returns_not_ok_never_raises(self):
        with patch("urllib.request.urlopen", side_effect=OSError("network down")):
            result = pr_health.check_pr_health("https://github.com/acme/repo/pull/9", token="fake")
        self.assertFalse(result["ok"])
        self.assertIn("network down", result["reason"])

    def test_ci_status_failure_degrades_gracefully(self):
        """CI status/reviews are best-effort — a failure fetching either must
        not take down the whole health check, since the PR itself resolved."""
        pr_response = _json_response({"state": "open", "head": {"sha": "abc"}, "mergeable_state": "clean"})

        def _side_effect(*args, **kwargs):
            # First call succeeds (the PR fetch); subsequent calls fail.
            if not hasattr(_side_effect, "called"):
                _side_effect.called = True
                return pr_response
            raise OSError("boom")

        with patch("urllib.request.urlopen", side_effect=_side_effect):
            result = pr_health.check_pr_health("https://github.com/acme/repo/pull/10", token="fake")
        self.assertTrue(result["ok"])
        self.assertIsNone(result["ci_conclusion"])
        self.assertIsNone(result["review_state"])


if __name__ == "__main__":
    unittest.main()
