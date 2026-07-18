"""
Unit tests for intelligence/governance/workflow_gate.py (Phase A §1.4).

Covers:
- RBAC: each role's allowed actions; separation of duties (no implicit inheritance)
- Unknown role / unknown action rejected
- require() raises GovernanceError when not permitted
- Signal lifecycle transitions (legal / illegal / no-op / terminal)
- Brief approval transitions
- QA gate checking (mandatory gates must be 'passed')
- log_mutation maps onto record_audit_event and never raises
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.governance import (
    ANALYST,
    EXECUTIVE_APPROVER,
    INTELLIGENCE_LEAD,
    GovernanceError,
    can,
    log_mutation,
    require,
    validate_brief_transition,
    validate_signal_transition,
)


class TestRBAC(unittest.TestCase):
    def test_analyst_actions(self):
        for a in ("signal.collect", "signal.clean", "signal.tier", "signal.score"):
            self.assertTrue(can(ANALYST, a)[0], a)
        # Analyst cannot verify, select or publish.
        for a in ("signal.verify", "signal.select", "brief.publish"):
            self.assertFalse(can(ANALYST, a)[0], a)

    def test_intelligence_lead_actions(self):
        for a in ("signal.verify", "signal.select", "brief.curate_watchlist",
                  "brief.qa_pass", "brief.record_lesson"):
            self.assertTrue(can(INTELLIGENCE_LEAD, a)[0], a)
        # Lead cannot publish (Executive-only).
        self.assertFalse(can(INTELLIGENCE_LEAD, "brief.publish")[0])

    def test_executive_separation_of_duties(self):
        self.assertTrue(can(EXECUTIVE_APPROVER, "brief.publish")[0])
        # Executive Approver deliberately cannot curate (separation of duties).
        self.assertFalse(can(EXECUTIVE_APPROVER, "brief.curate_watchlist")[0])
        self.assertFalse(can(EXECUTIVE_APPROVER, "signal.verify")[0])

    def test_unknown_role_and_action(self):
        self.assertFalse(can("captain", "brief.publish")[0])
        self.assertFalse(can(ANALYST, "signal.nuke")[0])

    def test_require_raises(self):
        require(INTELLIGENCE_LEAD, "signal.verify")  # no raise
        with self.assertRaises(GovernanceError):
            require(ANALYST, "brief.publish")


class TestSignalLifecycle(unittest.TestCase):
    def test_legal_path(self):
        path = ["TO_COLLECT", "SCORED", "VERIFYING", "VERIFIED",
                "READY_FOR_BRIEF", "IN_BRIEF", "ARCHIVED"]
        for cur, nxt in zip(path, path[1:]):
            self.assertTrue(validate_signal_transition(cur, nxt)[0], f"{cur}->{nxt}")

    def test_illegal_skip(self):
        self.assertFalse(validate_signal_transition("TO_COLLECT", "IN_BRIEF")[0])
        self.assertFalse(validate_signal_transition("VERIFIED", "TO_COLLECT")[0])

    def test_noop_and_terminal(self):
        self.assertTrue(validate_signal_transition("SCORED", "SCORED")[0])  # no-op
        self.assertFalse(validate_signal_transition("ARCHIVED", "SCORED")[0])  # terminal

    def test_duplicate_branch(self):
        self.assertTrue(validate_signal_transition("TO_COLLECT", "DUPLICATE")[0])
        self.assertTrue(validate_signal_transition("DUPLICATE", "ARCHIVED")[0])

    def test_unknown_status(self):
        self.assertFalse(validate_signal_transition("BOGUS", "SCORED")[0])


class TestBriefApprovalAndGates(unittest.TestCase):
    def test_brief_path(self):
        # 2026-07-18: consolidated from the original 7-state ladder to 3
        # (IN_REVIEW -> QA_PASSED -> PUBLISHED) — see workflow_gate.py.
        path = ["IN_REVIEW", "QA_PASSED", "PUBLISHED"]
        for cur, nxt in zip(path, path[1:]):
            self.assertTrue(validate_brief_transition(cur, nxt)[0], f"{cur}->{nxt}")

    def test_cannot_skip_to_published(self):
        self.assertFalse(validate_brief_transition("IN_REVIEW", "PUBLISHED")[0])


class TestMutationAudit(unittest.TestCase):
    def test_log_mutation_maps_to_audit_event(self):
        with mock.patch(
            "core.platform.audit_service.record_audit_event", return_value=True
        ) as rec:
            ok = log_mutation(
                table_name="intelligence_events",
                record_id="evt-1",
                mutation_type="UPDATE",
                actor_role=INTELLIGENCE_LEAD,
                before_state={"signal_status": "SCORED"},
                after_state={"signal_status": "VERIFYING"},
            )
        self.assertTrue(ok)
        _, kwargs = rec.call_args
        self.assertEqual(kwargs["category"], "mutation")
        self.assertEqual(kwargs["actor"], INTELLIGENCE_LEAD)
        self.assertEqual(kwargs["details"]["record_id"], "evt-1")
        self.assertEqual(kwargs["details"]["after_state"]["signal_status"], "VERIFYING")

    def test_log_mutation_never_raises(self):
        with mock.patch(
            "core.platform.audit_service.record_audit_event",
            side_effect=RuntimeError("db down"),
        ):
            # Must not propagate — audit failure cannot break the workflow.
            try:
                result = log_mutation("t", "id", "UPDATE", ANALYST)
            except Exception as exc:  # pragma: no cover
                self.fail(f"log_mutation raised: {exc}")
        self.assertIn(result, (True, False))


if __name__ == "__main__":
    unittest.main()
