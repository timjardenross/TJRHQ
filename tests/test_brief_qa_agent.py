"""
Unit tests for intelligence.audit.brief_qa_agent — the automated data_qa gate
agent. Uses InMemoryRepository throughout (no network), same convention as
tests/test_intelligence_workflow.py.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence.audit.brief_qa_agent import run_data_qa_agent, run_nightly, score_brief
from intelligence.workflow.repository import InMemoryRepository, RepositoryError


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _good_brief(**overrides) -> dict:
    brief = {
        "brief_id": "brf-1",
        "approval_status": "IN_REVIEW",
        "approval_audit": {},
        "generated_at": _now_iso(),
        "overall_risk": "GREEN",
        "confidence": 0.9,
        "executive_snapshot": "Optus outage disrupted mobile services nationwide this period.",
        "bottom_line": "Monitor Optus recovery; no action required today.",
        "emerging_themes": "Telecom sector showing repeated single-point-of-failure incidents.",
        "forward_watch": "Watch for Optus follow-up incident reports over the next 14 days.",
        "cps230_implications": "Operational resilience and continuity risk for a critical third party.",
        "top_events": [
            {"event_id": "evt-1", "title": "Optus outage disrupted mobile services", "risk_rating": "LOW", "source_name": "ABC"},
        ],
    }
    brief.update(overrides)
    return brief


class TestScoreBrief(unittest.TestCase):
    def test_well_formed_green_brief_scores_high_and_passes(self):
        result = score_brief(_good_brief())
        self.assertGreaterEqual(result["overall_score"], 85)
        self.assertTrue(result["passed"])
        self.assertEqual(result["recommendation"], "Approve")

    def test_red_brief_always_fails_regardless_of_score(self):
        result = score_brief(_good_brief(overall_risk="RED"))
        self.assertFalse(result["passed"])
        self.assertEqual(result["recommendation"], "Escalate")

    def test_missing_required_fields_lowers_completeness(self):
        brief = _good_brief(executive_snapshot="", bottom_line=None)
        result = score_brief(brief)
        self.assertLess(result["completeness_score"], 100)
        self.assertFalse(result["passed"])

    def test_green_brief_with_higher_risk_event_flagged(self):
        # overall_risk says GREEN but its own top_events includes a RED item -
        # the real mismatch this check exists to catch.
        brief = _good_brief(overall_risk="GREEN", top_events=[
            {"event_id": "evt-1", "title": "Major outage", "risk_rating": "RED", "source_name": "ABC"},
        ])
        result = score_brief(brief)
        self.assertLess(result["risk_accuracy_score"], 100)

    def test_stale_unreviewed_brief_loses_freshness_score(self):
        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        result = score_brief(_good_brief(generated_at=old))
        self.assertLess(result["freshness_score"], 100)

    def test_unknown_overall_risk_is_not_treated_as_a_pass(self):
        result = score_brief(_good_brief(overall_risk="UNKNOWN"))
        self.assertLess(result["risk_accuracy_score"], 100)

    def test_coherence_score_does_not_leak_the_broken_scale_check(self):
        # brief_coherence_checks()'s 5th sub-check (overall_risk_justified)
        # compares overall_risk against HIGH/CRITICAL/LOW/MEDIUM, but real
        # briefs only ever hold RED/AMBER/GREEN/UNKNOWN - it fails on every
        # real brief regardless of actual composition. coherence_score must
        # only average the 4 reused sub-checks, not that one; a perfectly
        # well-formed brief's coherence_score should be 100 even though the
        # underlying (unused) 5th check reports a mismatch.
        result = score_brief(_good_brief())
        self.assertEqual(result["coherence_score"], 100)
        self.assertFalse(any("does not match event composition" in n for n in result["notes"]))


class TestRunDataQaAgent(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryRepository()
        self.repo.insert_brief(_good_brief())

    def test_dry_run_never_calls_set_qa_gate(self):
        result = run_data_qa_agent(self.repo, "brf-1", dry_run=True)
        self.assertTrue(result["dry_run"])
        brief = self.repo.get_brief("brf-1")
        self.assertEqual(brief["approval_status"], "IN_REVIEW")
        self.assertEqual(brief.get("approval_audit"), {})

    def test_live_run_advances_a_passing_brief_to_data_qa_passed(self):
        result = run_data_qa_agent(self.repo, "brf-1", dry_run=False)
        self.assertEqual(result["gate_status"], "passed")
        brief = self.repo.get_brief("brf-1")
        self.assertEqual(brief["approval_status"], "DATA_QA_PASSED")
        self.assertEqual(brief["approval_audit"]["data_qa"]["status"], "passed")
        self.assertEqual(brief["approval_audit"]["data_qa"]["approved_by"], "system")
        self.assertIn("details", brief["approval_audit"]["data_qa"])

    def test_live_run_on_a_red_brief_leaves_it_in_review(self):
        self.repo.insert_brief(_good_brief(brief_id="brf-2", overall_risk="RED"))
        result = run_data_qa_agent(self.repo, "brf-2", dry_run=False)
        self.assertEqual(result["gate_status"], "failed")
        brief = self.repo.get_brief("brf-2")
        self.assertEqual(brief["approval_status"], "IN_REVIEW")

    def test_unknown_brief_id_raises(self):
        with self.assertRaises(RepositoryError):
            run_data_qa_agent(self.repo, "does-not-exist", dry_run=True)

    def test_only_ever_touches_the_data_qa_gate(self):
        run_data_qa_agent(self.repo, "brf-1", dry_run=False)
        brief = self.repo.get_brief("brf-1")
        self.assertEqual(set(brief["approval_audit"].keys()), {"data_qa"})
        # factual_qa/analytical_qa untouched - a passing data_qa run must never
        # itself grant the human-only gates.
        self.assertNotIn("factual_qa", brief["approval_audit"])
        self.assertNotIn("analytical_qa", brief["approval_audit"])


class TestRunNightly(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryRepository()

    def test_only_scores_briefs_currently_in_review(self):
        self.repo.insert_brief(_good_brief(brief_id="brf-1"))
        self.repo.insert_brief(_good_brief(brief_id="brf-2", approval_status="PUBLISHED"))
        results = run_nightly(self.repo, dry_run=True)
        self.assertEqual([r["brief_id"] for r in results], ["brf-1"])

    def test_a_passed_brief_drops_out_of_the_next_nightly_batch(self):
        self.repo.insert_brief(_good_brief(brief_id="brf-1"))
        run_nightly(self.repo, dry_run=False)
        second_pass = run_nightly(self.repo, dry_run=False)
        self.assertEqual(second_pass, [])

    def test_one_bad_brief_does_not_stop_the_batch(self):
        self.repo.insert_brief(_good_brief(brief_id="brf-1"))
        self.repo.insert_brief(_good_brief(brief_id="brf-2", top_events="not-a-list-should-not-crash"))
        results = run_nightly(self.repo, dry_run=True)
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertNotIn("error", r)


if __name__ == "__main__":
    unittest.main()
