"""
Focused unit tests for the Phase A workflow service + watchlist tracker
(complements the end-to-end tests/test_telstra_poc.py).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.analysis.intelligence_analyst import IntelligenceAnalyst
from intelligence.governance.workflow_gate import (
    ANALYST,
    EXECUTIVE_APPROVER,
    INTELLIGENCE_LEAD,
    GovernanceError,
)
from intelligence.watchlist.tracker import WatchlistTracker, query_matches_event
from intelligence.workflow import service
from intelligence.workflow.repository import InMemoryRepository, RepositoryError


class _NoLLM:
    def generate(self, prompt):
        return None, None


def _seed_scored_event(repo, eid="evt-1"):
    repo.insert_event({"event_id": eid, "raw_title": "Optus outage",
                       "raw_summary": "Optus mobile network down", "event_type": "telecom_outage",
                       "geography": "AU", "customer_impact": "high", "signal_status": "TO_COLLECT"})
    service.score_event(repo, IntelligenceAnalyst(llm_provider=_NoLLM()), eid)
    return eid


class TestServiceEdges(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryRepository()

    def test_verify_rejects_bad_confidence(self):
        eid = _seed_scored_event(self.repo)
        with self.assertRaises(GovernanceError):
            service.verify_event(self.repo, INTELLIGENCE_LEAD, eid, "VeryConfident")

    def test_verify_illegal_from_to_collect(self):
        self.repo.insert_event({"event_id": "e", "raw_title": "x", "signal_status": "TO_COLLECT"})
        with self.assertRaises(GovernanceError):  # TO_COLLECT -> VERIFIED illegal
            service.verify_event(self.repo, INTELLIGENCE_LEAD, "e", "Confirmed")

    def test_missing_event(self):
        with self.assertRaises(GovernanceError):
            service.verify_event(self.repo, INTELLIGENCE_LEAD, "nope", "Confirmed")

    def test_qa_gate_out_of_order_blocked(self):
        b = self.repo.insert_brief({"period_start": "a", "period_end": "b"})["brief_id"]
        # factual before data -> illegal brief transition (IN_REVIEW -> FACTUAL_QA_PASSED)
        with self.assertRaises(GovernanceError):
            service.set_qa_gate(self.repo, INTELLIGENCE_LEAD, b, "factual_qa")

    def test_full_qa_sequence(self):
        b = self.repo.insert_brief({"period_start": "a", "period_end": "b"})["brief_id"]
        service.set_qa_gate(self.repo, "system", b, "data_qa")
        service.set_qa_gate(self.repo, INTELLIGENCE_LEAD, b, "factual_qa")
        service.set_qa_gate(self.repo, INTELLIGENCE_LEAD, b, "analytical_qa")
        out = service.mark_qa_ready(self.repo, INTELLIGENCE_LEAD, b)
        self.assertEqual(out["approval_status"], "QA_READY")
        pub = service.publish_brief(self.repo, EXECUTIVE_APPROVER, b)
        self.assertEqual(pub["approval_status"], "PUBLISHED")

    def test_record_lesson_requires_lead(self):
        b = self.repo.insert_brief({"period_start": "a", "period_end": "b"})["brief_id"]
        with self.assertRaises(GovernanceError):
            service.record_lesson(self.repo, ANALYST, b, "should fail")
        row = service.record_lesson(self.repo, INTELLIGENCE_LEAD, b,
                                    "Comms failures amplified harm", "surprise")
        self.assertEqual(row["category"], "surprise")


class TestWatchlistMatching(unittest.TestCase):
    def test_query_matches(self):
        ev = {"raw_title": "ASIC widens enforcement action",
              "raw_summary": "regulator escalates enforcement against provider"}
        self.assertEqual(query_matches_event({"keyword": "asic", "lookfor": "enforcement"}, ev),
                         (True, 1.0))
        self.assertEqual(query_matches_event({"keyword": "asic"}, ev)[0], True)
        self.assertEqual(query_matches_event({"keyword": "aemo"}, ev), (False, 0.0))
        # lookfor absent -> no match even if keyword present
        self.assertEqual(query_matches_event({"keyword": "asic", "lookfor": "merger"}, ev),
                         (False, 0.0))
        # empty keyword never matches everything
        self.assertEqual(query_matches_event({}, ev), (False, 0.0))

    def test_track_brief_materialization(self):
        repo = InMemoryRepository()
        b = repo.insert_brief({"period_start": "a", "period_end": "b"})["brief_id"]
        repo.insert_watchlist_item({"brief_id": b, "item_text": "asic",
                                    "query": {"keyword": "asic", "lookfor": "enforcement"}})
        repo.insert_watchlist_item({"brief_id": b, "item_text": "backup",
                                    "query": {"keyword": "backup", "lookfor": "redundancy"}})
        nxt = {"event_id": "n1", "raw_title": "ASIC enforcement action escalates",
               "raw_summary": "enforcement widens"}
        summary = WatchlistTracker(repo).track_brief(b, [nxt])
        self.assertEqual(summary, {"items": 2, "materialized": 1, "pending": 1})

    def test_repository_missing_update_raises(self):
        repo = InMemoryRepository()
        with self.assertRaises(RepositoryError):
            repo.update_event("ghost", {"x": 1})


if __name__ == "__main__":
    unittest.main()
