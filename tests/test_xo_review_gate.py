"""
Tests for the 2026-09-26 XO engineering-review gate: version-bump
detection + conditional existing-file allowance in batch_coding.py,
the XO gatekeeper model call in xo_review.py, and the new PR-comment/
merge/close helpers in github_pr.py.

Never touches a real GitHub API or Model Router — everything at the
network boundary is mocked. Dotted-path import convention matches
tests/test_batch_coding_pr_error.py.
"""

import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.engineering import batch_coding, xo_review
from core.engineering.providers import github_pr


class TestVersionBumpTitleDetection(unittest.TestCase):
    def test_pypi_release_title_matches(self):
        self.assertTrue(batch_coding._is_version_bump_title("openai 3.13.0 -> 3.19.2 (pypi release)"))

    def test_npm_release_title_matches(self):
        self.assertTrue(batch_coding._is_version_bump_title("@radix-ui/react-collapsible 1.1.3 -> 1.1.20 (npm release)"))

    def test_non_version_bump_title_does_not_match(self):
        self.assertFalse(batch_coding._is_version_bump_title("In-tree virtual environment chatterbox-venv unignored in repository tree"))

    def test_empty_or_none_title_does_not_match(self):
        self.assertFalse(batch_coding._is_version_bump_title(""))
        self.assertFalse(batch_coding._is_version_bump_title(None))

    def test_other_ecosystem_word_does_not_match(self):
        self.assertFalse(batch_coding._is_version_bump_title("openai 3.13.0 -> 3.19.2 (crates release)"))


class TestOpenFilesPrConditionalAllowExisting(unittest.TestCase):
    def setUp(self):
        self.patchers = [
            patch.object(batch_coding, "_env_value", side_effect=self._env),
        ]
        for p in self.patchers:
            p.start()
        self.env = {"GITHUB_TOKEN": "tok", "GITHUB_REPO": "org/repo", "AUTO_ENGINEER_ALLOW_EXISTING_EDITS": ""}

    def tearDown(self):
        for p in self.patchers:
            p.stop()

    def _env(self, key):
        return self.env.get(key, "")

    def test_version_bump_title_allows_existing_without_env_flag(self):
        captured = {}

        def fake_open_files_pr(*a, **k):
            captured.update(k)
            return {"opened": True, "url": "https://github.com/org/repo/pull/1", "diff": "diff --git a/requirements.txt"}

        with patch.object(github_pr, "open_files_pr", side_effect=fake_open_files_pr), \
             patch.object(batch_coding, "_run_xo_review_and_notify"):
            batch_coding._open_files_pr(
                "custom-id", {"requirements.txt": "content"},
                {"__mission_title__": "openai 3.13.0 -> 3.19.2 (pypi release)"},
            )
        self.assertTrue(captured["allow_existing"])

    def test_non_version_bump_title_defers_existing_files(self):
        captured = {}

        def fake_open_files_pr(*a, **k):
            captured.update(k)
            return {"opened": True, "url": "https://github.com/org/repo/pull/2"}

        # Path.exists() patched True to simulate an existing file — this
        # also makes _open_files_pr's OWN deferred-review call believe the
        # file is real, so it must be mocked too, or this test makes a
        # real call to the live model-router + a real notify() attempt.
        with patch("pathlib.Path.exists", return_value=True), \
             patch.object(github_pr, "open_files_pr", side_effect=fake_open_files_pr), \
             patch.object(batch_coding, "_review_deferred_files") as mocked_deferred_review:
            batch_coding._open_files_pr(
                "custom-id", {"some/existing_file.py": "content"},
                {"__mission_title__": "Fix a real bug in the router"},
            )
        self.assertFalse(captured["allow_existing"])
        mocked_deferred_review.assert_called_once()

    def test_xo_review_only_runs_for_version_bump_titles(self):
        with patch.object(github_pr, "open_files_pr", return_value={"opened": True, "url": "https://github.com/org/repo/pull/3", "diff": "d"}), \
             patch.object(batch_coding, "_run_xo_review_and_notify") as mocked_review:
            batch_coding._open_files_pr(
                "custom-id", {"some/existing_file.py": "content"},
                {"__mission_title__": "Fix a real bug in the router"},
            )
        mocked_review.assert_not_called()

    def test_xo_review_runs_and_receives_the_real_diff_for_version_bump(self):
        with patch.object(github_pr, "open_files_pr", return_value={"opened": True, "url": "https://github.com/org/repo/pull/4", "diff": "diff --git a/requirements.txt b/requirements.txt"}), \
             patch.object(batch_coding, "_run_xo_review_and_notify") as mocked_review:
            batch_coding._open_files_pr(
                "custom-id", {"requirements.txt": "content"},
                {"__mission_title__": "openai 3.13.0 -> 3.19.2 (pypi release)", "summary": "bump"},
            )
        mocked_review.assert_called_once()
        self.assertEqual(mocked_review.call_args.kwargs["diff"], "diff --git a/requirements.txt b/requirements.txt")

    def test_xo_review_not_run_when_pr_did_not_open(self):
        with patch.object(github_pr, "open_files_pr", return_value={"opened": False, "reason": "git_failed"}), \
             patch.object(batch_coding, "_run_xo_review_and_notify") as mocked_review:
            batch_coding._open_files_pr(
                "custom-id", {"requirements.txt": "content"},
                {"__mission_title__": "openai 3.13.0 -> 3.19.2 (pypi release)"},
            )
        mocked_review.assert_not_called()


class TestPrNumberFromUrl(unittest.TestCase):
    def test_extracts_trailing_number(self):
        self.assertEqual(batch_coding._pr_number_from_url("https://github.com/org/repo/pull/314"), 314)

    def test_trailing_slash_handled(self):
        self.assertEqual(batch_coding._pr_number_from_url("https://github.com/org/repo/pull/314/"), 314)

    def test_malformed_url_returns_none(self):
        self.assertIsNone(batch_coding._pr_number_from_url(""))
        self.assertIsNone(batch_coding._pr_number_from_url("not-a-url"))


class TestRunXoReviewAndNotify(unittest.TestCase):
    def test_posts_verdict_comment_and_notifies(self):
        with patch.object(xo_review, "review_diff", return_value={"verdict": "approve", "reasoning": "looks fine"}), \
             patch.object(github_pr, "post_xo_verdict_comment") as mocked_comment, \
             patch("core.platform.notification_service.notify") as mocked_notify:
            batch_coding._run_xo_review_and_notify(
                token="tok", repo="org/repo", pr_url="https://github.com/org/repo/pull/5",
                diff="d", title="pkg 1.0 -> 2.0 (pypi release)", summary="s",
            )
        mocked_comment.assert_called_once_with("tok", "org/repo", 5, "approve", "looks fine")
        mocked_notify.assert_called_once()

    def test_hold_verdict_still_posts_and_notifies(self):
        with patch.object(xo_review, "review_diff", return_value={"verdict": "hold", "reasoning": "scope exceeded"}), \
             patch.object(github_pr, "post_xo_verdict_comment") as mocked_comment, \
             patch("core.platform.notification_service.notify") as mocked_notify:
            batch_coding._run_xo_review_and_notify(
                token="tok", repo="org/repo", pr_url="https://github.com/org/repo/pull/6",
                diff="d", title="pkg 1.0 -> 2.0 (pypi release)", summary="s",
            )
        mocked_comment.assert_called_once_with("tok", "org/repo", 6, "hold", "scope exceeded")
        mocked_notify.assert_called_once()

    def test_malformed_pr_url_skips_review_entirely(self):
        with patch.object(xo_review, "review_diff") as mocked_review:
            batch_coding._run_xo_review_and_notify(
                token="tok", repo="org/repo", pr_url="not-a-url",
                diff="d", title="pkg 1.0 -> 2.0 (pypi release)", summary="s",
            )
        mocked_review.assert_not_called()

    def test_review_diff_exception_still_posts_a_hold_comment(self):
        with patch.object(xo_review, "review_diff", side_effect=RuntimeError("boom")), \
             patch.object(github_pr, "post_xo_verdict_comment") as mocked_comment, \
             patch("core.platform.notification_service.notify"):
            batch_coding._run_xo_review_and_notify(
                token="tok", repo="org/repo", pr_url="https://github.com/org/repo/pull/7",
                diff="d", title="pkg 1.0 -> 2.0 (pypi release)", summary="s",
            )
        self.assertEqual(mocked_comment.call_args.args[3], "hold")

    def test_notification_failure_does_not_raise(self):
        with patch.object(xo_review, "review_diff", return_value={"verdict": "approve", "reasoning": "ok"}), \
             patch.object(github_pr, "post_xo_verdict_comment"), \
             patch("core.platform.notification_service.notify", side_effect=RuntimeError("telegram down")):
            batch_coding._run_xo_review_and_notify(
                token="tok", repo="org/repo", pr_url="https://github.com/org/repo/pull/8",
                diff="d", title="pkg 1.0 -> 2.0 (pypi release)", summary="s",
            )  # must not raise


class _FakeHTTPResponse:
    def __init__(self, body: dict):
        self._body = json.dumps(body).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestXoReviewDiff(unittest.TestCase):
    def test_empty_diff_fails_closed_without_a_request(self):
        with patch("core.engineering.xo_review.urllib.request.urlopen") as mocked:
            result = xo_review.review_diff(diff="", mission_title="t", mission_summary="s")
        mocked.assert_not_called()
        self.assertEqual(result["verdict"], "hold")

    def test_valid_approve_verdict_parsed(self):
        payload = {"success": True, "response": json.dumps({
            "verdict": "approve", "authority_check": "ok", "spot_check_findings": "ok", "reasoning": "fine",
        })}
        with patch("core.engineering.xo_review.urllib.request.urlopen", return_value=_FakeHTTPResponse(payload)):
            result = xo_review.review_diff(diff="diff --git a/x", mission_title="t", mission_summary="s")
        self.assertEqual(result["verdict"], "approve")
        self.assertEqual(result["reasoning"], "fine")

    def test_response_wrapped_in_markdown_fence_still_parses(self):
        inner = json.dumps({"verdict": "hold", "authority_check": "a", "spot_check_findings": "b", "reasoning": "c"})
        payload = {"success": True, "response": f"```json\n{inner}\n```"}
        with patch("core.engineering.xo_review.urllib.request.urlopen", return_value=_FakeHTTPResponse(payload)):
            result = xo_review.review_diff(diff="diff --git a/x", mission_title="t", mission_summary="s")
        self.assertEqual(result["verdict"], "hold")

    def test_invalid_verdict_token_fails_closed(self):
        payload = {"success": True, "response": json.dumps({"verdict": "yes", "reasoning": "x"})}
        with patch("core.engineering.xo_review.urllib.request.urlopen", return_value=_FakeHTTPResponse(payload)):
            result = xo_review.review_diff(diff="diff --git a/x", mission_title="t", mission_summary="s")
        self.assertEqual(result["verdict"], "hold")

    def test_non_json_response_fails_closed(self):
        payload = {"success": True, "response": "not json at all"}
        with patch("core.engineering.xo_review.urllib.request.urlopen", return_value=_FakeHTTPResponse(payload)):
            result = xo_review.review_diff(diff="diff --git a/x", mission_title="t", mission_summary="s")
        self.assertEqual(result["verdict"], "hold")

    def test_network_error_fails_closed(self):
        with patch("core.engineering.xo_review.urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            result = xo_review.review_diff(diff="diff --git a/x", mission_title="t", mission_summary="s")
        self.assertEqual(result["verdict"], "hold")

    def test_http_error_extracts_real_error_detail(self):
        error_body = json.dumps({"error": "GEMINI_API_KEY is not set"}).encode()

        class _FakeHTTPError(urllib.error.HTTPError):
            def read(self):
                return error_body

        exc = _FakeHTTPError("url", 500, "Internal Server Error", {}, None)
        with patch("core.engineering.xo_review.urllib.request.urlopen", side_effect=exc):
            result = xo_review.review_diff(diff="diff --git a/x", mission_title="t", mission_summary="s")
        self.assertEqual(result["verdict"], "hold")
        self.assertIn("GEMINI_API_KEY", result["reasoning"])

    def test_empty_model_response_fails_closed(self):
        payload = {"success": True, "response": ""}
        with patch("core.engineering.xo_review.urllib.request.urlopen", return_value=_FakeHTTPResponse(payload)):
            result = xo_review.review_diff(diff="diff --git a/x", mission_title="t", mission_summary="s")
        self.assertEqual(result["verdict"], "hold")


class TestGithubPrVerdictAndMergeHelpers(unittest.TestCase):
    def test_post_and_get_verdict_roundtrip(self):
        comments_store = []

        def fake_api_request(token, method, path, payload=None):
            if method == "POST" and "/comments" in path:
                comments_store.append({"body": payload["body"]})
                return {}
            if method == "GET" and "/comments" in path:
                return comments_store
            raise AssertionError(f"unexpected call {method} {path}")

        with patch.object(github_pr, "_api_request", side_effect=fake_api_request):
            self.assertTrue(github_pr.post_xo_verdict_comment("tok", "org/repo", 1, "approve", "fine"))
            self.assertEqual(github_pr.get_pr_review_verdict("tok", "org/repo", 1), "approve")

    def test_get_verdict_returns_none_when_no_comment_exists(self):
        with patch.object(github_pr, "_api_request", return_value=[]):
            self.assertIsNone(github_pr.get_pr_review_verdict("tok", "org/repo", 1))

    def test_get_verdict_uses_the_most_recent_marked_comment(self):
        comments = [
            {"body": f"{github_pr._XO_VERDICT_MARKER}hold-->old"},
            {"body": f"{github_pr._XO_VERDICT_MARKER}approve-->new"},
        ]
        with patch.object(github_pr, "_api_request", return_value=comments):
            self.assertEqual(github_pr.get_pr_review_verdict("tok", "org/repo", 1), "approve")

    def test_get_verdict_read_failure_returns_none(self):
        with patch.object(github_pr, "_api_request", side_effect=urllib.error.URLError("down")):
            self.assertIsNone(github_pr.get_pr_review_verdict("tok", "org/repo", 1))

    def test_merge_pr_marks_draft_ready_first_then_merges(self):
        calls = []

        def fake_api_request(token, method, path, payload=None):
            calls.append((method, path))
            if method == "GET" and path.endswith("/pulls/9"):
                return {"draft": True, "node_id": "PR_abc"}
            if method == "PUT" and "/merge" in path:
                return {"merged": True}
            raise AssertionError(f"unexpected REST call {method} {path}")

        def fake_graphql(token, query, variables):
            return {"data": {"markPullRequestReadyForReview": {"pullRequest": {"isDraft": False}}}}

        with patch.object(github_pr, "_api_request", side_effect=fake_api_request), \
             patch.object(github_pr, "_graphql_request", side_effect=fake_graphql):
            ok, message = github_pr.merge_pr("tok", "org/repo", 9)
        self.assertTrue(ok)
        self.assertIn("9", message)

    def test_merge_pr_skips_ready_for_review_when_already_ready(self):
        with patch.object(github_pr, "_api_request", side_effect=lambda t, m, p, payload=None: (
            {"draft": False} if m == "GET" else {"merged": True}
        )), patch.object(github_pr, "_mark_pr_ready_for_review") as mocked_ready:
            ok, _ = github_pr.merge_pr("tok", "org/repo", 10)
        self.assertTrue(ok)
        mocked_ready.assert_not_called()

    def test_merge_pr_failed_ready_transition_refuses_to_merge(self):
        with patch.object(github_pr, "_api_request", return_value={"draft": True, "node_id": "PR_x"}), \
             patch.object(github_pr, "_mark_pr_ready_for_review", return_value=False):
            ok, message = github_pr.merge_pr("tok", "org/repo", 11)
        self.assertFalse(ok)
        self.assertIn("ready for review", message)

    def test_merge_pr_http_error_surfaces_detail(self):
        error_body = b'{"message": "not authorized"}'

        class _FakeHTTPError(urllib.error.HTTPError):
            def read(self):
                return error_body

        def fake_api_request(token, method, path, payload=None):
            if method == "GET":
                return {"draft": False}
            raise _FakeHTTPError("url", 403, "Forbidden", {}, None)

        with patch.object(github_pr, "_api_request", side_effect=fake_api_request):
            ok, message = github_pr.merge_pr("tok", "org/repo", 12)
        self.assertFalse(ok)
        self.assertIn("merge failed", message)

    def test_close_pr_posts_comment_and_closes(self):
        calls = []
        with patch.object(github_pr, "_api_request", side_effect=lambda t, m, p, payload=None: calls.append((m, p, payload))):
            ok = github_pr.close_pr("tok", "org/repo", 13, "declined")
        self.assertTrue(ok)
        self.assertIn(("PATCH", "/repos/org/repo/pulls/13", {"state": "closed"}), calls)

    def test_close_pr_failure_returns_false(self):
        with patch.object(github_pr, "_api_request", side_effect=urllib.error.URLError("down")):
            self.assertFalse(github_pr.close_pr("tok", "org/repo", 14))


class TestSynthesizeDeferredDiff(unittest.TestCase):
    def test_builds_unified_diff_against_real_on_disk_content(self):
        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_text", return_value="old line\n"):
            diff = batch_coding._synthesize_deferred_diff(
                ["some/existing_file.py"], {"some/existing_file.py": "new line\n"},
            )
        self.assertIn("-old line", diff)
        self.assertIn("+new line", diff)
        self.assertIn("a/some/existing_file.py", diff)
        self.assertIn("b/some/existing_file.py", diff)

    def test_missing_on_disk_file_diffs_against_empty_string(self):
        with patch("pathlib.Path.exists", return_value=False):
            diff = batch_coding._synthesize_deferred_diff(
                ["some/new_looking_file.py"], {"some/new_looking_file.py": "content\n"},
            )
        self.assertIn("+content", diff)

    def test_fenced_out_file_missing_from_files_dict_is_skipped(self):
        diff = batch_coding._synthesize_deferred_diff(["not/in/files.py"], {})
        self.assertEqual(diff, "")

    def test_unreadable_file_treated_as_empty_old_content(self):
        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_text", side_effect=OSError("boom")):
            diff = batch_coding._synthesize_deferred_diff(
                ["some/existing_file.py"], {"some/existing_file.py": "content\n"},
            )
        self.assertIn("+content", diff)


class TestReviewDeferredFiles(unittest.TestCase):
    def test_returns_none_when_no_deferred_files(self):
        self.assertIsNone(batch_coding._review_deferred_files(
            deferred_existing=[], files={}, title="t", summary="s", custom_id="MSN-1",
        ))

    def test_returns_none_when_synthesized_diff_is_blank(self):
        with patch.object(batch_coding, "_synthesize_deferred_diff", return_value="   "), \
             patch.object(xo_review, "review_diff") as mocked_review:
            result = batch_coding._review_deferred_files(
                deferred_existing=["some/file.py"], files={"some/file.py": "x"},
                title="t", summary="s", custom_id="MSN-1",
            )
        self.assertIsNone(result)
        mocked_review.assert_not_called()

    def test_calls_xo_review_with_the_synthesized_diff_and_notifies(self):
        notify_calls = []
        with patch.object(batch_coding, "_synthesize_deferred_diff", return_value="diff-content"), \
             patch.object(xo_review, "review_diff", return_value={"verdict": "approve", "reasoning": "looks fine"}) as mocked_review, \
             patch("core.platform.notification_service.notify", side_effect=lambda *a, **k: notify_calls.append((a, k))):
            result = batch_coding._review_deferred_files(
                deferred_existing=["some/file.py"], files={"some/file.py": "x"},
                title="Fix a real bug", summary="details", custom_id="MSN-1",
            )
        mocked_review.assert_called_once_with(diff="diff-content", mission_title="Fix a real bug", mission_summary="details")
        self.assertEqual(result["verdict"], "approve")
        self.assertEqual(len(notify_calls), 1)

    def test_xo_review_exception_produces_fail_closed_hold_verdict(self):
        with patch.object(batch_coding, "_synthesize_deferred_diff", return_value="diff-content"), \
             patch.object(xo_review, "review_diff", side_effect=RuntimeError("boom")), \
             patch("core.platform.notification_service.notify"):
            result = batch_coding._review_deferred_files(
                deferred_existing=["some/file.py"], files={"some/file.py": "x"},
                title="t", summary="s", custom_id="MSN-1",
            )
        self.assertEqual(result["verdict"], "hold")
        self.assertIn("boom", result["reasoning"])

    def test_notify_failure_does_not_prevent_review_result_from_being_returned(self):
        with patch.object(batch_coding, "_synthesize_deferred_diff", return_value="diff-content"), \
             patch.object(xo_review, "review_diff", return_value={"verdict": "hold", "reasoning": "needs eyes"}), \
             patch("core.platform.notification_service.notify", side_effect=RuntimeError("telegram down")):
            result = batch_coding._review_deferred_files(
                deferred_existing=["some/file.py"], files={"some/file.py": "x"},
                title="t", summary="s", custom_id="MSN-1",
            )
        self.assertEqual(result["verdict"], "hold")


class TestModelRouterXoReviewPolicy(unittest.TestCase):
    def test_xo_engineering_review_task_type_registered(self):
        sys.path.insert(0, str(REPO_ROOT / "core" / "model-router"))
        import app as router_app
        self.assertIn("xo-engineering-review", router_app.TASK_POLICY)
        self.assertEqual(router_app.TASK_ROUTES.get("/api/model/xo-engineering-review"), "xo-engineering-review")
        policy = router_app.TASK_POLICY["xo-engineering-review"]
        self.assertEqual(policy.get("provider"), "gemini")
        self.assertTrue(policy.get("thinking_level"))


if __name__ == "__main__":
    unittest.main()
