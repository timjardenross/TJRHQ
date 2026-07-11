"""Offline tests for the build-request execution verifier (MSN-0356).

Run: python -m unittest core.coordination.tests.test_build_request_verifier
No network / no Supabase: all inputs are fixtures, including a frozen copy
of the real `ca83a08b` row confirmed live in Supabase during this mission's
investigation, so this suite doubles as a regression guard for the specific
defect MSN-0356 was chartered to catch.
"""

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.coordination import build_request_verifier as v  # noqa: E402


# --- fixtures ---------------------------------------------------------------

# Frozen copy of the real defect row (id ca83a08b-...), confirmed live in
# Supabase (project cjvrpjwewsrumnbdydgg) during MSN-0356's investigation.
CA83A08B_ROW = {
    "id": "ca83a08b-cab5-4adf-8e33-f68713e31aa5",
    "request_id": "BREQ-20260618-111042-spawn-xo-and-chief-engineer-authority-and-person",
    "source": "telegram",
    "requested_by": "@tjr1986",
    "title": "Spawn XO and Chief Engineer Authority and Persona System Mission",
    "summary": (
        "Adopt the XO and Chief Engineer persona charters as ship doctrine by creating "
        "a new mission (working title USS-TJR-MSN-0066) that defines authority tiers, "
        "audit rules, rollback requirements, and safe-action boundaries. Build the "
        "missing systems: cross-context introspection, architecture-compliance checker, "
        "work-package tracker, technical-debt scanner, and safe-action execution harness. "
        "Keep MSN-0065 stable as the existing read-only/gated Telegram operator rather "
        "than mutating it in flight."
    ),
    "rationale": (
        "MSN-0065's read-only/PENDING_TRIAGE/approve-tap guardrails intentionally prevent "
        "action orchestration, reducing the Telegram operator to a passive summarizer. The "
        "new XO and Chief Engineer charters require L3-L5 capabilities that cannot be "
        "safely bolted onto MSN-0065 without destabilizing its tested command surface."
    ),
    "status": "approved",
    "action_type": None,
    "action_payload": None,
    "action_result": None,
    "record_path": None,
    "created_at": "2026-06-18T09:10:42.911195+00:00",
}

# A real sibling row (also confirmed live) that mentions "mission" and
# "create" but is NOT a mission-spawn request — exists to guard against the
# false-positive the naive (non-proximity) version of the heuristic produced
# during development.
DEAD_CODE_AUDIT_ROW = {
    "id": "9c51fecc-799e-451c-beed-e76696154b03",
    "request_id": "BREQ-20260618-100438-dead-code-audit-and-deprecation-plan-for-mission",
    "source": "telegram",
    "title": "Dead-Code Audit and Deprecation Plan for Mission Registry and Runtime ID Minting",
    "summary": (
        "Perform a read-only grep-and-classify pass across the codebase to identify dead "
        "or deprecated code, including references to deprecated registry files "
        "(Missions/Mission-Index.md, Missions/Mission-Registry.md), the M-YYYYMMDD-HHMMSS "
        "runtime ID minting path in slack-bot/mission_logger.py, pre-MSN-0061 unwired "
        "Slack handlers, the orphaned /active-pilot-missions build artifact, and old "
        "alias-resolution fallbacks. Deliver a removal/deprecation plan with forwarding "
        "stubs where needed."
    ),
    "rationale": (
        "Deprecated dual registries and identity schemes create drift, risk collisions "
        "with the canonical registry (core/mission-control/registry/mission-index.txt), "
        "and complicate MSN-0064 Path A implementation."
    ),
    "status": "approved",
    "action_type": None,
    "action_payload": None,
    "action_result": None,
    "record_path": None,
    "created_at": "2026-06-18T08:04:38.782892+00:00",
}

REAL_MISSIONS_SNAPSHOT = [
    {"mission_id": "USS-TJR-MSN-0058", "title": "Number One & XO Capability Assessment", "status": "Closed"},
    {"mission_id": "USS-TJR-MSN-0064", "title": "Runtime Mission-ID Repoint to Canonical Mission Control IDs", "status": "Designed"},
]


def _governed_row(**over):
    row = {
        "id": "gov-1", "request_id": "AI-CREATE_MISSION-20260701-ABCDEF", "source": "lcars-ai-console-proposed",
        "title": "Proposed Mission", "status": "approved",
        "action_type": "create_mission",
        "action_payload": {"title": "Proposed Mission"},
        "action_result": {"success": True, "detail": "Mission USS-TJR-MSN-0200 registered", "executed_at": "2026-07-01T00:00:00Z"},
        "record_path": "/missions/USS-TJR-MSN-0200",
    }
    row.update(over)
    return row


class ClassifyLegacyShapeTests(unittest.TestCase):
    def test_flags_the_real_defect_row_as_mission_creation_shaped(self):
        shape, evidence = v.classify_legacy_shape(CA83A08B_ROW)
        self.assertEqual(shape, "create_mission")
        self.assertIn("mission", evidence.lower())

    def test_does_not_false_positive_on_unrelated_mission_and_create_mentions(self):
        shape, _ = v.classify_legacy_shape(DEAD_CODE_AUDIT_ROW)
        self.assertEqual(shape, "other")

    def test_plain_engineering_request_is_other(self):
        row = {"title": "Fix message truncation", "summary": "Split long replies.", "rationale": ""}
        shape, _ = v.classify_legacy_shape(row)
        self.assertEqual(shape, "other")


class VerifyLegacyCreateMissionTests(unittest.TestCase):
    def test_the_real_defect_row_is_not_found_downstream(self):
        """This is the exact case MSN-0356 was chartered to catch: an
        approved 'spawn a mission' request with no matching missions row."""
        status, evidence = v.verify_legacy_create_mission(CA83A08B_ROW, REAL_MISSIONS_SNAPSHOT)
        self.assertEqual(status, "not_found_downstream")
        self.assertIn("0066", evidence)
        self.assertIn("cannot distinguish never-attempted from silently-failed", evidence)

    def test_verified_when_working_title_id_matches_a_real_mission(self):
        row = dict(CA83A08B_ROW)
        missions = REAL_MISSIONS_SNAPSHOT + [{"mission_id": "USS-TJR-MSN-0066", "title": "XO and CE Authority", "status": "Idea"}]
        status, evidence = v.verify_legacy_create_mission(row, missions)
        self.assertEqual(status, "verified")
        self.assertIn("USS-TJR-MSN-0066", evidence)

    def test_verified_by_title_similarity_without_explicit_id(self):
        row = {"title": "Spawn Data Retention Compliance Mission", "summary": "", "rationale": ""}
        missions = [{"mission_id": "USS-TJR-MSN-9001", "title": "Data Retention Compliance Mission", "status": "Idea"}]
        status, evidence = v.verify_legacy_create_mission(row, missions)
        self.assertEqual(status, "verified")
        self.assertIn("similarity", evidence)

    def test_never_returns_failed_for_legacy_rows(self):
        # The legacy path has no attempt record at all, so this checker must
        # never claim to know a "failure" happened — only that nothing was found.
        status, _ = v.verify_legacy_create_mission(CA83A08B_ROW, [])
        self.assertNotEqual(status, "failed")
        self.assertEqual(status, "not_found_downstream")


class VerifyGovernedActionTests(unittest.TestCase):
    def test_create_handoff_is_always_verified(self):
        row = {"action_type": "create_handoff", "action_result": None}
        status, evidence = v.verify_governed_action(row, [], [])
        self.assertEqual(status, "verified")
        self.assertIn("self-fulfilling", evidence)

    def test_not_attempted_when_action_result_missing(self):
        row = {"action_type": "create_mission", "action_result": None, "record_path": None}
        status, _ = v.verify_governed_action(row, [], [])
        self.assertEqual(status, "not_attempted")

    def test_failed_is_distinguished_from_not_attempted(self):
        row = {
            "action_type": "create_mission",
            "action_result": {"success": False, "detail": "duplicate key", "executed_at": "x"},
            "record_path": None,
        }
        status, evidence = v.verify_governed_action(row, [], [])
        self.assertEqual(status, "failed")
        self.assertIn("duplicate key", evidence)

    def test_create_mission_verified_when_mission_row_exists(self):
        row = _governed_row()
        missions = [{"mission_id": "USS-TJR-MSN-0200", "title": "Proposed Mission", "status": "Idea"}]
        status, evidence = v.verify_governed_action(row, missions, [])
        self.assertEqual(status, "verified")
        self.assertIn("agree", evidence)

    def test_create_mission_mismatch_when_claimed_success_but_no_row(self):
        # A success:true action_result with no matching missions row is a
        # stronger signal than "not found" — flag it distinctly.
        row = _governed_row()
        status, evidence = v.verify_governed_action(row, [], [])
        self.assertEqual(status, "mismatch")
        self.assertIn("claims success", evidence)

    def test_log_decision_verified_when_decision_row_exists(self):
        row = {
            "action_type": "log_decision",
            "action_result": {"success": True, "detail": "Decision logged", "executed_at": "x"},
            "record_path": "decision-uuid-1",
        }
        decisions = [{"id": "decision-uuid-1", "decision_title": "x"}]
        status, evidence = v.verify_governed_action(row, [], decisions)
        self.assertEqual(status, "verified")
        self.assertIn("agree", evidence)

    def test_unknown_action_type_is_flagged_not_silently_accepted(self):
        row = {"action_type": "delete_everything", "action_result": {"success": True, "detail": "x"}}
        status, _ = v.verify_governed_action(row, [], [])
        self.assertEqual(status, "unknown_action_type")


class VerifyRequestTests(unittest.TestCase):
    def test_non_approved_rows_are_not_evaluated(self):
        row = {"status": "awaiting_review", "id": "x", "request_id": "x", "title": "x", "source": "x"}
        result = v.verify_request(row, [], [])
        self.assertEqual(result["verification"], "not_approved")

    def test_end_to_end_flags_the_real_defect_row(self):
        result = v.verify_request(CA83A08B_ROW, REAL_MISSIONS_SNAPSHOT, [])
        self.assertEqual(result["verification"], "not_found_downstream")
        self.assertEqual(result["id"], "ca83a08b-cab5-4adf-8e33-f68713e31aa5")
        self.assertIn(result["verification"], v.PROBLEM_STATUSES)

    def test_end_to_end_marks_unrelated_row_out_of_scope_not_flagged(self):
        result = v.verify_request(DEAD_CODE_AUDIT_ROW, REAL_MISSIONS_SNAPSHOT, [])
        self.assertEqual(result["verification"], "out_of_scope")
        self.assertNotIn(result["verification"], v.PROBLEM_STATUSES)


class AuditAndReportTests(unittest.TestCase):
    class FakeClient:
        def __init__(self, breqs, missions, decisions):
            self._breqs, self._missions, self._decisions = breqs, missions, decisions

        def select(self, table, columns="*", filters=None, limit=None):
            if table == "build_request_inbox":
                rows = self._breqs
                if filters and filters.get("status") == "eq.approved":
                    rows = [r for r in rows if r.get("status") == "approved"]
                return rows
            if table == "missions":
                return self._missions
            if table == "commander_decisions":
                return self._decisions
            return []

    def test_audit_end_to_end_flags_exactly_the_defect_row(self):
        client = self.FakeClient(
            breqs=[CA83A08B_ROW, DEAD_CODE_AUDIT_ROW, {"id": "z", "request_id": "z", "title": "z", "source": "z", "status": "awaiting_review"}],
            missions=REAL_MISSIONS_SNAPSHOT,
            decisions=[],
        )
        results = v.audit(client)
        self.assertEqual(len(results), 2)  # awaiting_review row excluded by the status filter
        flagged = [r for r in results if r["verification"] in v.PROBLEM_STATUSES]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0]["id"], "ca83a08b-cab5-4adf-8e33-f68713e31aa5")

    def test_format_report_lists_flagged_row(self):
        report = v.format_report([v.verify_request(CA83A08B_ROW, REAL_MISSIONS_SNAPSHOT, [])])
        self.assertIn("FLAGGED (1)", report)
        self.assertIn("ca83a08b", report)

    def test_format_report_no_flagged_rows(self):
        report = v.format_report([v.verify_request(DEAD_CODE_AUDIT_ROW, REAL_MISSIONS_SNAPSHOT, [])])
        self.assertIn("FLAGGED (0)", report)


if __name__ == "__main__":
    unittest.main()
