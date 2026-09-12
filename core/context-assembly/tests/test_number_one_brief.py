"""
Unit tests for context_service.py's _http_number_one_brief() — the
/brief/number-one HTTP endpoint's implementation.

2026-09-08 (USS-TJR-MSN-0054): this endpoint used to hand-roll its own
scoring/blocker/risk logic from scratch. Replaced with a call into the real,
already-tested NumberOne coordination engine (core/coordination/
number_one.py), which had zero live callers anywhere in the platform despite
being more capable (escalations, blocker aging, follow-up detection) than
what this endpoint reimplemented. These tests mock _load_missions() with
synthetic mission dicts so they run without a real Missions/ corpus or
Supabase — the live integration tests in test_captain_brief_integration.py
cover the real-corpus path when the service is actually running.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CA_DIR = _REPO_ROOT / "core" / "context-assembly"
_COORD_DIR = _REPO_ROOT / "core" / "coordination"

for p in (_CA_DIR, _COORD_DIR, _REPO_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import context_service

_SYNTHETIC_MISSIONS = [
    {
        "mission_id": "USS-TJR-MSN-9001",
        "title": "Test blocked mission",
        "status": "Blocked",
        "priority": "P0",
        "domain": "engineering",
        "blockers": ["waiting on infra"],
        "dependencies": [],
        "next_action": "escalate",
        "assigned_role": None,
    },
    {
        "mission_id": "USS-TJR-MSN-9002",
        "title": "Test active mission",
        "status": "Active",
        "priority": "P1",
        "domain": "engineering",
        "blockers": [],
        "dependencies": [],
        "next_action": "continue",
        "assigned_role": "chief-engineer",
    },
]


_SYNTHETIC_HANDOFF = {
    "mission_id": "ENG-HANDOFF-TEST-STALLED",
    "title": "[ENG-HANDOFF] Stalled test handoff",
    "status": "Blocked",
    "priority": "P1",
    "domain": "engineering",
    "blockers": ["no artifact yet"],
    "dependencies": [],
    "next_action": "Triage this",
    "assigned_role": None,
}


class TestHttpNumberOneBrief(unittest.TestCase):
    def _run(self, missions=None):
        # 2026-09-08: Missions/Engineering-Handoffs/ now has real content in
        # this checkout (a separate autonomous process's artifacts, unrelated
        # to this test) — patching only _load_missions isn't hermetic on its
        # own, since _http_number_one_brief() also merges in
        # load_engineering_handoffs()'s real files. Tests that want to
        # exercise that merge explicitly override this patch themselves
        # (test_engineering_handoffs_merged_into_queue,
        # test_engineering_handoff_load_failure_degrades_gracefully).
        with patch.object(context_service, "_load_missions", return_value=missions if missions is not None else _SYNTHETIC_MISSIONS), \
             patch("engineering_handoff_reader.load_engineering_handoffs", return_value=[]):
            return context_service._http_number_one_brief()

    def test_uses_real_engine(self):
        result = self._run()
        self.assertEqual(result["engine"], "number_one_coordination_engine")

    def test_contract_keys_present(self):
        result = self._run()
        for key in (
            "assembled_at", "source", "engine", "generated_at", "system_health",
            "total_missions", "active_count", "blocked_count", "proposed_count",
            "top_priorities", "blocked_missions", "follow_ups", "escalations",
            "specialist_workload", "recommended_actions",
        ):
            self.assertIn(key, result, f"Missing key: {key}")

    def test_total_missions_matches_input(self):
        result = self._run()
        self.assertEqual(result["total_missions"], len(_SYNTHETIC_MISSIONS))

    def test_work_queue_items_are_json_serializable_dicts(self):
        result = self._run()
        self.assertGreater(len(result["top_priorities"]), 0)
        for item in result["top_priorities"]:
            self.assertIsInstance(item, dict)
            for key in ("mission_id", "priority", "status", "title",
                        "assigned_specialist", "next_action", "blockers", "dependencies"):
                self.assertIn(key, item)
            # priority/status/confidence_band must be plain strings (or None),
            # never a raw Enum member — that would break json.dumps upstream
            # (Flask's jsonify would 500 on an unserializable Enum).
            self.assertIsInstance(item["priority"], str)
            self.assertIsInstance(item["status"], str)

    def test_escalations_are_json_serializable_dicts(self):
        result = self._run()
        for esc in result["escalations"]:
            self.assertIsInstance(esc, dict)
            for key in ("escalation_type", "mission_id", "level", "reason", "recommendation"):
                self.assertIn(key, esc)
            self.assertIsInstance(esc["level"], str)

    def test_empty_mission_list_does_not_raise(self):
        result = self._run(missions=[])
        self.assertEqual(result["total_missions"], 0)
        self.assertEqual(result["top_priorities"], [])

    def test_response_is_actually_json_serializable(self):
        import json
        result = self._run()
        json.dumps(result)  # raises if anything (Enum, datetime, dataclass) leaked through

    def test_engineering_handoffs_merged_into_queue(self):
        """load_engineering_handoffs()'s own docstring names Number One's
        advisory queue as its intended consumer, but nothing called it from
        here until now — this is the regression test for that wiring."""
        with patch.object(context_service, "_load_missions", return_value=[]), \
             patch("engineering_handoff_reader.load_engineering_handoffs", return_value=[_SYNTHETIC_HANDOFF]):
            result = context_service._http_number_one_brief()
        self.assertEqual(result["total_missions"], 1)
        ids = [item["mission_id"] for item in result["top_priorities"]]
        self.assertIn("ENG-HANDOFF-TEST-STALLED", ids)

    def test_engineering_handoff_load_failure_degrades_gracefully(self):
        """Missions/Engineering-Handoffs/ not existing (or any other read
        failure) must never break the brief — Number One should still see
        the regular missions."""
        with patch.object(context_service, "_load_missions", return_value=_SYNTHETIC_MISSIONS), \
             patch("engineering_handoff_reader.load_engineering_handoffs", side_effect=OSError("boom")):
            result = context_service._http_number_one_brief()
        self.assertEqual(result["total_missions"], len(_SYNTHETIC_MISSIONS))

    def test_pr_ci_failure_becomes_an_escalation(self):
        """Captain direction (2026-09-08): Number One should catch what a
        non-code-reviewing Captain can't — a red PR is exactly that."""
        mission_with_pr = {
            **_SYNTHETIC_MISSIONS[1],
            "metadata": {"pr_url": "https://github.com/acme/repo/pull/1"},
        }
        with patch.object(context_service, "_load_live_missions_for_number_one", return_value=[mission_with_pr]), \
             patch("engineering_handoff_reader.load_engineering_handoffs", return_value=[]), \
             patch("pr_health.check_pr_health", return_value={
                 "ok": True, "state": "open", "ci_conclusion": "failure",
                 "review_state": None, "mergeable_state": "blocked",
             }):
            result = context_service._http_number_one_brief()
        types = [e["escalation_type"] for e in result["escalations"]]
        self.assertIn("PR_CI_FAILING", types)

    def test_pr_changes_requested_becomes_an_escalation(self):
        mission_with_pr = {
            **_SYNTHETIC_MISSIONS[1],
            "metadata": {"pr_url": "https://github.com/acme/repo/pull/2"},
        }
        with patch.object(context_service, "_load_live_missions_for_number_one", return_value=[mission_with_pr]), \
             patch("engineering_handoff_reader.load_engineering_handoffs", return_value=[]), \
             patch("pr_health.check_pr_health", return_value={
                 "ok": True, "state": "open", "ci_conclusion": "success",
                 "review_state": "CHANGES_REQUESTED", "mergeable_state": "clean",
             }):
            result = context_service._http_number_one_brief()
        types = [e["escalation_type"] for e in result["escalations"]]
        self.assertIn("PR_CHANGES_REQUESTED", types)

    def test_healthy_pr_produces_no_pr_escalation(self):
        mission_with_pr = {
            **_SYNTHETIC_MISSIONS[1],
            "metadata": {"pr_url": "https://github.com/acme/repo/pull/3"},
        }
        with patch.object(context_service, "_load_live_missions_for_number_one", return_value=[mission_with_pr]), \
             patch("engineering_handoff_reader.load_engineering_handoffs", return_value=[]), \
             patch("pr_health.check_pr_health", return_value={
                 "ok": True, "state": "open", "ci_conclusion": "success",
                 "review_state": "APPROVED", "mergeable_state": "clean",
             }):
            result = context_service._http_number_one_brief()
        types = [e["escalation_type"] for e in result["escalations"]]
        self.assertNotIn("PR_CI_FAILING", types)
        self.assertNotIn("PR_CHANGES_REQUESTED", types)

    def test_pr_health_check_failure_degrades_gracefully(self):
        """A GitHub API failure (bad token, rate limit, network) must never
        break the brief — the endpoint must still return a valid response
        with no PR_* escalations added, not raise or 500."""
        mission_with_pr = {
            **_SYNTHETIC_MISSIONS[1],
            "metadata": {"pr_url": "https://github.com/acme/repo/pull/4"},
        }
        with patch.object(context_service, "_load_live_missions_for_number_one", return_value=[mission_with_pr]), \
             patch("engineering_handoff_reader.load_engineering_handoffs", return_value=[]), \
             patch("pr_health.check_pr_health", side_effect=RuntimeError("boom")):
            result = context_service._http_number_one_brief()
        self.assertEqual(result["total_missions"], 1)
        types = [e["escalation_type"] for e in result["escalations"]]
        self.assertNotIn("PR_CI_FAILING", types)
        self.assertNotIn("PR_CHANGES_REQUESTED", types)

    def test_mission_without_pr_url_is_skipped(self):
        with patch.object(context_service, "_load_live_missions_for_number_one", return_value=_SYNTHETIC_MISSIONS), \
             patch("engineering_handoff_reader.load_engineering_handoffs", return_value=[]), \
             patch("pr_health.check_pr_health") as mock_check:
            context_service._http_number_one_brief()
        mock_check.assert_not_called()


if __name__ == "__main__":
    unittest.main()
