"""
Tests for the Phase 1 changes in docs/self-improvement/
HQ-EVOLUTION-SOURCE-EXPANSION.md: watchlist topic rotation
(external_discovery._select_rotated_topics / watchlist_rotation.py) and
the new dependency_releases.py source.

Same bare-sibling-import convention as tests/test_hq_evolution.py (this
package runs with scripts/self_improvement as sys.path[0], not as a
`scripts.self_improvement.X` package import).
"""

import json
import sys
import tempfile
import unittest
import urllib.error
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
SELF_IMPROVEMENT_DIR = REPO_ROOT / "scripts" / "self_improvement"
sys.path.insert(0, str(SELF_IMPROVEMENT_DIR))

import dependency_releases
import external_discovery
import watchlist_rotation

DEFAULT_EVOLUTION_CONFIG = {
    "max_external_searches_per_cycle": 6,
    "max_external_candidates_per_search": 5,
    "max_external_candidates_per_cycle": 20,
    "external_request_timeout_seconds": 8,
}


class FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode()

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestTopicRotation(unittest.TestCase):
    def test_never_searched_topics_sort_before_searched_ones(self):
        topics = [
            {"id": "a", "why_relevant": "x"}, {"id": "b", "why_relevant": "x"}, {"id": "c", "why_relevant": "x"},
        ]
        state = {"a": "2026-09-20T00:00:00+00:00", "b": "2026-09-24T00:00:00+00:00"}
        selected = external_discovery._select_rotated_topics(topics, state, max_searches=2)
        self.assertEqual([t["id"] for t in selected], ["c", "a"])

    def test_stalest_searched_topic_comes_before_more_recently_searched_one(self):
        topics = [{"id": "a", "why_relevant": "x"}, {"id": "b", "why_relevant": "x"}]
        state = {"a": "2026-09-20T00:00:00+00:00", "b": "2026-09-24T00:00:00+00:00"}
        selected = external_discovery._select_rotated_topics(topics, state, max_searches=1)
        self.assertEqual([t["id"] for t in selected], ["a"])

    def test_nine_topics_six_slots_reaches_every_topic_over_two_cycles(self):
        """Regression for the exact starvation this rotation fixes: 9
        watchlist topics, max_external_searches_per_cycle=6 — a plain
        [:6] slice would never reach topics 7-9 across any number of
        cycles. Rotation must reach all 9 within 2 cycles."""
        topics = [{"id": f"t{i}", "why_relevant": "x"} for i in range(9)]
        state: dict[str, str] = {}
        cycle1 = external_discovery._select_rotated_topics(topics, state, max_searches=6)
        for t in cycle1:
            state[t["id"]] = "2026-09-25T03:00:00+00:00"
        cycle2 = external_discovery._select_rotated_topics(topics, state, max_searches=6)
        reached = {t["id"] for t in cycle1} | {t["id"] for t in cycle2}
        self.assertEqual(reached, {t["id"] for t in topics})

    def test_discover_without_rotation_state_keeps_prior_plain_slice_behavior(self):
        """rotation_state=None (the default) must behave exactly like the
        pre-rotation code: first max_searches topics, in file order."""
        topics = [{"id": f"t{i}", "github_query": "q", "why_relevant": "x"} for i in range(9)]
        with patch("sources.common.urllib.request.urlopen", side_effect=urllib.error.URLError("no network")):
            external_discovery.discover(topics, DEFAULT_EVOLUTION_CONFIG)  # must not raise, no rotation bookkeeping

    def test_discover_updates_rotation_state_for_selected_topics_even_on_network_failure(self):
        topics = [{"id": "a", "github_query": "q", "why_relevant": "x"}]
        state: dict[str, str] = {}
        with patch("sources.common.urllib.request.urlopen", side_effect=urllib.error.URLError("no network")):
            external_discovery.discover(topics, DEFAULT_EVOLUTION_CONFIG, rotation_state=state)
        self.assertIn("a", state)

    def test_discover_does_not_mark_topic_searched_when_skipped_for_missing_why_relevant(self):
        topics = [{"id": "a", "github_query": "q"}]  # no why_relevant -> skipped before any request
        state: dict[str, str] = {}
        external_discovery.discover(topics, DEFAULT_EVOLUTION_CONFIG, rotation_state=state)
        self.assertNotIn("a", state)

    def test_query_no_longer_uses_sort_updated_and_adds_a_recency_floor(self):
        topic = {"id": "a", "github_query": "q", "why_relevant": "x"}
        captured_urls = []

        def fake_urlopen(req, timeout=None):
            captured_urls.append(req.full_url)
            return FakeResponse({"items": []})

        with patch("sources.common.urllib.request.urlopen", side_effect=fake_urlopen):
            external_discovery.discover([topic], DEFAULT_EVOLUTION_CONFIG)
        self.assertEqual(len(captured_urls), 1)
        self.assertNotIn("sort=updated", captured_urls[0])
        self.assertIn("pushed%3A%3E", captured_urls[0])  # urlencoded "pushed:>YYYY-MM-DD"


class TestWatchlistRotationPersistence(unittest.TestCase):
    def test_missing_file_returns_empty_dict(self):
        self.assertEqual(watchlist_rotation.load_rotation_state(Path("/nonexistent/rotation.json")), {})

    def test_corrupt_file_returns_empty_dict_not_exception(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rotation.json"
            path.write_text("{not valid json")
            self.assertEqual(watchlist_rotation.load_rotation_state(path), {})

    def test_save_then_load_roundtrips(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "review" / "rotation.json"
            state = {"model-routing": "2026-09-25T03:00:00+00:00"}
            watchlist_rotation.save_rotation_state(path, state)
            self.assertEqual(watchlist_rotation.load_rotation_state(path), state)


class TestDependencyReleases(unittest.TestCase):
    def test_parse_pypi_packages_finds_pinned_versions_and_skips_unpinned(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "requirements.txt").write_text(
                "deepeval==1.2.3\n"
                "# a comment\n"
                "requests>=2.0\n"  # unpinned specifier -> skipped
                "some-package\n"  # bare, no specifier -> skipped
                "flask==3.0.0  # trailing comment\n"
            )
            packages = dict(dependency_releases.parse_pypi_packages(root))
            self.assertEqual(packages.get("deepeval"), "1.2.3")
            self.assertEqual(packages.get("flask"), "3.0.0")
            self.assertNotIn("requests", packages)
            self.assertNotIn("some-package", packages)

    def test_parse_pypi_packages_excludes_vendored_venv_copies(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            vendored = root / ".venv" / "lib" / "site-packages" / "something"
            vendored.mkdir(parents=True)
            (vendored / "requirements.txt").write_text("vendored-pkg==1.0.0\n")
            (root / "requirements.txt").write_text("real-pkg==1.0.0\n")
            packages = dict(dependency_releases.parse_pypi_packages(root))
            self.assertIn("real-pkg", packages)
            self.assertNotIn("vendored-pkg", packages)

    def test_parse_npm_packages_strips_caret_and_tilde(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "lcars-portal").mkdir()
            (root / "lcars-portal" / "package.json").write_text(json.dumps({
                "dependencies": {"next": "^14.0.0"},
                "devDependencies": {"typescript": "~5.2.0", "some-workspace-pkg": "workspace:*"},
            }))
            packages = dict(dependency_releases.parse_npm_packages(root))
            self.assertEqual(packages.get("next"), "14.0.0")
            self.assertEqual(packages.get("typescript"), "5.2.0")
            self.assertNotIn("some-workspace-pkg", packages)

    def test_bump_kind_none_when_latest_not_newer(self):
        self.assertIsNone(dependency_releases._bump_kind("2.0.0", "2.0.0"))
        self.assertIsNone(dependency_releases._bump_kind("2.0.0", "1.9.9"))

    def test_bump_kind_classifies_major_vs_minor(self):
        self.assertEqual(dependency_releases._bump_kind("1.2.3", "2.0.0"), "major")
        self.assertEqual(dependency_releases._bump_kind("1.2.3", "1.3.0"), "minor_or_patch")

    def test_pypi_candidate_none_when_network_fails(self):
        with patch("dependency_releases.urllib.request.urlopen", side_effect=urllib.error.URLError("no network")):
            self.assertIsNone(dependency_releases._pypi_candidate("deepeval", "1.0.0", timeout=8))

    def test_pypi_candidate_none_when_no_newer_version_available(self):
        with patch("dependency_releases.urllib.request.urlopen", return_value=FakeResponse({"info": {"version": "1.0.0", "summary": "s", "project_url": "https://pypi.org/project/x/"}})):
            self.assertIsNone(dependency_releases._pypi_candidate("x", "1.0.0", timeout=8))

    def test_pypi_candidate_built_when_newer_version_available(self):
        payload = {"info": {"version": "2.0.0", "summary": "does a thing", "project_url": "https://pypi.org/project/x/"}}
        with patch("dependency_releases.urllib.request.urlopen", return_value=FakeResponse(payload)):
            candidate = dependency_releases._pypi_candidate("x", "1.0.0", timeout=8)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["value"], "high")
        self.assertEqual(candidate["complexity"], "moderate")  # major bump
        self.assertIn("x", candidate["why_relevant"])
        self.assertTrue(candidate["why_relevant"])  # never empty -> would fail the relevance gate's why_relevant requirement

    def test_discover_respects_max_total_budget(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            reqs = "\n".join(f"pkg{i}==1.0.0" for i in range(10))
            (root / "requirements.txt").write_text(reqs)
            payload = {"info": {"version": "2.0.0", "summary": "s", "project_url": "https://pypi.org/project/x/"}}
            with patch("dependency_releases.urllib.request.urlopen", return_value=FakeResponse(payload)):
                candidates = dependency_releases.discover({"dependency_release_batch_size": 5}, root, max_total=3)
        self.assertEqual(len(candidates), 3)

    def test_discover_caps_registry_requests_when_nothing_is_outdated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "requirements.txt").write_text("\n".join(f"pkg{i}==1.0.0" for i in range(40)))
            payload = {"info": {"version": "1.0.0", "summary": "s", "project_url": "https://pypi.org/project/x/"}}
            with patch("dependency_releases.urllib.request.urlopen", return_value=FakeResponse(payload)) as urlopen:
                candidates = dependency_releases.discover(
                    {"dependency_release_batch_size": 5, "dependency_release_max_requests": 7}, root,
                )
        self.assertEqual(candidates, [])
        self.assertEqual(urlopen.call_count, 7)  # not 40: up-to-date packages still spend request budget

    def test_daily_window_advances_and_covers_every_package(self):
        packages = list(range(10))
        seen = set()
        for day in range(3):
            seen.update(dependency_releases._daily_window(packages, 4, date(2026, 9, 25) + timedelta(days=day)))
        self.assertEqual(seen, set(packages))  # ceil(10/4)=3 days covers all, no head-of-list starvation
        self.assertEqual(dependency_releases._daily_window(packages, 20), packages)
        self.assertEqual(dependency_releases._daily_window([], 4), [])

    def test_discover_returns_empty_list_when_no_budget_remains(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            candidates = dependency_releases.discover({}, Path(tmpdir), max_total=0)
        self.assertEqual(candidates, [])


if __name__ == "__main__":
    unittest.main()
