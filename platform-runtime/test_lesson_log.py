"""
Tests for /lesson-log command handler.

Coverage:
  - Empty input returns usage text
  - Mission ID extraction from free text
  - LLM output parsing
  - _not_captured helper
  - handle_lesson_log returns lesson ID on success (mocked persistence)
  - Graceful fallback when LLM unavailable
  - Graceful fallback when capture_lesson fails
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from commands.lesson_log import (
    _extract_mission_id,
    _not_captured,
    _parse_llm_output,
    _USAGE,
    handle_lesson_log,
)


class TestExtractMissionId(unittest.TestCase):
    def test_m_format(self):
        self.assertEqual(_extract_mission_id("M-20260614-123456 worked well"), "M-20260614-123456")

    def test_msn_format(self):
        self.assertEqual(_extract_mission_id("MSN-0054 failed on retry"), "MSN-0054")

    def test_uss_tjr_format(self):
        self.assertEqual(_extract_mission_id("USS-TJR-MSN-0001 lesson here"), "USS-TJR-MSN-0001")

    def test_no_id(self):
        self.assertEqual(_extract_mission_id("no mission ID here"), "")


class TestNotCaptured(unittest.TestCase):
    def test_empty(self):
        self.assertTrue(_not_captured(""))

    def test_not_captured_string(self):
        self.assertTrue(_not_captured("Not captured."))
        self.assertTrue(_not_captured("not captured"))

    def test_na(self):
        self.assertTrue(_not_captured("N/A"))

    def test_real_value(self):
        self.assertFalse(_not_captured("Pipeline was reliable under load."))


class TestParseLlmOutput(unittest.TestCase):
    def test_full_output(self):
        llm = (
            "Title: Retry Backoff Required\n"
            "Mission ID: MSN-0054\n"
            "Context: Rate limits hit under parallel load.\n"
            "Lesson: Add per-task circuit breaker with exponential backoff.\n"
            "Outcome: Reduced failures from 30% to 2%.\n"
            "Future Guidance: Always set task-level timeout, not just mission-level.\n"
        )
        fields = _parse_llm_output(llm)
        self.assertEqual(fields["title"], "Retry Backoff Required")
        self.assertEqual(fields["mission_id"], "MSN-0054")
        self.assertIn("Rate limits", fields["context"])
        self.assertIn("circuit breaker", fields["lesson"])
        self.assertIn("2%", fields["outcome"])
        self.assertIn("task-level", fields["future_guidance"])

    def test_missing_fields(self):
        llm = "Title: Minimal\nFuture Guidance: Always test in production.\n"
        fields = _parse_llm_output(llm)
        self.assertEqual(fields["title"], "Minimal")
        self.assertEqual(fields["future_guidance"], "Always test in production.")
        self.assertEqual(fields["mission_id"], "")
        self.assertEqual(fields["lesson"], "")

    def test_multiline_field(self):
        llm = "Title: Multi\nLesson: Line one.\nLine two.\nLine three.\nOutcome: Good.\n"
        fields = _parse_llm_output(llm)
        self.assertIn("Line one", fields["lesson"])
        self.assertIn("Line two", fields["lesson"])


class TestHandleLessonLog(unittest.TestCase):
    def test_empty_text_returns_usage(self):
        result = handle_lesson_log("")
        self.assertIn("Usage", result)
        self.assertIn("/lesson-log", result)

    def test_whitespace_only_returns_usage(self):
        result = handle_lesson_log("   ")
        self.assertIn("Usage", result)

    @patch("core.knowledge.lesson_capture.capture_lesson")
    @patch("llm.generate_response")
    def test_success_returns_lesson_id(self, mock_llm, mock_capture):
        mock_llm.return_value = (
            "Title: Test Lesson\n"
            "Mission ID: MSN-0001\n"
            "Context: Test context.\n"
            "Lesson: Always verify.\n"
            "Outcome: Success.\n"
            "Future Guidance: Check twice.\n"
        )
        mock_result = MagicMock()
        mock_result.lesson_id = "LL-042"
        mock_result.title = "Test Lesson"
        mock_result.markdown_appended = True
        mock_result.supabase_upserted = True
        mock_result.knowledge_record_written = True
        mock_result.errors = []
        mock_capture.return_value = mock_result

        result = handle_lesson_log("MSN-0001 lesson: always verify", "U001", "C001")
        self.assertIn("LL-042", result)
        self.assertIn("Lesson Captured", result)

    @patch("llm.generate_response", side_effect=Exception("LLM down"))
    @patch("core.knowledge.lesson_capture.capture_lesson")
    def test_llm_failure_falls_back(self, mock_capture, _mock_llm):
        mock_result = MagicMock()
        mock_result.lesson_id = "LL-043"
        mock_result.title = "Fallback Lesson"
        mock_result.markdown_appended = True
        mock_result.supabase_upserted = False
        mock_result.knowledge_record_written = False
        mock_result.errors = []
        mock_capture.return_value = mock_result

        result = handle_lesson_log("pipeline failed at load test", "U001", "C001")
        self.assertIn("LL-043", result)

    @patch("llm.generate_response")
    @patch("core.knowledge.lesson_capture.capture_lesson", side_effect=Exception("DB down"))
    def test_capture_failure_returns_error(self, _mock_capture, mock_llm):
        mock_llm.return_value = (
            "Title: Failing Test\nMission ID: Not captured.\n"
            "Lesson: Test.\nFuture Guidance: Fix DB.\n"
        )
        result = handle_lesson_log("some lesson text", "U001", "C001")
        self.assertIn("Partial Failure", result)
        self.assertIn("Exception", result)  # type name shown; message is in logs


if __name__ == "__main__":
    unittest.main()
