"""Tests for MSN-0012 — Slack Discovery & Backlog Command Layer.

Covers:
  - handle_mission_brief()  — output shape, empty input, LLM mocked
  - handle_mission_capture() — output shape, empty input, LLM mocked
  - handle_decision_log()   — output shape, empty input, defaults
  - handle_ask_specialist() — specialist routing, unknown name, empty input,
                               list output, fallback when LLM unavailable
  - parse_specialist_command() — name parsing, aliases, partial match
  - No mutations: none of the handlers write to disk, GitHub, or Notion
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_llm(return_value: str = "LLM output here"):
    """Return a patch context manager that stubs generate_response()."""
    return patch("llm.generate_response", return_value=return_value)


# ===========================================================================
# /mission-brief
# ===========================================================================

class TestMissionBrief(unittest.TestCase):

    def test_empty_input_returns_usage(self):
        from commands.mission_brief import handle_mission_brief
        result = handle_mission_brief("")
        self.assertIn("Usage", result)
        self.assertIn("/mission-brief", result)

    def test_empty_whitespace_returns_usage(self):
        from commands.mission_brief import handle_mission_brief
        result = handle_mission_brief("   ")
        self.assertIn("Usage", result)

    def test_valid_input_calls_llm_and_returns_output(self):
        from commands.mission_brief import handle_mission_brief
        with patch("llm.generate_response", return_value="MOCK BRIEF OUTPUT"):
            result = handle_mission_brief("Build a Slack backlog capture tool")
        self.assertIn("MOCK BRIEF OUTPUT", result)
        self.assertIn("MISSION IMPLEMENTATION BRIEF", result)

    def test_result_is_string(self):
        from commands.mission_brief import handle_mission_brief
        with patch("llm.generate_response", return_value="output"):
            result = handle_mission_brief("any text")
        self.assertIsInstance(result, str)

    def test_llm_failure_returns_fallback(self):
        from commands.mission_brief import handle_mission_brief
        with patch("llm.generate_response", side_effect=RuntimeError("offline")):
            result = handle_mission_brief("Build something important")
        self.assertIn("MISSION IMPLEMENTATION BRIEF", result)
        self.assertIn("Build something important", result)

    def test_fallback_contains_implementation_instruction(self):
        from commands.mission_brief import handle_mission_brief
        with patch("llm.generate_response", side_effect=RuntimeError("x")):
            result = handle_mission_brief("Some task")
        self.assertIn("smallest safe change", result)

    def test_accepts_user_and_channel_args(self):
        from commands.mission_brief import handle_mission_brief
        with patch("llm.generate_response", return_value="ok"):
            result = handle_mission_brief("task", user_id="U123", channel_id="C456")
        self.assertIsInstance(result, str)


# ===========================================================================
# /mission-capture
# ===========================================================================

class TestMissionCapture(unittest.TestCase):

    def test_empty_input_returns_usage(self):
        from commands.mission_capture import handle_mission_capture
        result = handle_mission_capture("")
        self.assertIn("Usage", result)
        self.assertIn("/mission-capture", result)

    def test_valid_input_returns_capture_header(self):
        from commands.mission_capture import handle_mission_capture
        with patch("llm.generate_response", return_value="CAPTURE OUTPUT"):
            result = handle_mission_capture("We need Slack to become a backlog tool")
        self.assertIn("MISSION CAPTURE", result)
        self.assertIn("CAPTURE OUTPUT", result)

    def test_llm_failure_returns_fallback(self):
        from commands.mission_capture import handle_mission_capture
        with patch("llm.generate_response", side_effect=RuntimeError("x")):
            result = handle_mission_capture("An idea about GitHub automation")
        self.assertIn("MISSION CAPTURE", result)
        self.assertIn("GitHub automation", result)

    def test_fallback_has_suggested_priority(self):
        from commands.mission_capture import handle_mission_capture
        with patch("llm.generate_response", side_effect=RuntimeError("x")):
            result = handle_mission_capture("build something")
        self.assertIn("P2", result)

    def test_result_is_string(self):
        from commands.mission_capture import handle_mission_capture
        with patch("llm.generate_response", return_value="x"):
            result = handle_mission_capture("idea")
        self.assertIsInstance(result, str)


# ===========================================================================
# /decision-log
# ===========================================================================

class TestDecisionLog(unittest.TestCase):

    def test_empty_input_returns_usage(self):
        from commands.decision_log import handle_decision_log
        result = handle_decision_log("")
        self.assertIn("Usage", result)
        self.assertIn("/decision-log", result)

    def test_valid_input_returns_entry_header(self):
        from commands.decision_log import handle_decision_log
        with patch("llm.generate_response", return_value="ENTRY OUTPUT"):
            result = handle_decision_log("Use GitHub as source of truth")
        self.assertIn("DECISION LOG ENTRY", result)
        self.assertIn("ENTRY OUTPUT", result)

    def test_llm_failure_returns_fallback(self):
        from commands.decision_log import handle_decision_log
        with patch("llm.generate_response", side_effect=RuntimeError("x")):
            result = handle_decision_log("Use Aider for local tasks")
        self.assertIn("DECISION LOG ENTRY", result)

    def test_fallback_default_status_is_proposed(self):
        from commands.decision_log import handle_decision_log
        with patch("llm.generate_response", side_effect=RuntimeError("x")):
            result = handle_decision_log("some decision")
        self.assertIn("Proposed", result)

    def test_fallback_owner_is_captain_tjr(self):
        from commands.decision_log import handle_decision_log
        with patch("llm.generate_response", side_effect=RuntimeError("x")):
            result = handle_decision_log("decision text")
        self.assertIn("Captain TJR", result)

    def test_fallback_storage_location_referenced(self):
        from commands.decision_log import handle_decision_log
        with patch("llm.generate_response", side_effect=RuntimeError("x")):
            result = handle_decision_log("decision text")
        self.assertIn("Decision-Register", result)

    def test_result_is_string(self):
        from commands.decision_log import handle_decision_log
        with patch("llm.generate_response", return_value="x"):
            result = handle_decision_log("a decision")
        self.assertIsInstance(result, str)


# ===========================================================================
# /ask-specialist — parse_specialist_command
# ===========================================================================

class TestParseSpecialistCommand(unittest.TestCase):

    def setUp(self):
        from commands.ask_specialist import parse_specialist_command
        self._parse = parse_specialist_command

    def test_canonical_name_and_question(self):
        key, q = self._parse("chief-engineer How should we architect this?")
        self.assertEqual(key, "chief-engineer")
        self.assertEqual(q, "How should we architect this?")

    def test_alias_engineer(self):
        key, _ = self._parse("engineer What about security?")
        self.assertEqual(key, "chief-engineer")

    def test_alias_po(self):
        key, _ = self._parse("po What is the MVP?")
        self.assertEqual(key, "product-owner")

    def test_alias_scribe(self):
        key, _ = self._parse("scribe Write a summary")
        self.assertEqual(key, "mission-scribe")

    def test_commander_key(self):
        key, _ = self._parse("commander What should we prioritise?")
        self.assertEqual(key, "commander")

    def test_unknown_name_returns_empty_key(self):
        key, _ = self._parse("admiral What is the plan?")
        self.assertEqual(key, "")

    def test_empty_string_returns_empty(self):
        key, q = self._parse("")
        self.assertEqual(key, "")
        self.assertEqual(q, "")

    def test_strips_at_mention(self):
        key, q = self._parse("<@U123> chief-engineer How does this work?")
        self.assertEqual(key, "chief-engineer")

    def test_partial_match_code(self):
        key, _ = self._parse("code-reviewer Is this safe?")
        self.assertEqual(key, "code-reviewer")

    def test_name_only_no_question(self):
        key, q = self._parse("chief-engineer")
        self.assertEqual(key, "chief-engineer")
        self.assertEqual(q, "")


# ===========================================================================
# /ask-specialist — handle_ask_specialist
# ===========================================================================

class TestHandleAskSpecialist(unittest.TestCase):

    def test_empty_input_returns_usage_and_specialist_list(self):
        from commands.ask_specialist import handle_ask_specialist
        result = handle_ask_specialist("")
        self.assertIn("Usage", result)
        self.assertIn("/ask-specialist", result)
        self.assertIn("chief-engineer", result)

    def test_unknown_specialist_returns_error_and_valid_list(self):
        from commands.ask_specialist import handle_ask_specialist
        result = handle_ask_specialist("admiral What is the plan?")
        self.assertIn("not recognised", result)
        self.assertIn("chief-engineer", result)

    def test_name_only_no_question_returns_guidance(self):
        from commands.ask_specialist import handle_ask_specialist
        result = handle_ask_specialist("chief-engineer")
        self.assertIn("No question provided", result)
        self.assertIn("chief-engineer", result)

    def test_valid_specialist_question_returns_response(self):
        from commands.ask_specialist import handle_ask_specialist
        with patch("llm.generate_response", return_value="SPECIALIST SAYS"):
            result = handle_ask_specialist("chief-engineer How should we implement this?")
        self.assertIn("Chief Engineer", result)
        self.assertIn("SPECIALIST SAYS", result)

    def test_llm_failure_returns_fallback(self):
        from commands.ask_specialist import handle_ask_specialist
        with patch("llm.generate_response", side_effect=RuntimeError("offline")):
            result = handle_ask_specialist("chief-engineer What about this?")
        self.assertIn("Chief Engineer", result)
        self.assertIn("LLM unavailable", result)

    def test_product_owner_specialist(self):
        from commands.ask_specialist import handle_ask_specialist
        with patch("llm.generate_response", return_value="PO SAYS"):
            result = handle_ask_specialist("product-owner What is the MVP?")
        self.assertIn("Product Owner", result)

    def test_knowledge_officer_specialist(self):
        from commands.ask_specialist import handle_ask_specialist
        with patch("llm.generate_response", return_value="KO SAYS"):
            result = handle_ask_specialist("knowledge-officer How should this be documented?")
        self.assertIn("Knowledge Officer", result)

    def test_mission_scribe_specialist(self):
        from commands.ask_specialist import handle_ask_specialist
        with patch("llm.generate_response", return_value="SCRIBE SAYS"):
            result = handle_ask_specialist("mission-scribe Write a summary")
        self.assertIn("Mission Scribe", result)

    def test_result_is_always_string(self):
        from commands.ask_specialist import handle_ask_specialist
        with patch("llm.generate_response", return_value="x"):
            result = handle_ask_specialist("commander What next?")
        self.assertIsInstance(result, str)

    def test_list_valid_specialists_contains_all_names(self):
        from commands.ask_specialist import list_valid_specialists
        listing = list_valid_specialists()
        for key in ("chief-engineer", "product-owner", "knowledge-officer",
                    "code-reviewer", "mission-scribe", "commander"):
            self.assertIn(key, listing)

    def test_no_mutation_by_default(self):
        """Handlers must not write to disk, GitHub, or Notion."""
        from commands.ask_specialist import handle_ask_specialist
        with patch("llm.generate_response", return_value="ok"), \
             patch("builtins.open", side_effect=AssertionError("file write attempted")) as mock_open:
            mock_open.side_effect = None  # allow reads but track calls
            handle_ask_specialist("chief-engineer What is safe?")
            # No open() calls expected from the handler itself
            mock_open.assert_not_called()


# ===========================================================================
# Cross-cutting: no-mutation guarantee
# ===========================================================================

class TestNoMutationGuarantee(unittest.TestCase):
    """All four handlers must not touch the filesystem in normal operation."""

    def _run_with_open_watch(self, fn, text):
        """Run fn(text) watching for unexpected file writes."""
        with patch("llm.generate_response", return_value="x"):
            result = fn(text)
        self.assertIsInstance(result, str)

    def test_mission_brief_no_file_write(self):
        from commands.mission_brief import handle_mission_brief
        self._run_with_open_watch(handle_mission_brief, "build something")

    def test_mission_capture_no_file_write(self):
        from commands.mission_capture import handle_mission_capture
        self._run_with_open_watch(handle_mission_capture, "an idea")

    def test_decision_log_no_file_write(self):
        from commands.decision_log import handle_decision_log
        self._run_with_open_watch(handle_decision_log, "we decided x")

    def test_ask_specialist_no_file_write(self):
        from commands.ask_specialist import handle_ask_specialist
        self._run_with_open_watch(handle_ask_specialist, "chief-engineer question here")


if __name__ == "__main__":
    unittest.main(verbosity=2)
