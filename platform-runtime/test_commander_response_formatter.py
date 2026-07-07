"""Tests for MSN-0011B — commander_response_formatter.py.

Covers:
  - classify_response_type() — keyword-based type detection and priority
  - parse_commander_response() — header stripping, error detection, type classification
  - format_commander_response() — mrkdwn output structure, field omission, safe defaults
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

from commander_response_formatter import (
    _DEFAULT_TYPE,
    _INTAKE_HEADER,
    RESPONSE_TYPES,
    classify_response_type,
    format_commander_response,
    parse_commander_response,
)


# ===========================================================================
# classify_response_type
# ===========================================================================

class TestClassifyResponseType(unittest.TestCase):
    """Keyword-based type detection; first match in priority order wins."""

    def test_recommendation_keyword_recommend(self):
        self.assertEqual(classify_response_type("I recommend proceeding with option B."), "RECOMMENDATION")

    def test_recommendation_keyword_suggest(self):
        self.assertEqual(classify_response_type("I suggest we defer this mission."), "RECOMMENDATION")

    def test_decision_keyword_decided(self):
        self.assertEqual(classify_response_type("We have decided to proceed."), "DECISION")

    def test_decision_keyword_approved(self):
        self.assertEqual(classify_response_type("This approach has been approved."), "DECISION")

    def test_task_keyword_implement(self):
        self.assertEqual(classify_response_type("Next step: implement the auth layer."), "TASK")

    def test_task_keyword_action_item(self):
        self.assertEqual(classify_response_type("Action item: review the PR by Friday."), "TASK")

    def test_escalation_keyword_urgent(self):
        self.assertEqual(classify_response_type("This is urgent — contact the team immediately."), "ESCALATION")

    def test_escalation_wins_over_recommendation(self):
        # ESCALATION has higher priority than RECOMMENDATION
        text = "I recommend escalating this critical priority issue."
        self.assertEqual(classify_response_type(text), "ESCALATION")

    def test_question_keyword_clarify(self):
        self.assertEqual(classify_response_type("Please clarify the scope before proceeding."), "QUESTION")

    def test_closeout_keyword_complete(self):
        self.assertEqual(classify_response_type("This mission is now complete."), "CLOSEOUT")

    def test_default_info_no_keywords(self):
        self.assertEqual(classify_response_type("Here is a summary of current status."), "INFO")

    def test_empty_string_defaults_to_info(self):
        self.assertEqual(classify_response_type(""), "INFO")

    def test_case_insensitive(self):
        self.assertEqual(classify_response_type("RECOMMEND proceeding with caution."), "RECOMMENDATION")

    def test_returns_valid_type(self):
        for text in (
            "recommend",
            "decided",
            "implement",
            "escalat",
            "clarify",
            "complete",
            "no keywords here at all",
        ):
            self.assertIn(classify_response_type(text), RESPONSE_TYPES)


# ===========================================================================
# parse_commander_response
# ===========================================================================

class TestParseCommanderResponse(unittest.TestCase):
    """Parsing: header stripping, error detection, type classification."""

    def test_strips_slack_header(self):
        raw = f"{_INTAKE_HEADER}\n\nI recommend we proceed with option A."
        result = parse_commander_response(raw)
        self.assertNotIn(_INTAKE_HEADER, result["body"])
        self.assertIn("option A", result["body"])

    def test_no_header_passthrough(self):
        raw = "This is a summary of the situation."
        result = parse_commander_response(raw)
        self.assertEqual(result["body"], raw)

    def test_empty_raw_returns_error_type(self):
        result = parse_commander_response("")
        self.assertEqual(result["type"], "ERROR")

    def test_none_like_empty_returns_error(self):
        result = parse_commander_response("   ")
        self.assertEqual(result["type"], "ERROR")

    def test_warning_emoji_detected_as_error(self):
        raw = f"{_INTAKE_HEADER}\n\n:warning: Commander is temporarily unavailable."
        result = parse_commander_response(raw)
        self.assertEqual(result["type"], "ERROR")

    def test_x_emoji_detected_as_error(self):
        raw = f"{_INTAKE_HEADER}\n\n:x: Commander runtime exited with code 1."
        result = parse_commander_response(raw)
        self.assertEqual(result["type"], "ERROR")

    def test_hourglass_emoji_detected_as_error(self):
        raw = f"{_INTAKE_HEADER}\n\n:hourglass: Commander synthesis timed out."
        result = parse_commander_response(raw)
        self.assertEqual(result["type"], "ERROR")

    def test_type_classified_from_body(self):
        raw = f"{_INTAKE_HEADER}\n\nI recommend proceeding with option B."
        result = parse_commander_response(raw)
        self.assertEqual(result["type"], "RECOMMENDATION")

    def test_metadata_source_is_commander(self):
        result = parse_commander_response("Some synthesis text.")
        self.assertEqual(result["metadata"]["source"], "Commander")

    def test_lifecycle_state_is_none_by_default(self):
        result = parse_commander_response("Some synthesis text.")
        self.assertIsNone(result["lifecycle_state"])

    def test_confidence_is_none_by_default(self):
        result = parse_commander_response("Some synthesis text.")
        self.assertIsNone(result["confidence"])

    def test_result_has_required_keys(self):
        result = parse_commander_response("Any text.")
        for key in ("type", "body", "lifecycle_state", "confidence", "metadata"):
            self.assertIn(key, result)

    def test_type_is_always_valid(self):
        for raw in ("", "recommend", f"{_INTAKE_HEADER}\n\n:x: error", "no keywords"):
            result = parse_commander_response(raw)
            self.assertIn(result["type"], RESPONSE_TYPES,
                          f"Invalid type {result['type']!r} for input {raw!r}")


# ===========================================================================
# format_commander_response
# ===========================================================================

class TestFormatCommanderResponse(unittest.TestCase):
    """Slack mrkdwn output: structure, field omission, safe defaults."""

    def _basic(self, **overrides) -> dict:
        base = {
            "type": "RECOMMENDATION",
            "body": "Proceed with option B.",
            "lifecycle_state": "DECISION",
            "confidence": "High",
            "metadata": {"source": "Commander"},
        }
        base.update(overrides)
        return base

    def test_header_contains_response_type(self):
        result = format_commander_response(self._basic(type="RECOMMENDATION"))
        self.assertTrue(result.startswith("*Commander Response — RECOMMENDATION*"))

    def test_body_present_in_output(self):
        result = format_commander_response(self._basic(body="My synthesis body."))
        self.assertIn("My synthesis body.", result)

    def test_metadata_section_present(self):
        result = format_commander_response(self._basic())
        self.assertIn("_Metadata_", result)
        self.assertIn("• Source: Commander", result)

    def test_lifecycle_state_included_when_set(self):
        result = format_commander_response(self._basic(lifecycle_state="DECISION"))
        self.assertIn("• Lifecycle State: DECISION", result)

    def test_lifecycle_state_omitted_when_none(self):
        result = format_commander_response(self._basic(lifecycle_state=None))
        self.assertNotIn("Lifecycle State", result)

    def test_confidence_included_when_set(self):
        result = format_commander_response(self._basic(confidence="Medium"))
        self.assertIn("• Confidence: Medium", result)

    def test_confidence_omitted_when_none(self):
        result = format_commander_response(self._basic(confidence=None))
        self.assertNotIn("Confidence", result)

    def test_missing_body_uses_placeholder(self):
        result = format_commander_response({"type": "INFO"})
        self.assertIn("Commander returned no response body", result)

    def test_unknown_type_defaults_to_info(self):
        result = format_commander_response({"type": "BOGUSTYPE", "body": "text"})
        self.assertIn("*Commander Response — INFO*", result)

    def test_none_type_defaults_to_info(self):
        result = format_commander_response({"type": None, "body": "text"})
        self.assertIn("*Commander Response — INFO*", result)

    def test_all_response_types_format_correctly(self):
        for rtype in RESPONSE_TYPES:
            result = format_commander_response({"type": rtype, "body": "body text"})
            self.assertIn(f"*Commander Response — {rtype}*", result,
                          f"Header missing for type {rtype}")

    def test_custom_source_in_metadata(self):
        result = format_commander_response(
            self._basic(metadata={"source": "Specialist Runtime"})
        )
        self.assertIn("• Source: Specialist Runtime", result)

    def test_empty_metadata_uses_default_source(self):
        result = format_commander_response({"type": "INFO", "body": "x", "metadata": {}})
        self.assertIn("• Source: Commander", result)

    def test_missing_metadata_key_uses_default_source(self):
        result = format_commander_response({"type": "INFO", "body": "x"})
        self.assertIn("• Source: Commander", result)

    def test_result_is_string(self):
        self.assertIsInstance(format_commander_response(self._basic()), str)


# ===========================================================================
# Round-trip: parse then format
# ===========================================================================

class TestRoundTrip(unittest.TestCase):
    """parse_commander_response → format_commander_response produces valid Slack output."""

    def _round_trip(self, raw: str) -> str:
        return format_commander_response(parse_commander_response(raw))

    def test_recommendation_round_trip(self):
        raw = f"{_INTAKE_HEADER}\n\nI recommend proceeding with option A."
        result = self._round_trip(raw)
        self.assertIn("*Commander Response — RECOMMENDATION*", result)
        self.assertIn("option A", result)
        self.assertNotIn(_INTAKE_HEADER, result)

    def test_error_fallback_round_trip(self):
        raw = f"{_INTAKE_HEADER}\n\n:warning: Commander is temporarily unavailable.\nReason: script not found"
        result = self._round_trip(raw)
        self.assertIn("*Commander Response — ERROR*", result)
        self.assertIn("unavailable", result)

    def test_plain_synthesis_round_trip(self):
        raw = "Current status: all systems nominal."
        result = self._round_trip(raw)
        self.assertIn("*Commander Response — INFO*", result)
        self.assertIn("all systems nominal", result)

    def test_empty_raw_round_trip(self):
        result = self._round_trip("")
        self.assertIn("*Commander Response — ERROR*", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
