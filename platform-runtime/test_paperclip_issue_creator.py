"""Tests for MSN-0011C — paperclip_issue_creator.py.

Covers:
  - is_issue_creation_request() trigger detection
  - extract_issue_title() noise stripping and truncation
  - resolve_priority() keyword detection and defaults
  - resolve_paperclip_assignee() routing rules
  - build_issue_description() structure
  - create_slack_paperclip_issue() — Paperclip client mocked
  - format_issue_confirmation() Slack mrkdwn
  - format_issue_error() safe error format
  - format_issue_question() clarification format
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

import paperclip_issue_creator as _pic
from paperclip_issue_creator import (
    _AGENT_CHIEF_ENGINEER,
    _AGENT_XO,
    build_issue_description,
    create_slack_paperclip_issue,
    extract_issue_title,
    format_issue_confirmation,
    format_issue_error,
    format_issue_question,
    is_issue_creation_request,
    resolve_paperclip_assignee,
    resolve_priority,
)


# ===========================================================================
# is_issue_creation_request
# ===========================================================================

class TestIsIssueCreationRequest(unittest.TestCase):
    """Trigger phrase detection."""

    def test_create_paperclip_issue(self):
        self.assertTrue(is_issue_creation_request("create a Paperclip issue for fixing the PATH bug"))

    def test_create_issue_bare(self):
        self.assertTrue(is_issue_creation_request("create issue for Chief Engineer to fix bridge"))

    def test_log_this_as_a_task(self):
        self.assertTrue(is_issue_creation_request("log this as a task for Chief Engineer"))

    def test_log_a_task(self):
        self.assertTrue(is_issue_creation_request("log a task to fix the terminal PATH handling"))

    def test_create_task(self):
        self.assertTrue(is_issue_creation_request("create task: review the Slack bridge"))

    def test_open_issue(self):
        self.assertTrue(is_issue_creation_request("open issue for governance review"))

    def test_non_trigger_text(self):
        self.assertFalse(is_issue_creation_request("what should we prioritise next?"))

    def test_empty_string(self):
        self.assertFalse(is_issue_creation_request(""))

    def test_general_commander_question(self):
        self.assertFalse(is_issue_creation_request("recommend the next mission for MSN-0015"))


# ===========================================================================
# extract_issue_title
# ===========================================================================

class TestExtractIssueTitle(unittest.TestCase):
    """Title noise stripping and sensible fallbacks."""

    def test_strips_create_paperclip_issue(self):
        title = extract_issue_title("create a Paperclip issue for fixing the Platypus PATH problem")
        self.assertNotIn("create", title.lower())
        self.assertIn("PATH", title)

    def test_strips_commander_prefix(self):
        title = extract_issue_title("commander: create issue to fix the Slack thread response errors")
        self.assertNotIn("commander:", title.lower())

    def test_strips_at_mention(self):
        title = extract_issue_title("@Commander create issue for review lifecycle governance")
        self.assertNotIn("@Commander", title)

    def test_strips_log_this_as_task(self):
        title = extract_issue_title("log this as a task for Chief Engineer to review the Slack bridge")
        self.assertNotIn("log this as a task", title.lower())

    def test_result_is_not_empty(self):
        title = extract_issue_title("create issue")
        self.assertIsInstance(title, str)
        self.assertTrue(len(title) > 0)

    def test_truncates_to_max_len(self):
        long_text = "create issue for " + ("x " * 100)
        title = extract_issue_title(long_text, max_len=80)
        self.assertLessEqual(len(title), 80)

    def test_empty_input_returns_fallback(self):
        title = extract_issue_title("")
        self.assertIsInstance(title, str)
        self.assertTrue(len(title) > 0)


# ===========================================================================
# resolve_priority
# ===========================================================================

class TestResolvePriority(unittest.TestCase):
    """Priority keyword detection and defaults."""

    def test_high_keyword(self):
        self.assertEqual(resolve_priority("create a high priority issue for PATH fix"), "high")

    def test_critical_keyword(self):
        self.assertEqual(resolve_priority("this is a critical issue"), "urgent")

    def test_urgent_keyword(self):
        self.assertEqual(resolve_priority("urgent: fix this now"), "urgent")

    def test_low_keyword(self):
        self.assertEqual(resolve_priority("low priority improvement"), "low")

    def test_medium_keyword(self):
        self.assertEqual(resolve_priority("medium priority task"), "medium")

    def test_high_priority_phrase(self):
        self.assertEqual(resolve_priority("create high priority issue for Chief Engineer"), "high")

    def test_no_keyword_returns_default(self):
        # Default is 'medium' unless PAPERCLIP_DEFAULT_PRIORITY env var overrides
        result = resolve_priority("create issue for fixing the PATH problem")
        self.assertIn(result, ("urgent", "high", "medium", "low"))

    def test_returns_valid_priority(self):
        for text in ("high", "low", "urgent", "critical", "medium", "no keywords here"):
            p = resolve_priority(text)
            self.assertIn(p, ("urgent", "high", "medium", "low"),
                          f"Invalid priority {p!r} for {text!r}")


# ===========================================================================
# resolve_paperclip_assignee
# ===========================================================================

class TestResolvePaperclipAssignee(unittest.TestCase):
    """Agent routing rules."""

    def test_explicit_chief_engineer_mention(self):
        result = resolve_paperclip_assignee("log a task for Chief Engineer to fix the PATH bug")
        self.assertEqual(result["agent_name"], "Chief Engineer")
        self.assertEqual(result["agent_id"], _AGENT_CHIEF_ENGINEER["id"])

    def test_engineering_keywords_route_to_chief_engineer(self):
        result = resolve_paperclip_assignee("create issue to fix the build script bug")
        self.assertEqual(result["agent_name"], "Chief Engineer")

    def test_code_keyword_routes_to_chief_engineer(self):
        result = resolve_paperclip_assignee("create issue for fixing code in the repo")
        self.assertEqual(result["agent_name"], "Chief Engineer")

    def test_governance_keyword_routes_to_xo(self):
        result = resolve_paperclip_assignee("create issue to review lifecycle governance for MSN-0015B")
        self.assertEqual(result["agent_name"], "XO")

    def test_decision_keyword_routes_to_xo(self):
        result = resolve_paperclip_assignee("create issue for decision on scope alignment")
        self.assertEqual(result["agent_name"], "XO")

    def test_unknown_routes_to_xo_default(self):
        result = resolve_paperclip_assignee("create issue for reviewing the weekly summary")
        self.assertEqual(result["agent_name"], "XO")

    def test_result_has_agent_name_and_id(self):
        result = resolve_paperclip_assignee("any text")
        self.assertIn("agent_name", result)
        self.assertIn("agent_id", result)
        self.assertIsInstance(result["agent_name"], str)
        self.assertIsInstance(result["agent_id"], str)

    def test_path_keyword_routes_to_chief_engineer(self):
        # 'path' is an engineering keyword per mission brief
        result = resolve_paperclip_assignee("fix the Platypus PATH handling problem")
        self.assertEqual(result["agent_name"], "Chief Engineer")


# ===========================================================================
# build_issue_description
# ===========================================================================

class TestBuildIssueDescription(unittest.TestCase):
    """Description structure and metadata."""

    def test_contains_source_slack(self):
        desc = build_issue_description("fix the bug", "C123", "1234.56", "U789")
        self.assertIn("Slack", desc)

    def test_contains_channel_id(self):
        desc = build_issue_description("fix the bug", "C123", "1234.56", "U789")
        self.assertIn("C123", desc)

    def test_contains_thread_ts(self):
        desc = build_issue_description("fix the bug", "C123", "1234.56", "U789")
        self.assertIn("1234.56", desc)

    def test_contains_user_id(self):
        desc = build_issue_description("fix the bug", "C123", "1234.56", "U789")
        self.assertIn("U789", desc)

    def test_contains_original_request(self):
        desc = build_issue_description("fix the specific path bug", "C", "T", "U")
        self.assertIn("fix the specific path bug", desc)

    def test_commander_summary_included_when_provided(self):
        desc = build_issue_description("msg", "C", "T", "U", commander_summary="Summary here")
        self.assertIn("Summary here", desc)

    def test_commander_summary_omitted_when_none(self):
        desc = build_issue_description("msg", "C", "T", "U", commander_summary=None)
        self.assertNotIn("Commander Context", desc)

    def test_none_fields_use_placeholder(self):
        desc = build_issue_description("msg")
        self.assertIn("_unknown_", desc)


# ===========================================================================
# create_slack_paperclip_issue (client mocked)
# ===========================================================================

_UNSET = object()  # sentinel to distinguish None from "not provided"


class TestCreateSlackPaperclipIssue(unittest.TestCase):
    """Paperclip client mocked — tests result dict structure and routing."""

    _DEFAULT_ISSUE = {"id": "uuid-001", "identifier": "STA-3", "title": "Test Issue"}

    def _mock_client(self, is_enabled=True, create_return=_UNSET):
        """Build a MagicMock PaperclipClient."""
        mc = MagicMock()
        mc.is_enabled.return_value = is_enabled
        mc.create_issue.return_value = (
            self._DEFAULT_ISSUE if create_return is _UNSET else create_return
        )
        return mc

    def test_happy_path_returns_ok_true(self):
        mc = self._mock_client()
        with patch.object(_pic, "_CLIENT_AVAILABLE", True), \
             patch.object(_pic, "PaperclipClient", return_value=mc):
            result = create_slack_paperclip_issue(
                message_text="create issue for fixing the PATH bug",
                channel_id="C123",
                thread_ts="1234.56",
                user_id="U789",
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["identifier"], "STA-3")

    def test_happy_path_result_structure(self):
        mc = self._mock_client()
        with patch.object(_pic, "_CLIENT_AVAILABLE", True), \
             patch.object(_pic, "PaperclipClient", return_value=mc):
            result = create_slack_paperclip_issue("create issue for PATH bug", "C", "T", "U")
        for key in ("ok", "issue", "identifier", "title", "priority", "assignee", "error"):
            self.assertIn(key, result)

    def test_paperclip_disabled_returns_ok_false(self):
        mc = self._mock_client(is_enabled=False)
        with patch.object(_pic, "_CLIENT_AVAILABLE", True), \
             patch.object(_pic, "PaperclipClient", return_value=mc):
            result = create_slack_paperclip_issue("create issue for test", "C", "T", "U")
        self.assertFalse(result["ok"])
        self.assertIsNotNone(result["error"])

    def test_client_not_available_returns_ok_false(self):
        with patch.object(_pic, "_CLIENT_AVAILABLE", False):
            result = create_slack_paperclip_issue("create issue for test", "C", "T", "U")
        self.assertFalse(result["ok"])
        self.assertIsNotNone(result["error"])

    def test_create_issue_returns_none_returns_ok_false(self):
        mc = self._mock_client(create_return=None)
        with patch.object(_pic, "_CLIENT_AVAILABLE", True), \
             patch.object(_pic, "PaperclipClient", return_value=mc):
            result = create_slack_paperclip_issue("create issue for test", "C", "T", "U")
        self.assertFalse(result["ok"])

    def test_engineering_message_assigns_chief_engineer(self):
        mc = self._mock_client()
        with patch.object(_pic, "_CLIENT_AVAILABLE", True), \
             patch.object(_pic, "PaperclipClient", return_value=mc):
            result = create_slack_paperclip_issue(
                "create issue for Chief Engineer to fix the build script bug"
            )
        self.assertEqual(result["assignee"]["agent_name"], "Chief Engineer")

    def test_governance_message_assigns_xo(self):
        mc = self._mock_client()
        with patch.object(_pic, "_CLIENT_AVAILABLE", True), \
             patch.object(_pic, "PaperclipClient", return_value=mc):
            result = create_slack_paperclip_issue(
                "create issue to review lifecycle governance for MSN-0015B"
            )
        self.assertEqual(result["assignee"]["agent_name"], "XO")

    def test_high_priority_passed_to_client(self):
        mc = self._mock_client()
        with patch.object(_pic, "_CLIENT_AVAILABLE", True), \
             patch.object(_pic, "PaperclipClient", return_value=mc):
            create_slack_paperclip_issue("create high priority issue for fixing PATH")
        _, kwargs = mc.create_issue.call_args
        self.assertEqual(kwargs.get("priority") or mc.create_issue.call_args[0][2] if mc.create_issue.call_args[0] else kwargs.get("priority"), "high")

    def test_exception_in_create_issue_returns_ok_false(self):
        mc = self._mock_client()
        mc.create_issue.side_effect = RuntimeError("connection refused")
        with patch.object(_pic, "_CLIENT_AVAILABLE", True), \
             patch.object(_pic, "PaperclipClient", return_value=mc):
            result = create_slack_paperclip_issue("create issue for PATH fix")
        self.assertFalse(result["ok"])
        self.assertIn("RuntimeError", result["error"])


# ===========================================================================
# format_issue_confirmation
# ===========================================================================

class TestFormatIssueConfirmation(unittest.TestCase):
    """Slack mrkdwn structure for successful issue creation."""

    def _result(self, **overrides):
        base = {
            "ok": True,
            "issue": {"id": "uuid-001", "identifier": "STA-3"},
            "identifier": "STA-3",
            "title": "Fix PATH handling in Platypus runtime",
            "priority": "high",
            "assignee": {"agent_name": "Chief Engineer", "agent_id": "abc-123"},
            "error": None,
        }
        base.update(overrides)
        return base

    def test_header_is_task_type(self):
        msg = format_issue_confirmation(self._result())
        self.assertIn("*Commander Response — TASK*", msg)

    def test_contains_checkmark_and_created(self):
        msg = format_issue_confirmation(self._result())
        self.assertIn("✅", msg)
        self.assertIn("created", msg.lower())

    def test_contains_identifier(self):
        msg = format_issue_confirmation(self._result())
        self.assertIn("STA-3", msg)

    def test_contains_title(self):
        msg = format_issue_confirmation(self._result())
        self.assertIn("Fix PATH handling", msg)

    def test_contains_assignee(self):
        msg = format_issue_confirmation(self._result())
        self.assertIn("Chief Engineer", msg)

    def test_contains_priority(self):
        msg = format_issue_confirmation(self._result())
        self.assertIn("High", msg)  # capitalised

    def test_lifecycle_state_is_paperclip_issue(self):
        msg = format_issue_confirmation(self._result())
        self.assertIn("PAPERCLIP_ISSUE", msg)

    def test_url_included_when_present(self):
        result = self._result()
        result["issue"]["url"] = "http://127.0.0.1:3100/issue/STA-3"
        msg = format_issue_confirmation(result)
        self.assertIn("http://127.0.0.1:3100/issue/STA-3", msg)

    def test_url_omitted_when_absent(self):
        msg = format_issue_confirmation(self._result())
        self.assertNotIn("http://", msg)

    def test_origin_is_slack(self):
        msg = format_issue_confirmation(self._result())
        self.assertIn("Origin: Slack", msg)


# ===========================================================================
# format_issue_error and format_issue_question
# ===========================================================================

class TestFormatIssueErrorAndQuestion(unittest.TestCase):
    """Safe error and clarification formats."""

    def test_error_header(self):
        msg = format_issue_error("Paperclip returned 500")
        self.assertIn("*Commander Response — ERROR*", msg)

    def test_error_contains_reason(self):
        msg = format_issue_error("Paperclip returned 500")
        self.assertIn("Paperclip returned 500", msg)

    def test_error_no_stack_trace_marker(self):
        msg = format_issue_error("RuntimeError: connection refused")
        # Should not include traceback-style content
        self.assertNotIn("Traceback", msg)
        self.assertNotIn("File \"", msg)

    def test_error_contains_next_step(self):
        msg = format_issue_error("unavailable")
        self.assertIn("Next step", msg)

    def test_question_header(self):
        msg = format_issue_question("What is the issue title?")
        self.assertIn("*Commander Response — QUESTION*", msg)

    def test_question_contains_missing_detail(self):
        msg = format_issue_question("What is the issue title?")
        self.assertIn("What is the issue title?", msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
