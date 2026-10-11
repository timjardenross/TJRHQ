"""The LLM-backed guardrail rails are recorded in the direct call log (lengths only, never text)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.security import llm_guardrails as g

PROMPT_SENTINEL = "PROMPT-SENTINEL-MUST-NOT-APPEAR-IN-LOG"


class GuardrailCallLogTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        self.addCleanup(os.unlink, self.path)
        env = patch.dict(os.environ, {"LLM_DIRECT_CALL_LOG": self.path})
        env.start()
        self.addCleanup(env.stop)

    def rows(self):
        return [json.loads(line) for line in Path(self.path).read_text().splitlines()]

    def test_input_rail_is_logged_with_lengths_only(self):
        with patch.object(g, "_invoke_worker_inner", return_value={"blocked": False}):
            g.check_input_rail(PROMPT_SENTINEL)
        (row,) = self.rows()
        self.assertEqual(row["task_type"], "guardrail-check-input")
        self.assertEqual(row["source"], "direct")
        self.assertEqual(row["prompt_len"], len(PROMPT_SENTINEL))
        self.assertTrue(row["success"])
        self.assertEqual(row["model"], g._rail_model())
        self.assertNotIn(PROMPT_SENTINEL, json.dumps(row))

    def test_output_rail_is_logged(self):
        with patch.object(g, "_invoke_worker_inner", return_value={"blocked": False}):
            g.check_output_rail(PROMPT_SENTINEL)
        (row,) = self.rows()
        self.assertEqual(row["task_type"], "guardrail-check-output")
        self.assertEqual(row["prompt_len"], len(PROMPT_SENTINEL))

    def test_failure_is_logged_and_still_raised(self):
        with patch.object(g, "_invoke_worker_inner", side_effect=g.GuardrailsUnavailableError("down")), \
             patch.object(g, "_FAIL_OPEN", False), \
             self.assertRaises(g.GuardrailsUnavailableError):
            g.check_input_rail("x")
        (row,) = self.rows()
        self.assertFalse(row["success"])
        self.assertEqual(row["error"], "GuardrailsUnavailableError")

    def test_redact_is_not_logged(self):
        with patch.object(g, "_invoke_worker_inner", return_value={"redacted_text": "t", "findings": []}):
            g.redact_pii("text")
        self.assertEqual(self.rows(), [])

    def test_logging_failure_never_breaks_the_rail(self):
        with patch.object(g, "_invoke_worker_inner", return_value={"blocked": False}), \
             patch.dict(os.environ, {"LLM_DIRECT_CALL_LOG": "/nonexistent-dir/x.jsonl"}):
            g.check_input_rail("x")


if __name__ == "__main__":
    unittest.main()
