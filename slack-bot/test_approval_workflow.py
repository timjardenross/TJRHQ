"""Test XO approval workflow with E2E Agent guard rails."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Ensure the slack-bot directory is on the path so commands can be imported
# ---------------------------------------------------------------------------
_SLACK_BOT_DIR = Path(__file__).resolve().parent
if str(_SLACK_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_SLACK_BOT_DIR))

from commands.mission_brief import (
    can_agent_claim_handoff,
    find_existing_engineering_handoff,
    require_explicit_assignment,
    save_engineering_handoff_from_build_record,
    xo_can_approve,
    validate_agent_execution_preconditions,
)
from lib.xo_policy import xo_can_approve as xo_policy_can_approve


def _write_handoff(
    tmp_path: Path,
    *,
    batch_status: str,
    batch_group: str = "BATCH-001",
    assigned_by: str = "",
    source_record: str = "",
) -> Path:
    """Write a minimal engineering handoff file for testing."""
    content = (
        "# Engineering Handoff\n\n"
        "- Status: APPROVED_FOR_ENGINEERING\n"
        f"- Batch Status: {batch_status}\n"
        f"- Batch Group: {batch_group}\n"
        "- Priority: P2\n"
        "- Decision ID: DEC-REC-TEST\n"
        "- Approved At: 2026-06-12 00:00:00\n"
        "- Approved By: U_XO\n"
        f"- Source Build Record: {source_record}\n"
        f"- Assigned By: {assigned_by}\n"
    )
    path = tmp_path / "ENG-HANDOFF-TEST.md"
    path.write_text(content, encoding="utf-8")
    return path


class TestAuthorizationGuard(unittest.TestCase):
    """GUARD: Only the XO system policy can approve."""

    def test_xo_policy_approves_with_full_context(self):
        decision = xo_policy_can_approve({
            "requesting_user": "U_XO",
            "mission_title": "XO Approval Workflow",
            "record_path": "Missions/Build-Records/BUILD-001.md",
            "thread_ts": "111.222",
            "current_status": "APPROVED_FOR_ENGINEERING",
            "current_batch_status": "PENDING",
            "batch_group": "unassigned",
            "priority": "P2",
            "decision_id": "DEC-REC-001",
            "assigned_by": "",
            "guard_rails_ok": "true",
            "validation_evidence": "present",
        })
        self.assertTrue(decision.approved)
        self.assertEqual(decision.resulting_state, "APPROVED_FOR_ENGINEERING + PENDING")
        self.assertNotIn("SUBMITTED", decision.resulting_state)
        self.assertEqual(decision.policy_decision, "APPROVED")

    def test_policy_failure_is_fail_secure(self):
        with patch(
            "lib.xo_policy._load_policy_sources",
            side_effect=RuntimeError("policy backend down"),
        ):
            allowed, reason = xo_can_approve({
                "requesting_user": "U_XO",
                "mission_title": "XO Approval Workflow",
                "record_path": "Missions/Build-Records/BUILD-001.md",
                "thread_ts": "111.222",
                "current_status": "APPROVED_FOR_ENGINEERING",
                "current_batch_status": "PENDING",
                "batch_group": "unassigned",
                "priority": "P2",
                "decision_id": "DEC-REC-001",
                "assigned_by": "",
                "guard_rails_ok": "true",
                "validation_evidence": "present",
            })
            self.assertFalse(allowed)
            self.assertTrue(reason)

    def test_incomplete_context_denied(self):
        decision = xo_policy_can_approve({
                "requesting_user": "U_XO",
                "thread_ts": "111.222",
            })
        self.assertFalse(decision.approved)
        self.assertIn("Missing required policy context fields", decision.decision_reason)

    def test_legacy_wrapper_is_fail_secure(self):
        allowed, reason = xo_can_approve({})
        self.assertFalse(allowed)
        self.assertTrue(reason)

    def test_policy_object_approves_to_pending_only(self):
        with patch(
            "os.environ.get",
            side_effect=lambda k, d="": {
                "XO_SYSTEM_ENABLED": "true",
                "XO_SYSTEM_ROLE": "system",
            }.get(k, d),
        ):
            decision = xo_policy_can_approve({
                "requesting_user": "U_XO",
                "mission_title": "XO Approval Workflow",
                "record_path": "Missions/Build-Records/BUILD-001.md",
                "thread_ts": "111.222",
                "current_status": "APPROVED_FOR_ENGINEERING",
                "current_batch_status": "PENDING",
                "batch_group": "unassigned",
                "priority": "P2",
                "decision_id": "DEC-REC-001",
                "guard_rails_ok": "true",
                "validation_evidence": "present",
            })
            self.assertTrue(decision.approved)
            self.assertEqual(decision.resulting_state, "APPROVED_FOR_ENGINEERING + PENDING")
            self.assertNotIn("SUBMITTED", decision.resulting_state)
            self.assertTrue(decision.policy_trace)


class TestIdempotencyGuard(unittest.TestCase):
    """GUARD: No duplicate handoffs."""

    def test_duplicate_approval_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source = "Missions/Build-Records/BUILD-001.md"
            content = (
                "# Engineering Handoff\n\n"
                f"- Source Build Record: {source}\n"
                "- Status: APPROVED_FOR_ENGINEERING\n"
                "- Batch Status: PENDING\n"
            )
            (tmp_path / "ENG-HANDOFF-001.md").write_text(content, encoding="utf-8")

            import commands.mission_brief as mb

            original_dir = mb._ENGINEERING_HANDOFFS_DIR
            original_root = mb._REPO_ROOT
            mb._ENGINEERING_HANDOFFS_DIR = tmp_path
            mb._REPO_ROOT = tmp_path.parent
            try:
                result = find_existing_engineering_handoff(source)
            finally:
                mb._ENGINEERING_HANDOFFS_DIR = original_dir
                mb._REPO_ROOT = original_root

            self.assertIsNotNone(result)
            self.assertIn("ENG-HANDOFF-001.md", result)

    def test_new_approval_finds_nothing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            import commands.mission_brief as mb

            original_dir = mb._ENGINEERING_HANDOFFS_DIR
            mb._ENGINEERING_HANDOFFS_DIR = tmp_path
            try:
                result = find_existing_engineering_handoff("Missions/Build-Records/BUILD-NONEXISTENT.md")
            finally:
                mb._ENGINEERING_HANDOFFS_DIR = original_dir

            self.assertIsNone(result)


class TestAgentExecutionGuards(unittest.TestCase):
    """GUARD: Agent cannot execute until the handoff is explicit and ready."""

    def test_agent_blocked_pending_status(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            path = _write_handoff(tmp_path, batch_status="PENDING")

            import commands.mission_brief as mb

            original_root = mb._REPO_ROOT
            mb._REPO_ROOT = tmp_path.parent
            try:
                rel = str(path.relative_to(tmp_path.parent))
                result = can_agent_claim_handoff(rel)
            finally:
                mb._REPO_ROOT = original_root

            self.assertFalse(result)

    def test_agent_allowed_submitted_status(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            path = _write_handoff(
                tmp_path,
                batch_status="SUBMITTED",
                batch_group="BATCH-001",
                assigned_by="number_one",
            )

            import commands.mission_brief as mb

            original_root = mb._REPO_ROOT
            mb._REPO_ROOT = tmp_path.parent
            try:
                rel = str(path.relative_to(tmp_path.parent))
                result = can_agent_claim_handoff(rel)
            finally:
                mb._REPO_ROOT = original_root

            self.assertTrue(result)

    def test_explicit_assignment_required(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            path = _write_handoff(
                tmp_path,
                batch_status="SUBMITTED",
                batch_group="BATCH-001",
                assigned_by="",
            )

            import commands.mission_brief as mb

            original_root = mb._REPO_ROOT
            mb._REPO_ROOT = tmp_path.parent
            try:
                rel = str(path.relative_to(tmp_path.parent))
                result = require_explicit_assignment(rel)
            finally:
                mb._REPO_ROOT = original_root

            self.assertFalse(result)


class TestApprovalDoesNotTriggerAgent(unittest.TestCase):
    """CRITICAL: Approval must NOT execute agent."""

    def test_approval_creates_pending_not_submitted(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            import commands.mission_brief as mb

            original_dir = mb._ENGINEERING_HANDOFFS_DIR
            original_root = mb._REPO_ROOT
            mb._ENGINEERING_HANDOFFS_DIR = tmp_path / "Engineering-Handoffs"
            mb._REPO_ROOT = tmp_path
            try:
                build_record = {
                    "record_path": "Missions/Build-Records/BUILD-TEST.md",
                    "request_text": "Add approval workflow",
                    "mission_title": "XO Approval Workflow",
                    "channel_id": "C123",
                    "thread_ts": "111.222",
                    "user_id": "U_XO",
                }
                handoff_path = save_engineering_handoff_from_build_record(build_record, "U_XO")
                content = (tmp_path / handoff_path).read_text(encoding="utf-8")
            finally:
                mb._ENGINEERING_HANDOFFS_DIR = original_dir
                mb._REPO_ROOT = original_root

        self.assertIn("Batch Status: PENDING", content)
        self.assertNotIn("Batch Status: SUBMITTED", content)
        self.assertIn("Approved By: XO", content)
        self.assertIn("Requesting User: U_XO", content)
        self.assertIn("System Actor: XO", content)
        self.assertIn("Policy Decision: APPROVED", content)

    def test_agent_polling_finds_nothing_after_approval(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            path = _write_handoff(tmp_path, batch_status="PENDING", batch_group="unassigned")

            import commands.mission_brief as mb

            original_root = mb._REPO_ROOT
            mb._REPO_ROOT = tmp_path.parent
            try:
                rel = str(path.relative_to(tmp_path.parent))
                can_execute, reason = validate_agent_execution_preconditions(rel)
            finally:
                mb._REPO_ROOT = original_root

            self.assertFalse(can_execute)
            self.assertTrue(reason)
            self.assertTrue("PENDING" in reason or "Guard rail" in reason)


if __name__ == "__main__":
    unittest.main(verbosity=2)
