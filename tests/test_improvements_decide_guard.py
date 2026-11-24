"""Improvements decide: repeated and conflicting decisions are refused server-side.

Covers scripts/self_improvement/dashboard.py api_opportunity_decide. Skipped when
Flask is not installed (same as the other dashboard tests).
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

import pytest

pytest.importorskip("flask")

from tests.si_dashboard_helpers import si_test_client  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "self_improvement"))

from opportunity_store import OpportunityStore  # noqa: E402


class DecideGuardTests(unittest.TestCase):
    def setUp(self):
        import dashboard
        self.dashboard = dashboard
        self.tmp = Path(tempfile.mkdtemp())
        self.original = dashboard.opportunity_store
        self.store = OpportunityStore(self.tmp)
        dashboard.opportunity_store = self.store
        self.client = si_test_client(dashboard)

    def tearDown(self):
        self.dashboard.opportunity_store = self.original
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _opp(self, state="proposed", **kw):
        return self.store.create_new(
            title="Reduce config sprawl", change_class=kw.pop("change_class", "configuration"),
            discovery_source="internal", lifecycle_state=state,
            provenance=[{"source": "internal_evidence_collector", "location": "config/", "detail": "config_files_count=47"}], **kw)

    def _decide(self, opp, decision, **extra):
        return self.client.post("/api/opportunity/decide", json={"opportunity_id": opp.opportunity_id, "decision_type": decision, **extra})

    def _state(self, opp):
        import lifecycle
        return lifecycle.detail_of(self.store.get(opp.opportunity_id))

    # --- repeats are idempotent --------------------------------------------------
    def test_repeated_approve_is_a_no_op_that_does_not_rerun_the_remediation_bridge(self):
        opp = self._opp(source_finding_id="F-1")
        calls = []
        original = self.dashboard.save_decision
        self.dashboard.save_decision = lambda *a, **k: calls.append(a)
        try:
            first = self._decide(opp, "approve_improvement")
            second = self._decide(opp, "approve_improvement")
        finally:
            self.dashboard.save_decision = original
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.get_json()["unchanged"])
        self.assertIn("opportunity", second.get_json())
        self.assertEqual(len(calls), 1, "the remediation authorisation must be saved once")

    def test_repeated_reject_keeps_the_original_reason(self):
        opp = self._opp()
        self._decide(opp, "reject", reasoning="first reason")
        again = self._decide(opp, "reject", reasoning="second reason")
        self.assertTrue(again.get_json()["unchanged"])
        self.assertEqual(self.store.get(opp.opportunity_id)["rejection_reason"], "first reason")

    def test_repeated_mark_implemented_does_not_restart_the_observation_window(self):
        opp = self._opp()
        self._decide(opp, "approve_improvement")
        self._decide(opp, "mark_implemented")
        started = self.store.get(opp.opportunity_id)["outcome_contract"]["observation_started_at"]
        again = self._decide(opp, "mark_implemented")
        # Already refused by the existing state check (400); nothing is rewritten.
        self.assertEqual(again.status_code, 400)
        self.assertEqual(self.store.get(opp.opportunity_id)["outcome_contract"]["observation_started_at"], started)

    # --- conflicts are refused ---------------------------------------------------
    def test_approve_after_reject_is_refused_and_nothing_changes(self):
        opp = self._opp()
        self._decide(opp, "reject")
        r = self._decide(opp, "approve_improvement")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.get_json()["current_state"], "rejected")
        self.assertEqual(self._state(opp), "rejected")

    def test_reject_after_approve_is_refused(self):
        opp = self._opp()
        self._decide(opp, "approve_improvement")
        self.assertEqual(self._decide(opp, "reject").status_code, 409)
        self.assertEqual(self._state(opp), "approved")

    def test_a_stale_approve_cannot_regress_a_progressed_opportunity(self):
        opp = self._opp(state="implementing")
        self.assertEqual(self._decide(opp, "approve_improvement").status_code, 409)
        self.assertEqual(self._state(opp), "implementing")

    def test_a_second_create_mission_with_a_different_mission_is_refused(self):
        opp = self._opp()
        self.assertEqual(self._decide(opp, "create_mission", mission_id="MSN-1").status_code, 200)
        self.assertEqual(self._decide(opp, "create_mission", mission_id="MSN-2").status_code, 409)
        self.assertEqual(self.store.get(opp.opportunity_id)["mission_id"], "MSN-1")
        # the same mission is a harmless repeat
        self.assertTrue(self._decide(opp, "create_mission", mission_id="MSN-1").get_json()["unchanged"])

    # --- every transition the portal UI uses still works ---------------------------
    def test_ui_transitions_remain_legal(self):
        ok = [
            ("proposed", "approve_improvement", {}), ("proposed", "more_evidence", {"reasoning": "need data"}),
            ("proposed", "reject", {}), ("proposed", "create_mission", {"mission_id": "MSN-9"}),
            ("watching", "turn_into_improvement", {}), ("watching", "not_useful", {}),
            ("rejected", "turn_into_improvement", {}), ("proposed", "keep_watching", {}),
        ]
        for state, decision, extra in ok:
            with self.subTest(state=state, decision=decision):
                opp = self._opp(state=state)
                r = self._decide(opp, decision, **extra)
                self.assertEqual(r.status_code, 200, r.get_json())
                self.assertFalse(r.get_json().get("unchanged", False))

    def test_approved_without_a_mission_can_still_get_one(self):
        opp = self._opp()
        self._decide(opp, "approve_improvement")
        self.assertEqual(self._decide(opp, "create_mission", mission_id="MSN-3").status_code, 200)

    def test_more_evidence_still_accumulates_new_reasons_but_not_the_same_one_twice(self):
        opp = self._opp()
        self._decide(opp, "more_evidence", reasoning="a")
        self._decide(opp, "more_evidence", reasoning="b")
        self._decide(opp, "more_evidence", reasoning="a")
        self.assertEqual(self.store.get(opp.opportunity_id)["missing_evidence"], ["a", "b"])

    # --- concurrency -------------------------------------------------------------
    def test_simultaneous_decisions_apply_exactly_one(self):
        opp = self._opp(source_finding_id="F-2")
        saved = []
        original = self.dashboard.save_decision
        self.dashboard.save_decision = lambda *a, **k: saved.append(a)
        results: list[int] = []

        def go(decision):
            c = si_test_client(self.dashboard)
            results.append(c.post("/api/opportunity/decide", json={"opportunity_id": opp.opportunity_id, "decision_type": decision}).status_code)

        try:
            threads = [threading.Thread(target=go, args=("approve_improvement",)) for _ in range(4)] + [threading.Thread(target=go, args=("reject",)) for _ in range(4)]
            for t in threads: t.start()
            for t in threads: t.join()
        finally:
            self.dashboard.save_decision = original
        final = self._state(opp)
        self.assertIn(final, ("approved", "rejected"))
        # whichever decision won, the opposite one never overwrote it
        self.assertEqual(len(saved), 1 if final == "approved" else 0)


if __name__ == "__main__":
    unittest.main()
