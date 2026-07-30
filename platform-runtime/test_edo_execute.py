"""Tests for the EDO execution runner + dispatch artifacts (EDO-006)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

from lib.delivery import execution  # noqa: E402
import edo_execute  # noqa: E402

MISSION = {"mission_id": "MSN-0099", "title": "Improve Medical Bay dashboard",
           "status": "Designed", "description": "make it better",
           "plan_steps": ["Investigate", "Implement", "Test"]}


class TestArtifacts(unittest.TestCase):
    def test_prepare_dispatch_ok(self):
        art, reason = execution.prepare_dispatch(MISSION, plan_approved=True)
        self.assertEqual(reason, "ok")
        self.assertTrue(art["branch"].startswith("edo/"))
        self.assertTrue(art["draft"])
        self.assertEqual(art["transition"]["to_state"], "in_progress")
        self.assertIn("MSN-0099", art["pr_title"])

    def test_prepare_dispatch_gate(self):
        art, reason = execution.prepare_dispatch(MISSION, plan_approved=False)
        self.assertIsNone(art)
        self.assertIn("plan not approved", reason)

    def test_pr_body_is_draft_and_no_autonomous_merge(self):
        art, _ = execution.prepare_dispatch(MISSION, plan_approved=True)
        body = art["pr_body"]
        self.assertIn("draft", body.lower())
        self.assertIn("XO approval", body)
        self.assertIn("Do not merge", body)

    def test_manifest_carries_governance(self):
        art, _ = execution.prepare_dispatch(MISSION, plan_approved=True)
        self.assertTrue(art["manifest"]["governance"]["no_autonomous_merge"])


class TestRunner(unittest.TestCase):
    def test_run_with_injected_mission(self):
        art, reason = edo_execute.run("MSN-0099", plan_approved=True, mission=MISSION)
        self.assertEqual(reason, "ok")
        self.assertEqual(art["mission_id"], "MSN-0099")

    def test_run_blocks_without_approval(self):
        art, reason = edo_execute.run("MSN-0099", plan_approved=False, mission=MISSION)
        self.assertIsNone(art)

    def test_run_unknown_mission(self):
        with patch.object(edo_execute.data, "fetch_delivery_rows", return_value=[]):
            art, reason = edo_execute.run("MSN-XXXX", plan_approved=True)
        self.assertIsNone(art)
        self.assertIn("no mission found", reason)

    def test_run_finds_mission_in_delivery_rows(self):
        with patch.object(edo_execute.data, "fetch_delivery_rows", return_value=[MISSION]):
            art, reason = edo_execute.run("MSN-0099", plan_approved=True)
        self.assertEqual(reason, "ok")

    def test_main_dry_run_blocked_returns_2(self):
        rc = edo_execute.main(["--mission", "MSN-0099", "--dry-run"])  # no --plan-approved
        self.assertEqual(rc, 2)

    def test_main_dry_run_ok_returns_0(self):
        with patch.object(edo_execute.data, "fetch_delivery_rows", return_value=[MISSION]):
            rc = edo_execute.main(["--mission", "MSN-0099", "--plan-approved", "--dry-run"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
