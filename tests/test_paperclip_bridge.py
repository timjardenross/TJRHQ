"""Tests for MSN-0014B Paperclip Commander Bridge.

Tests PaperclipClient and mission_bridge with mocked HTTP — no live Paperclip
instance required.  All network calls are replaced with in-memory stubs.

Run:
    cd tools/paperclip && python3 ../../test_paperclip_bridge.py -v
    # or from repo root:
    python3 test_paperclip_bridge.py -v
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# Make tools/paperclip importable
sys.path.insert(0, str(Path(__file__).parent / "tools" / "paperclip"))

from client import PaperclipClient  # noqa: E402
from mission_bridge import (  # noqa: E402
    _format_issue_body,
    _format_synthesis_comment,
    _map_priority,
    push_mission_to_paperclip,
    update_paperclip_issue_status,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

COMPANY_ID = "d416eafd-625d-4474-a53e-cc6966689bde"
XO_ID = "664f7f52-15d8-4358-957e-d095868f74e1"
CE_ID = "0b911a35-0c82-420c-86dc-5ca35ae05df4"

_HEALTH_OK = {"status": "ok", "version": "2026.529.0", "deploymentMode": "local_trusted"}

_COMPANY = {"id": COMPANY_ID, "name": "Starfleet HQ", "issuePrefix": "STA"}

_AGENTS = [
    {"id": XO_ID, "name": "XO", "role": "ceo", "urlKey": "xo",
     "adapterConfig": {"model": "ollama/qwen3:8b"}, "status": "idle"},
    {"id": CE_ID, "name": "Chief Engineer", "role": "general", "urlKey": "chief-engineer",
     "adapterConfig": {"model": "ollama/deepseek-coder:6.7b"}, "status": "idle"},
]

_ISSUE = {
    "id": "test-issue-uuid-0001",
    "companyId": COMPANY_ID,
    "title": "Test issue",
    "identifier": "STA-3",
    "issueNumber": 3,
    "status": "todo",
    "priority": "high",
    "assigneeAgentId": XO_ID,
}

_COMMENT = {
    "id": "test-comment-uuid-0001",
    "issueId": "test-issue-uuid-0001",
    "body": "Commander synthesis here",
    "authorUserId": "local-board",
}

_MISSION_CANDIDATE = {
    "mission_candidate_id": "MIS-20260606-120000-000000-abc123",
    "decision_id": "DEC-20260606-120000",
    "title": "Implement Slack Runtime — USS TJR Crew Collaboration",
    "question": "Should USS TJR invest in Slack integration for Commander?",
    "recommended_action": "Proceed with Slack integration as primary Commander interface.",
    "decision_summary": "Commander TJR made a strategic decision in response to...",
    "decision_mode": "strategic",
    "lead_specialist": "Chief of Staff",
    "supporting_specialists": ["Chief Engineer", "Knowledge Officer"],
    "current_bottleneck": "Commander is inaccessible outside the terminal.",
    "opportunity_cost": "Delay means crew cannot act on Commander guidance in real time.",
    "time_to_value": "Short — hours to days.",
    "reversibility": "High — Slack integration is easily reverted.",
    "strategic_alignment": "High — aligns with USS TJR accessibility objectives.",
    "risks": ["Slack token may expire.", "Slack bot requires persistent hosting."],
    "success_criteria": ["Slack bot responds to Commander questions.", "Synthesis visible in channel."],
    "options": [{"description": "Option A: Slack"}, {"description": "Option B: CLI only"}],
    "status": "Draft",
    "github_issue_url": None,
}

_SYNTHESIS = """## Commander TJR — Strategic Decision\n\n## Recommended Action\nProceed with Slack integration.\n\n## Risks\n- Hosting required.\n"""


# ---------------------------------------------------------------------------
# Helper: build a PaperclipClient with mocked _request
# ---------------------------------------------------------------------------

def _mock_client(responses: dict[str, Any]) -> PaperclipClient:
    """Build a PaperclipClient whose _request returns pre-canned responses."""
    pc = PaperclipClient()

    def _fake_request(method: str, path: str, payload=None):
        key = f"{method} {path.split('?')[0]}"  # strip query params
        return responses.get(key, responses.get(path))

    pc._request = _fake_request  # type: ignore[method-assign]
    return pc


# ---------------------------------------------------------------------------
# PaperclipClient unit tests
# ---------------------------------------------------------------------------

class TestPaperclipClientHealth(unittest.TestCase):

    def test_health_ok(self):
        pc = _mock_client({"GET /api/health": _HEALTH_OK})
        self.assertEqual(pc.health()["status"], "ok")

    def test_health_unreachable(self):
        pc = _mock_client({"GET /api/health": None})
        self.assertEqual(pc.health(), {})

    def test_is_enabled_true(self):
        pc = _mock_client({"GET /api/health": _HEALTH_OK})
        with patch.dict("os.environ", {"PAPERCLIP_ENABLED": "true"}):
            self.assertTrue(pc.is_enabled())

    def test_is_enabled_flag_false(self):
        pc = _mock_client({"GET /api/health": _HEALTH_OK})
        with patch.dict("os.environ", {"PAPERCLIP_ENABLED": "false"}):
            self.assertFalse(pc.is_enabled())

    def test_is_enabled_unhealthy(self):
        pc = _mock_client({"GET /api/health": {"status": "error"}})
        self.assertFalse(pc.is_enabled())


class TestPaperclipClientCompanies(unittest.TestCase):

    def test_list_companies(self):
        pc = _mock_client({"GET /api/companies": [_COMPANY]})
        result = pc.list_companies()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], COMPANY_ID)

    def test_list_companies_empty_on_error(self):
        pc = _mock_client({"GET /api/companies": None})
        self.assertEqual(pc.list_companies(), [])

    def test_get_company(self):
        pc = _mock_client({f"GET /api/companies/{COMPANY_ID}": _COMPANY})
        result = pc.get_company(COMPANY_ID)
        self.assertEqual(result["name"], "Starfleet HQ")

    def test_get_company_none_on_error(self):
        pc = _mock_client({f"GET /api/companies/{COMPANY_ID}": None})
        self.assertIsNone(pc.get_company(COMPANY_ID))


class TestPaperclipClientAgents(unittest.TestCase):

    def test_list_agents(self):
        pc = _mock_client({f"GET /api/companies/{COMPANY_ID}/agents": _AGENTS})
        agents = pc.list_agents(COMPANY_ID)
        self.assertEqual(len(agents), 2)
        names = [a["name"] for a in agents]
        self.assertIn("XO", names)
        self.assertIn("Chief Engineer", names)

    def test_agent_id_for_chief_of_staff(self):
        pc = PaperclipClient()
        self.assertEqual(pc.agent_id_for_specialist("Chief of Staff"), pc.xo_agent_id)

    def test_agent_id_for_chief_engineer(self):
        pc = PaperclipClient()
        self.assertEqual(pc.agent_id_for_specialist("Chief Engineer"), pc.chief_engineer_agent_id)

    def test_agent_id_for_coder_agent(self):
        pc = PaperclipClient()
        self.assertEqual(pc.agent_id_for_specialist("Coder Agent"), pc.chief_engineer_agent_id)

    def test_agent_id_unknown_returns_none(self):
        pc = PaperclipClient()
        self.assertIsNone(pc.agent_id_for_specialist("Medical Officer"))


class TestPaperclipClientIssues(unittest.TestCase):

    def test_create_issue(self):
        pc = _mock_client({f"POST /api/companies/{COMPANY_ID}/issues": _ISSUE})
        result = pc.create_issue("Test issue", priority="high", assignee_agent_id=XO_ID)
        self.assertEqual(result["identifier"], "STA-3")

    def test_create_issue_returns_none_on_error(self):
        pc = _mock_client({f"POST /api/companies/{COMPANY_ID}/issues": None})
        self.assertIsNone(pc.create_issue("Test issue"))

    def test_create_issue_returns_none_on_malformed(self):
        pc = _mock_client({f"POST /api/companies/{COMPANY_ID}/issues": {"error": "validation failed"}})
        self.assertIsNone(pc.create_issue("Test issue"))

    def test_get_issue(self):
        pc = _mock_client({"GET /api/issues/test-issue-uuid-0001": _ISSUE})
        result = pc.get_issue("test-issue-uuid-0001")
        self.assertEqual(result["identifier"], "STA-3")

    def test_get_issue_none_on_error(self):
        pc = _mock_client({"GET /api/issues/bad-id": None})
        self.assertIsNone(pc.get_issue("bad-id"))

    def test_update_issue(self):
        updated = {**_ISSUE, "status": "in_progress"}
        pc = _mock_client({"PATCH /api/issues/test-issue-uuid-0001": updated})
        result = pc.update_issue("test-issue-uuid-0001", status="in_progress")
        self.assertEqual(result["status"], "in_progress")

    def test_list_issues(self):
        pc = _mock_client({f"GET /api/companies/{COMPANY_ID}/issues": [_ISSUE]})
        result = pc.list_issues()
        self.assertEqual(result[0]["identifier"], "STA-3")


class TestPaperclipClientComments(unittest.TestCase):

    def test_add_comment(self):
        pc = _mock_client({"POST /api/issues/test-issue-uuid-0001/comments": _COMMENT})
        result = pc.add_comment("test-issue-uuid-0001", "Commander synthesis")
        self.assertEqual(result["id"], "test-comment-uuid-0001")

    def test_add_comment_none_on_error(self):
        pc = _mock_client({"POST /api/issues/test-issue-uuid-0001/comments": None})
        self.assertIsNone(pc.add_comment("test-issue-uuid-0001", "test"))

    def test_list_comments(self):
        pc = _mock_client({"GET /api/issues/test-issue-uuid-0001/comments": [_COMMENT]})
        result = pc.list_comments("test-issue-uuid-0001")
        self.assertEqual(len(result), 1)


# ---------------------------------------------------------------------------
# mission_bridge unit tests
# ---------------------------------------------------------------------------

class TestPriorityMapping(unittest.TestCase):

    def test_strategic_maps_to_high(self):
        c = {**_MISSION_CANDIDATE, "decision_mode": "strategic"}
        self.assertEqual(_map_priority(c), "high")

    def test_explicit_priority_wins(self):
        c = {**_MISSION_CANDIDATE, "priority": "urgent"}
        self.assertEqual(_map_priority(c), "urgent")

    def test_p0_maps_to_urgent(self):
        c = {**_MISSION_CANDIDATE, "priority": "P0"}
        self.assertEqual(_map_priority(c), "urgent")

    def test_operational_maps_to_medium(self):
        c = {**_MISSION_CANDIDATE, "decision_mode": "operational"}
        self.assertEqual(_map_priority(c), "medium")

    def test_governance_maps_to_medium(self):
        c = {**_MISSION_CANDIDATE, "decision_mode": "governance"}
        self.assertEqual(_map_priority(c), "medium")

    def test_unknown_mode_defaults_to_high(self):
        c = {**_MISSION_CANDIDATE, "decision_mode": "unknown"}
        self.assertEqual(_map_priority(c), "high")


class TestIssueBodyFormatter(unittest.TestCase):

    def _body(self, candidate=None):
        return _format_issue_body(candidate or _MISSION_CANDIDATE)

    def test_contains_title(self):
        self.assertIn("Implement Slack Runtime", self._body())

    def test_contains_question(self):
        self.assertIn("Should USS TJR invest", self._body())

    def test_contains_recommended_action(self):
        self.assertIn("Proceed with Slack integration", self._body())

    def test_contains_bottleneck(self):
        self.assertIn("inaccessible outside the terminal", self._body())

    def test_contains_risks(self):
        self.assertIn("Slack token may expire", self._body())

    def test_contains_success_criteria(self):
        self.assertIn("Slack bot responds", self._body())

    def test_contains_lead_specialist(self):
        self.assertIn("Chief of Staff", self._body())

    def test_contains_traceability(self):
        self.assertIn("MIS-20260606", self._body())

    def test_contains_decision_id(self):
        self.assertIn("DEC-20260606", self._body())


class TestSynthesisCommentFormatter(unittest.TestCase):

    def test_contains_commander_heading(self):
        body = _format_synthesis_comment(_SYNTHESIS, _MISSION_CANDIDATE)
        self.assertIn("Commander TJR Synthesis", body)

    def test_contains_synthesis(self):
        body = _format_synthesis_comment(_SYNTHESIS, _MISSION_CANDIDATE)
        self.assertIn("Proceed with Slack integration", body)

    def test_contains_mission_id(self):
        body = _format_synthesis_comment(_SYNTHESIS, _MISSION_CANDIDATE)
        self.assertIn("MIS-20260606", body)

    def test_contains_decision_mode(self):
        body = _format_synthesis_comment(_SYNTHESIS, _MISSION_CANDIDATE)
        self.assertIn("Strategic", body)


class TestPushMissionToPaperclip(unittest.TestCase):

    def _make_client(self):
        responses = {
            "GET /api/health": _HEALTH_OK,
            f"POST /api/companies/{COMPANY_ID}/issues": _ISSUE,
            f"POST /api/issues/{_ISSUE['id']}/comments": _COMMENT,
        }
        return _mock_client(responses)

    def test_happy_path_returns_result(self):
        pc = self._make_client()
        result = push_mission_to_paperclip(_MISSION_CANDIDATE, _SYNTHESIS, client=pc)
        self.assertIsNotNone(result)
        self.assertEqual(result["identifier"], "STA-3")
        self.assertEqual(result["issue_id"], _ISSUE["id"])
        self.assertIsNotNone(result["comment_id"])

    def test_paperclip_disabled_returns_none(self):
        pc = self._make_client()
        with patch.dict("os.environ", {"PAPERCLIP_ENABLED": "false"}):
            result = push_mission_to_paperclip(_MISSION_CANDIDATE, _SYNTHESIS, client=pc)
        self.assertIsNone(result)

    def test_issue_creation_failure_returns_none(self):
        responses = {
            "GET /api/health": _HEALTH_OK,
            f"POST /api/companies/{COMPANY_ID}/issues": None,  # failure
        }
        pc = _mock_client(responses)
        result = push_mission_to_paperclip(_MISSION_CANDIDATE, _SYNTHESIS, client=pc)
        self.assertIsNone(result)

    def test_comment_failure_still_returns_result(self):
        responses = {
            "GET /api/health": _HEALTH_OK,
            f"POST /api/companies/{COMPANY_ID}/issues": _ISSUE,
            f"POST /api/issues/{_ISSUE['id']}/comments": None,  # comment fails
        }
        pc = _mock_client(responses)
        result = push_mission_to_paperclip(_MISSION_CANDIDATE, _SYNTHESIS, client=pc)
        # Issue was created — result should still be returned
        self.assertIsNotNone(result)
        self.assertEqual(result["identifier"], "STA-3")
        self.assertIsNone(result["comment_id"])

    def test_xo_assigned_for_chief_of_staff_lead(self):
        pc = self._make_client()
        result = push_mission_to_paperclip(_MISSION_CANDIDATE, _SYNTHESIS, client=pc)
        # Chief of Staff lead → XO agent
        self.assertEqual(result["assignee_agent_id"], XO_ID)

    def test_chief_engineer_assigned_for_engineering_lead(self):
        candidate = {**_MISSION_CANDIDATE, "lead_specialist": "Chief Engineer"}
        responses = {
            "GET /api/health": _HEALTH_OK,
            f"POST /api/companies/{COMPANY_ID}/issues": {**_ISSUE, "assigneeAgentId": CE_ID},
            f"POST /api/issues/{_ISSUE['id']}/comments": _COMMENT,
        }
        pc = _mock_client(responses)
        result = push_mission_to_paperclip(candidate, _SYNTHESIS, client=pc)
        self.assertEqual(result["assignee_agent_id"], CE_ID)

    def test_paperclip_url_in_result(self):
        pc = self._make_client()
        result = push_mission_to_paperclip(_MISSION_CANDIDATE, _SYNTHESIS, client=pc)
        self.assertIn("STA-3", result["paperclip_url"])


class TestUpdatePaperclipIssueStatus(unittest.TestCase):

    def _make_client(self, updated_issue):
        responses = {
            "GET /api/health": _HEALTH_OK,
            f"PATCH /api/issues/{_ISSUE['id']}": updated_issue,
            f"POST /api/issues/{_ISSUE['id']}/comments": _COMMENT,
        }
        return _mock_client(responses)

    def test_in_progress_maps_correctly(self):
        pc = self._make_client({**_ISSUE, "status": "in_progress"})
        result = update_paperclip_issue_status(_ISSUE["id"], "In Progress", client=pc)
        self.assertTrue(result)

    def test_completed_maps_to_done(self):
        pc = self._make_client({**_ISSUE, "status": "done"})
        result = update_paperclip_issue_status(_ISSUE["id"], "Completed", client=pc)
        self.assertTrue(result)

    def test_deferred_maps_to_cancelled(self):
        pc = self._make_client({**_ISSUE, "status": "cancelled"})
        result = update_paperclip_issue_status(_ISSUE["id"], "Deferred", client=pc)
        self.assertTrue(result)

    def test_disabled_returns_false(self):
        pc = self._make_client({**_ISSUE, "status": "in_progress"})
        with patch.dict("os.environ", {"PAPERCLIP_ENABLED": "false"}):
            result = update_paperclip_issue_status(_ISSUE["id"], "In Progress", client=pc)
        self.assertFalse(result)

    def test_patch_failure_returns_false(self):
        responses = {
            "GET /api/health": _HEALTH_OK,
            f"PATCH /api/issues/{_ISSUE['id']}": None,
        }
        pc = _mock_client(responses)
        result = update_paperclip_issue_status(_ISSUE["id"], "In Progress", client=pc)
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
