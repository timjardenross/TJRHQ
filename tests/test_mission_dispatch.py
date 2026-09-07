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
from unittest.mock import patch, MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.engineering import mission_dispatch  # noqa: E402


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
        mission_dispatch.record_dispatch(self.tmpdir, "MSN-9001", True, "Draft PR opened")
        mission_dispatch.record_dispatch(self.tmpdir, "MSN-9002", False, "sync-one failed")
        ids = mission_dispatch.load_dispatched_ids(self.tmpdir)
        self.assertEqual(ids, {"MSN-9001", "MSN-9002"})

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
        mission_dispatch.record_dispatch(self.data_root, "MSN-9001", True, "already done")
        with patch("core.engineering.mission_dispatch.fetch_approved_missions", return_value=[make_mission(mission_id="MSN-9001")]), \
             patch("core.engineering.mission_dispatch.dispatch_one") as mock_dispatch:
            results = mission_dispatch.run_cycle(self.repo_root, self.data_root, dry_run=False)
        mock_dispatch.assert_not_called()
        self.assertEqual(results["already_dispatched"], 1)
        self.assertEqual(results["dispatched"], 0)

    def test_successful_dispatch_recorded_and_never_repeated_on_next_call(self):
        with patch("core.engineering.mission_dispatch.fetch_approved_missions", return_value=[make_mission()]), \
             patch("core.engineering.mission_dispatch.dispatch_one", return_value={"success": True, "message": "Draft PR opened: https://x/pr/1"}) as mock_dispatch:
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

    def test_failed_dispatch_still_recorded_so_it_is_not_retried_forever(self):
        with patch("core.engineering.mission_dispatch.fetch_approved_missions", return_value=[make_mission()]), \
             patch("core.engineering.mission_dispatch.dispatch_one", return_value={"success": False, "error": "sync-one exited 1"}):
            results = mission_dispatch.run_cycle(self.repo_root, self.data_root, dry_run=False)
        self.assertEqual(results["failed"], 1)
        self.assertIn("MSN-9001", mission_dispatch.load_dispatched_ids(self.data_root))


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
        self.assertIn("https://github.com/x/y/pull/1", outcome["message"])

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
