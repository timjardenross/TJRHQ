"""
Unit tests for the Phase A HTTP-governance dispatcher (workflow/api.py) and the
escalation watchdog (workflow/escalation.py).
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.analysis.intelligence_analyst import IntelligenceAnalyst
from intelligence.governance.workflow_gate import (
    ANALYST,
    EXECUTIVE_APPROVER,
    INTELLIGENCE_LEAD,
)
from intelligence.workflow import api, escalation, service
from intelligence.workflow.repository import InMemoryRepository


class _NoLLM:
    def generate(self, prompt):
        return None, None


def _scored_event(repo, eid="evt-1", **extra):
    repo.insert_event({"event_id": eid, "raw_title": "Optus outage",
                       "raw_summary": "Optus down", "event_type": "telecom_outage",
                       "geography": "AU", "customer_impact": "high",
                       "signal_status": "TO_COLLECT", **extra})
    service.score_event(repo, IntelligenceAnalyst(llm_provider=_NoLLM()), eid)
    return eid


class TestDispatcher(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryRepository()

    def test_unknown_action_404(self):
        status, body = api.dispatch(self.repo, "signal.nuke", INTELLIGENCE_LEAD, {})
        self.assertEqual(status, 404)

    def test_missing_role_403(self):
        status, body = api.dispatch(self.repo, "signal.verify", "", {"event_id": "x",
                                                                      "confidence_level": "Confirmed"})
        self.assertEqual(status, 403)

    def test_missing_fields_400(self):
        status, body = api.dispatch(self.repo, "signal.verify", INTELLIGENCE_LEAD, {"event_id": "x"})
        self.assertEqual(status, 400)
        self.assertIn("confidence_level", body["error"])

    def test_rbac_denied_403(self):
        eid = _scored_event(self.repo)
        status, body = api.dispatch(self.repo, "signal.verify", ANALYST,
                                    {"event_id": eid, "confidence_level": "Confirmed"})
        self.assertEqual(status, 403)

    def test_not_found_404(self):
        status, body = api.dispatch(self.repo, "signal.verify", INTELLIGENCE_LEAD,
                                    {"event_id": "ghost", "confidence_level": "Confirmed"})
        self.assertEqual(status, 404)

    def test_bad_input_400(self):
        eid = _scored_event(self.repo)
        status, body = api.dispatch(self.repo, "signal.verify", INTELLIGENCE_LEAD,
                                    {"event_id": eid, "confidence_level": "SuperSure"})
        self.assertEqual(status, 400)

    def test_happy_path_200(self):
        eid = _scored_event(self.repo)
        status, body = api.dispatch(self.repo, "signal.verify", INTELLIGENCE_LEAD,
                                    {"event_id": eid, "confidence_level": "Confirmed"})
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["result"]["signal_status"], "VERIFIED")

    def test_publish_flow_via_dispatch(self):
        b = self.repo.insert_brief({"period_start": "a", "period_end": "b"})["brief_id"]
        s, _ = api.dispatch(self.repo, "brief.qa_pass", "system", {"brief_id": b})
        self.assertEqual(s, 200)
        s, body = api.dispatch(self.repo, "brief.publish", EXECUTIVE_APPROVER, {"brief_id": b})
        self.assertEqual(s, 200)
        self.assertEqual(body["result"]["approval_status"], "PUBLISHED")

    def test_extract_role(self):
        self.assertEqual(api.extract_role({"X-User-Role": " intelligence_lead "}), "intelligence_lead")
        self.assertEqual(api.extract_role(None), "")


class TestEscalation(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryRepository()
        self.now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)

    def test_stuck_signal_flagged(self):
        old = (self.now - timedelta(hours=80)).isoformat()
        fresh = (self.now - timedelta(hours=2)).isoformat()
        self.repo.insert_event({"event_id": "old", "signal_status": "VERIFYING", "collected_at": old})
        self.repo.insert_event({"event_id": "new", "signal_status": "VERIFYING", "collected_at": fresh})
        self.repo.insert_event({"event_id": "done", "signal_status": "IN_BRIEF", "collected_at": old})
        found = escalation.find_stuck_signals(self.repo, self.now)
        ids = {f["event_id"] for f in found}
        self.assertEqual(ids, {"old"})
        self.assertEqual(found[0]["escalate_to"], escalation.ESCALATE_XO)

    def test_stuck_brief_qa_passed_escalates_to_captain(self):
        old = (self.now - timedelta(hours=90)).isoformat()
        self.repo.insert_brief({"brief_id": "b1", "approval_status": "QA_PASSED", "generated_at": old})
        self.repo.insert_brief({"brief_id": "b2", "approval_status": "PUBLISHED", "generated_at": old})
        found = escalation.find_stuck_briefs(self.repo, self.now)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["brief_id"], "b1")
        self.assertEqual(found[0]["escalate_to"], escalation.ESCALATE_CAPTAIN)

    def test_lead_unavailable(self):
        self.assertIsNone(escalation.check_lead_availability(
            self.now, (self.now - timedelta(hours=10)).isoformat()))
        flag = escalation.check_lead_availability(
            self.now, (self.now - timedelta(hours=60)).isoformat())
        self.assertIsNotNone(flag)
        self.assertEqual(flag["type"], "lead_unavailable")

    def test_report_aggregates(self):
        old = (self.now - timedelta(hours=90)).isoformat()
        self.repo.insert_event({"event_id": "s", "signal_status": "SCORED", "collected_at": old})
        self.repo.insert_brief({"brief_id": "b", "approval_status": "IN_REVIEW", "generated_at": old})
        report = escalation.escalation_report(
            self.repo, self.now, last_lead_activity=(self.now - timedelta(hours=60)).isoformat())
        self.assertTrue(report["escalations_required"])
        self.assertEqual(report["count"], 3)  # signal + brief + lead


if __name__ == "__main__":
    unittest.main()
