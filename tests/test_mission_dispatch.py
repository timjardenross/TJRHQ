"""
Tests for core/engineering/mission_dispatch.py — the Approved-for-
Engineering Mission auto-dispatch that closes the gap where reaching
that status only sent a Slack/Telegram notification and nothing actually
triggered AI implementation.

Never touches real Supabase or the real batch_coding.py subprocess —
everything network/subprocess-shaped is mocked. Never touches real
data/self-improvement/ — every test uses a scratch tmpdir.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.engineering import mission_dispatch


def make_mission(**overrides):
    base = {
        "mission_id": "MSN-9001",
        "title": "Consolidate self-improvement policy config",
        "description": "Establish a single canonical format.",
        "status": "Approved for Engineering",
        "updated_at": "2026-09-06T10:00:00+00:00",
    }
    base.update(overrides)
    return base


class TestDispatchLog(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_no_log_file_means_nothing_dispatched_yet(self):
        self.assertEqual(mission_dispatch.load_dispatched_ids(self.tmpdir), set())

    def test_record_then_load_roundtrip(self):
        mission_dispatch.record_dispatch(self.tmpdir, "MSN-9001", True, "Draft PR opened", pr_opened=True)
        mission_dispatch.record_dispatch(self.tmpdir, "MSN-9002", False, "sync-one failed")
        ids = mission_dispatch.load_dispatched_ids(self.tmpdir)
        # A single failure is a retry candidate, not "done" — only the
        # successful mission counts as dispatched (see module comment above
        # load_dispatched_ids: this used to wrongly include both).
        self.assertEqual(ids, {"MSN-9001"})

    def test_success_without_a_pr_is_not_permanently_dispatched(self):
        """2026-09-26 fix: "coded fine, no PR" must not be treated the same
        as "fully delivered" — see _dispatch_history's own docstring for
        the real incident (7 Missions stuck forever once the XO-review
        gate could have opened a PR for them, but never got the chance)."""
        mission_dispatch.record_dispatch(self.tmpdir, "MSN-9001", True, "coded, no PR (no new files to add)")
        self.assertEqual(mission_dispatch.load_dispatched_ids(self.tmpdir), set())

    def test_success_without_a_pr_below_the_retry_cap_stays_eligible(self):
        for _ in range(mission_dispatch.MAX_DISPATCH_ATTEMPTS - 1):
            mission_dispatch.record_dispatch(self.tmpdir, "MSN-9001", True, "coded, no PR")
        self.assertEqual(mission_dispatch.load_dispatched_ids(self.tmpdir), set())

    def test_success_without_a_pr_at_the_retry_cap_stops_being_retried(self):
        for _ in range(mission_dispatch.MAX_DISPATCH_ATTEMPTS):
            mission_dispatch.record_dispatch(self.tmpdir, "MSN-9001", True, "coded, no PR")
        self.assertEqual(mission_dispatch.load_dispatched_ids(self.tmpdir), {"MSN-9001"})

    def test_a_pr_opening_after_several_no_pr_successes_marks_it_permanently_done(self):
        """The exact scenario this fix exists for: a Mission coded without
        a PR a couple of times (old code, or a title that didn't qualify
        yet), then a capability change (e.g. the XO-review gate) lets a
        later attempt actually open one — that must lock in as done, not
        keep retrying."""
        mission_dispatch.record_dispatch(self.tmpdir, "MSN-9001", True, "coded, no PR")
        mission_dispatch.record_dispatch(self.tmpdir, "MSN-9001", True, "coded, no PR")
        mission_dispatch.record_dispatch(self.tmpdir, "MSN-9001", True, "Draft PR opened", pr_opened=True)
        self.assertEqual(mission_dispatch.load_dispatched_ids(self.tmpdir), {"MSN-9001"})

    def test_a_single_failure_is_not_treated_as_dispatched(self):
        mission_dispatch.record_dispatch(self.tmpdir, "MSN-9001", False, "sync-one exited 1")
        self.assertEqual(mission_dispatch.load_dispatched_ids(self.tmpdir), set())

    def test_failures_below_the_retry_cap_are_not_treated_as_dispatched(self):
        for _ in range(mission_dispatch.MAX_DISPATCH_ATTEMPTS - 1):
            mission_dispatch.record_dispatch(self.tmpdir, "MSN-9001", False, "sync-one exited 1")
        self.assertEqual(mission_dispatch.load_dispatched_ids(self.tmpdir), set())

    def test_failures_at_the_retry_cap_stop_being_retried(self):
        for _ in range(mission_dispatch.MAX_DISPATCH_ATTEMPTS):
            mission_dispatch.record_dispatch(self.tmpdir, "MSN-9001", False, "sync-one exited 1")
        self.assertEqual(mission_dispatch.load_dispatched_ids(self.tmpdir), {"MSN-9001"})

    def test_a_success_resets_the_failure_streak(self):
        mission_dispatch.record_dispatch(self.tmpdir, "MSN-9001", False, "sync-one exited 1")
        mission_dispatch.record_dispatch(self.tmpdir, "MSN-9001", False, "sync-one exited 1")
        mission_dispatch.record_dispatch(self.tmpdir, "MSN-9001", True, "Draft PR opened", pr_opened=True)
        # Two failures then a success-with-PR: the streak that mattered
        # ended in a real delivery, so this mission is done (not
        # exhausted-and-stuck).
        self.assertEqual(mission_dispatch.load_dispatched_ids(self.tmpdir), {"MSN-9001"})

    def test_corrupt_log_line_never_raises(self):
        log_path = self.tmpdir / "review" / mission_dispatch.DISPATCH_LOG_NAME
        log_path.parent.mkdir(parents=True)
        log_path.write_text("not json\n")
        self.assertEqual(mission_dispatch.load_dispatched_ids(self.tmpdir), set())


class TestFetchApprovedMissions(unittest.TestCase):
    def test_supabase_failure_returns_empty_list_never_raises(self):
        with patch("core.engineering.mission_dispatch.supabase_get", side_effect=RuntimeError("no creds")):
            self.assertEqual(mission_dispatch.fetch_approved_missions(), [])

    def test_queries_the_correct_status_value(self):
        with patch("core.engineering.mission_dispatch.supabase_get", return_value=[]) as mock_get:
            mission_dispatch.fetch_approved_missions(limit=10)
        called_path = mock_get.call_args[0][0]
        self.assertIn("status=eq.Approved%20for%20Engineering", called_path)
        self.assertIn("limit=10", called_path)


class TestWriteHandoffFile(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_writes_a_real_handoff_file_with_expected_sections(self):
        mission = make_mission()
        path = mission_dispatch.write_handoff_file(self.tmpdir, mission)
        self.assertTrue(path.exists())
        content = path.read_text()
        self.assertIn("- Status: APPROVED_FOR_ENGINEERING", content)
        self.assertIn("- Batch Status: PENDING", content)
        self.assertIn("## Mission Title", content)
        self.assertIn(mission["title"], content)
        self.assertIn(mission["description"], content)
        self.assertIn("draft PR only", content)

    def test_missing_description_never_raises_and_says_so(self):
        mission = make_mission(description=None)
        path = mission_dispatch.write_handoff_file(self.tmpdir, mission)
        self.assertIn("no description recorded", path.read_text())

    def test_retry_for_same_mission_replaces_prior_file_not_duplicates_it(self):
        mission = make_mission()
        handoffs_dir = self.tmpdir / "Missions" / "Engineering-Handoffs"
        first = mission_dispatch.write_handoff_file(self.tmpdir, mission)
        second = mission_dispatch.write_handoff_file(self.tmpdir, mission)
        matches = list(handoffs_dir.glob(f"ENG-HANDOFF-{mission['mission_id']}-*.md"))
        self.assertEqual(len(matches), 1, "a retry for the same mission_id must not leave a stale duplicate file behind")
        self.assertTrue(second.exists())
        self.assertFalse(first.exists() and first != second)

    def test_retry_for_different_mission_does_not_touch_other_missions_files(self):
        mission_a = make_mission(mission_id="MSN-AAA")
        mission_b = make_mission(mission_id="MSN-BBB")
        handoffs_dir = self.tmpdir / "Missions" / "Engineering-Handoffs"
        path_a = mission_dispatch.write_handoff_file(self.tmpdir, mission_a)
        mission_dispatch.write_handoff_file(self.tmpdir, mission_b)
        mission_dispatch.write_handoff_file(self.tmpdir, mission_b)
        self.assertTrue(path_a.exists(), "a retry for a different mission_id must not remove another mission's file")
        self.assertEqual(len(list(handoffs_dir.glob("ENG-HANDOFF-MSN-BBB-*.md"))), 1)


class TestRunCycle(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.repo_root = self.tmpdir / "repo"
        self.data_root = self.tmpdir / "data"
        self.repo_root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_dry_run_never_writes_the_dispatch_log(self):
        with patch("core.engineering.mission_dispatch.fetch_approved_missions", return_value=[make_mission()]):
            results = mission_dispatch.run_cycle(self.repo_root, self.data_root, dry_run=True)
        self.assertEqual(results["dispatched"], 1)
        self.assertFalse((self.data_root / "review" / mission_dispatch.DISPATCH_LOG_NAME).exists())

    def test_already_dispatched_mission_is_never_dispatched_twice(self):
        mission_dispatch.record_dispatch(self.data_root, "MSN-9001", True, "already done", pr_opened=True)
        with patch("core.engineering.mission_dispatch.fetch_approved_missions", return_value=[make_mission(mission_id="MSN-9001")]), \
             patch("core.engineering.mission_dispatch.dispatch_one") as mock_dispatch:
            results = mission_dispatch.run_cycle(self.repo_root, self.data_root, dry_run=False)
        mock_dispatch.assert_not_called()
        self.assertEqual(results["already_dispatched"], 1)
        self.assertEqual(results["dispatched"], 0)

    def test_successful_dispatch_recorded_and_never_repeated_on_next_call(self):
        with patch("core.engineering.mission_dispatch.fetch_approved_missions", return_value=[make_mission()]), \
             patch("core.engineering.mission_dispatch.dispatch_one", return_value={"success": True, "pr_opened": True, "message": "Draft PR opened: https://x/pr/1"}) as mock_dispatch:
            first = mission_dispatch.run_cycle(self.repo_root, self.data_root, dry_run=False)
        mock_dispatch.assert_called_once()
        self.assertEqual(first["dispatched"], 1)

        # Second cycle, same mission still "Approved for Engineering" in
        # Supabase (nobody's moved it on) — must not re-dispatch.
        with patch("core.engineering.mission_dispatch.fetch_approved_missions", return_value=[make_mission()]), \
             patch("core.engineering.mission_dispatch.dispatch_one") as mock_dispatch_again:
            second = mission_dispatch.run_cycle(self.repo_root, self.data_root, dry_run=False)
        mock_dispatch_again.assert_not_called()
        self.assertEqual(second["already_dispatched"], 1)

    def test_failed_dispatch_is_retried_on_the_next_cycle(self):
        with patch("core.engineering.mission_dispatch.fetch_approved_missions", return_value=[make_mission()]), \
             patch("core.engineering.mission_dispatch.dispatch_one", return_value={"success": False, "error": "sync-one exited 1"}):
            results = mission_dispatch.run_cycle(self.repo_root, self.data_root, dry_run=False)
        self.assertEqual(results["failed"], 1)
        # A transient failure must not permanently block the Mission — see
        # this module's own deploy/mission-engineering-dispatch.service
        # comment: "a retry after a transient failure is always safe."
        self.assertNotIn("MSN-9001", mission_dispatch.load_dispatched_ids(self.data_root))

        with patch("core.engineering.mission_dispatch.fetch_approved_missions", return_value=[make_mission()]), \
             patch("core.engineering.mission_dispatch.dispatch_one", return_value={"success": False, "error": "sync-one exited 1"}) as mock_dispatch_again:
            mission_dispatch.run_cycle(self.repo_root, self.data_root, dry_run=False)
        mock_dispatch_again.assert_called_once()  # actually retried, not skipped

    def test_failed_dispatch_gives_up_after_the_retry_cap_and_says_so(self):
        with patch("core.engineering.mission_dispatch.fetch_approved_missions", return_value=[make_mission()]), \
             patch("core.engineering.mission_dispatch.dispatch_one", return_value={"success": False, "error": "sync-one exited 1"}):
            for _ in range(mission_dispatch.MAX_DISPATCH_ATTEMPTS):
                mission_dispatch.run_cycle(self.repo_root, self.data_root, dry_run=False)

        # Now permanently skipped — the retry budget is spent.
        self.assertIn("MSN-9001", mission_dispatch.load_dispatched_ids(self.data_root))
        with patch("core.engineering.mission_dispatch.fetch_approved_missions", return_value=[make_mission()]), \
             patch("core.engineering.mission_dispatch.dispatch_one") as mock_dispatch:
            results = mission_dispatch.run_cycle(self.repo_root, self.data_root, dry_run=False)
        mock_dispatch.assert_not_called()
        self.assertEqual(results["already_dispatched"], 1)

        # The Captain-facing message on the exhausting attempt must say it
        # gave up (mission-dispatch-status only ever surfaces the latest
        # record per mission_id — see dashboard.py's load_mission_dispatch_log).
        log_path = self.data_root / "review" / mission_dispatch.DISPATCH_LOG_NAME
        last_line = log_path.read_text().strip().splitlines()[-1]
        self.assertIn("giving up", json.loads(last_line)["message"])

    def test_success_without_pr_is_retried_on_the_next_cycle(self):
        """The real 2026-09-26 bug: coded fine, no PR — must remain a
        retry candidate (e.g. a later capability change, like the
        XO-review gate, might open one), not be treated as done."""
        with patch("core.engineering.mission_dispatch.fetch_approved_missions", return_value=[make_mission()]), \
             patch("core.engineering.mission_dispatch.dispatch_one", return_value={"success": True, "pr_opened": False, "message": "coded, no PR"}):
            results = mission_dispatch.run_cycle(self.repo_root, self.data_root, dry_run=False)
        self.assertEqual(results["dispatched"], 1)
        self.assertNotIn("MSN-9001", mission_dispatch.load_dispatched_ids(self.data_root))

        with patch("core.engineering.mission_dispatch.fetch_approved_missions", return_value=[make_mission()]), \
             patch("core.engineering.mission_dispatch.dispatch_one", return_value={"success": True, "pr_opened": False, "message": "coded, no PR"}) as mock_dispatch_again:
            mission_dispatch.run_cycle(self.repo_root, self.data_root, dry_run=False)
        mock_dispatch_again.assert_called_once()  # actually retried, not skipped

    def test_success_without_pr_gives_up_after_the_retry_cap_and_says_so(self):
        with patch("core.engineering.mission_dispatch.fetch_approved_missions", return_value=[make_mission()]), \
             patch("core.engineering.mission_dispatch.dispatch_one", return_value={"success": True, "pr_opened": False, "message": "coded, no PR"}):
            for _ in range(mission_dispatch.MAX_DISPATCH_ATTEMPTS):
                mission_dispatch.run_cycle(self.repo_root, self.data_root, dry_run=False)

        self.assertIn("MSN-9001", mission_dispatch.load_dispatched_ids(self.data_root))
        with patch("core.engineering.mission_dispatch.fetch_approved_missions", return_value=[make_mission()]), \
             patch("core.engineering.mission_dispatch.dispatch_one") as mock_dispatch:
            results = mission_dispatch.run_cycle(self.repo_root, self.data_root, dry_run=False)
        mock_dispatch.assert_not_called()
        self.assertEqual(results["already_dispatched"], 1)

        log_path = self.data_root / "review" / mission_dispatch.DISPATCH_LOG_NAME
        last_line = log_path.read_text().strip().splitlines()[-1]
        self.assertIn("giving up", json.loads(last_line)["message"])

    def test_pr_opening_after_no_pr_attempts_stops_further_retries(self):
        """A later cycle that finally opens a PR (e.g. the mission's title
        now qualifies under the XO-review gate) must lock the mission in
        as permanently done, same as if it had opened first try."""
        with patch("core.engineering.mission_dispatch.fetch_approved_missions", return_value=[make_mission()]), \
             patch("core.engineering.mission_dispatch.dispatch_one", return_value={"success": True, "pr_opened": False, "message": "coded, no PR"}):
            mission_dispatch.run_cycle(self.repo_root, self.data_root, dry_run=False)

        with patch("core.engineering.mission_dispatch.fetch_approved_missions", return_value=[make_mission()]), \
             patch("core.engineering.mission_dispatch.dispatch_one", return_value={"success": True, "pr_opened": True, "message": "Draft PR opened"}):
            mission_dispatch.run_cycle(self.repo_root, self.data_root, dry_run=False)

        self.assertIn("MSN-9001", mission_dispatch.load_dispatched_ids(self.data_root))
        with patch("core.engineering.mission_dispatch.fetch_approved_missions", return_value=[make_mission()]), \
             patch("core.engineering.mission_dispatch.dispatch_one") as mock_dispatch:
            mission_dispatch.run_cycle(self.repo_root, self.data_root, dry_run=False)
        mock_dispatch.assert_not_called()


class TestDispatchOneSubprocessHandling(unittest.TestCase):
    """Mirrors HandoffPRStrategy's own subprocess result handling exactly
    — never invokes a real subprocess, but the mocked-out surface must
    match auto_remediation.py's proven contract."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_successful_delivery_with_pr_url(self):
        fake_result = MagicMock(returncode=0, stdout=json.dumps({"status": "delivered", "pr_url": "https://github.com/x/y/pull/1"}), stderr="")
        with patch("core.engineering.mission_dispatch.subprocess.run", return_value=fake_result):
            outcome = mission_dispatch.dispatch_one(self.tmpdir, make_mission())
        self.assertTrue(outcome["success"])
        self.assertTrue(outcome["pr_opened"])
        self.assertIn("https://github.com/x/y/pull/1", outcome["message"])

    def test_successful_delivery_without_pr_url_reports_pr_opened_false(self):
        fake_result = MagicMock(returncode=0, stdout=json.dumps({"status": "delivered", "artifact": "some/path.patch.md"}), stderr="")
        with patch("core.engineering.mission_dispatch.subprocess.run", return_value=fake_result):
            outcome = mission_dispatch.dispatch_one(self.tmpdir, make_mission())
        self.assertTrue(outcome["success"])
        self.assertFalse(outcome["pr_opened"])

    def test_nonzero_exit_is_reported_as_failure(self):
        fake_result = MagicMock(returncode=1, stdout="", stderr="traceback here")
        with patch("core.engineering.mission_dispatch.subprocess.run", return_value=fake_result):
            outcome = mission_dispatch.dispatch_one(self.tmpdir, make_mission())
        self.assertFalse(outcome["success"])

    def test_subprocess_exception_is_caught_not_raised(self):
        with patch("core.engineering.mission_dispatch.subprocess.run", side_effect=OSError("no venv")):
            outcome = mission_dispatch.dispatch_one(self.tmpdir, make_mission())
        self.assertFalse(outcome["success"])

    def test_unparseable_stdout_is_reported_as_failure_not_raised(self):
        fake_result = MagicMock(returncode=0, stdout="not json", stderr="")
        with patch("core.engineering.mission_dispatch.subprocess.run", return_value=fake_result):
            outcome = mission_dispatch.dispatch_one(self.tmpdir, make_mission())
        self.assertFalse(outcome["success"])


if __name__ == "__main__":
    unittest.main()
