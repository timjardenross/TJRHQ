"""
Tests for the 2026-09-26 Gemini thinking-level fix in core/model-router/app.py.

Real incident this fixes: every Gemini-routed task_type left
`generationConfig` unset in the request body, so `gemini-flash-latest`
(currently resolving to Gemini 3.8 Flash) applied its default
`thinking_level: "medium"` to every call. Confirmed live via
call_log.jsonl: hq-evolution-external-fit calls with ~1400 prompt tokens
and ~80 output tokens were taking 220-300s each — only explained by large
amounts of invisible thinking-token generation the router never asked
for or logged (usageMetadata.thoughtsTokenCount was never even read).

Same dotted-path import convention as tests/test_model_router_route_contract.py.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL_ROUTER_DIR = REPO_ROOT / "core" / "model-router"
sys.path.insert(0, str(MODEL_ROUTER_DIR))

import app


class TestGeminiGenerateThinkingConfig(unittest.TestCase):
    def test_no_thinking_level_omits_generation_config_entirely(self):
        """Preserves exact prior request shape for any caller that doesn't
        pass thinking_level — no behaviour change unless a task_type
        explicitly opts in."""
        captured = {}

        class _FakeResponse:
            def read(self):
                return b'{"candidates": [], "usageMetadata": {}}'
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            import json
            captured["body"] = json.loads(req.data.decode())
            return _FakeResponse()

        with patch("app.urllib.request.urlopen", side_effect=fake_urlopen), \
             patch.dict("os.environ", {"GEMINI_API_KEY": "test-key-not-real"}):  # pragma: allowlist secret
            app._gemini_generate("gemini-flash-latest", "prompt", 60)
        self.assertNotIn("generationConfig", captured["body"])

    def test_thinking_level_low_is_included_in_request_body(self):
        captured = {}

        class _FakeResponse:
            def read(self):
                return b'{"candidates": [], "usageMetadata": {}}'
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            import json
            captured["body"] = json.loads(req.data.decode())
            return _FakeResponse()

        with patch("app.urllib.request.urlopen", side_effect=fake_urlopen), \
             patch.dict("os.environ", {"GEMINI_API_KEY": "test-key-not-real"}):  # pragma: allowlist secret
            app._gemini_generate("gemini-flash-latest", "prompt", 60, thinking_level="low")
        self.assertEqual(captured["body"]["generationConfig"], {"thinkingConfig": {"thinking_level": "low"}})


class TestEveryGeminiTaskTypeSetsThinkingLevel(unittest.TestCase):
    def test_all_gemini_routed_task_types_have_thinking_level_low(self):
        """Regression test for the fix itself: every Gemini-routed
        task_type must set thinking_level, not just some of them — a
        partial fix would leave the same 200-300s latency on whichever
        task_types were missed."""
        gemini_tasks = {name: policy for name, policy in app.TASK_POLICY.items() if policy.get("provider") == "gemini"}
        self.assertTrue(gemini_tasks, "no Gemini-routed task_types found — did TASK_POLICY change shape?")
        missing = {name for name, policy in gemini_tasks.items() if not policy.get("thinking_level")}
        self.assertEqual(missing, set(), f"Gemini task_type(s) with no thinking_level set: {missing}")

    def test_run_task_passes_policy_thinking_level_to_gemini_generate(self):
        with patch("app._gemini_generate", return_value={"candidates": [{"content": {"parts": [{"text": "ok"}]}}], "usageMetadata": {}}) as mocked, \
             patch("app.check_output_rail", return_value=None), \
             patch("app.secure_outbound_prompt", return_value=("prompt", None)):
            app._run_task("hq-evolution-external-fit", "prompt", {})
        mocked.assert_called_once()
        self.assertEqual(mocked.call_args.args[4], "low")


class TestThoughtsTokenCountLogged(unittest.TestCase):
    def test_thoughts_token_count_captured_in_token_info(self):
        fake_response = {
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
            "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 10, "thoughtsTokenCount": 500},
        }
        with patch("app._gemini_generate", return_value=fake_response), \
             patch("app.check_output_rail", return_value=None), \
             patch("app.secure_outbound_prompt", return_value=("prompt", None)), \
             patch("app._log_call") as mocked_log:
            app._run_task("hq-evolution-external-fit", "prompt", {})
        logged_entry = mocked_log.call_args.args[0]
        self.assertEqual(logged_entry["token_info"]["thoughts_token_count"], 500)


if __name__ == "__main__":
    unittest.main()
