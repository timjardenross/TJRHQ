"""USS-TJR-MSN-0412 Stream 5: glm-*:cloud (Ollama Cloud) leaves the host, so the router must
guard it like the Gemini branch: redact before sending, check the reply, fail closed.
Local models stay unguarded. The guard and the Ollama call are faked; no network, no worker.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "core" / "model-router"))
sys.path.insert(0, str(REPO_ROOT))

import app

from core.security.llm_guardrails import (
    BlockedByGuardrailsError,
    GuardrailsUnavailableError,
)

RAW = "Review the note from Jane Citizen."
SAFE = "Review the note from <PERSON>."


def _ollama_ok(model, prompt, keep_alive, timeout, num_predict=None):
    return {"response": " fine ", "prompt_eval_count": 1, "eval_count": 1}


class CloudModelGuardTest(unittest.TestCase):
    def test_is_cloud_model(self):
        self.assertTrue(app._is_cloud_model("glm-5.3:cloud"))
        self.assertTrue(app._is_cloud_model("glm-5.2:cloud"))
        self.assertFalse(app._is_cloud_model("gemma3:4b"))
        self.assertFalse(app._is_cloud_model("mistral-small3.2:24b"))

    def _run_escalate(self, secure, out_rail, gen):
        with patch("app._available_model_names", return_value={app.MODEL_CLOUD, app.MODEL_CLOUD_ALT}), \
             patch("app._resolve_cloud_escalation",
                   side_effect=lambda t, p: ({**p, "model": app.MODEL_CLOUD}, "cloud_primary", "")), \
             patch("app.secure_outbound_prompt", secure), \
             patch("app.check_output_rail", out_rail), \
             patch("app._ollama_generate", gen):
            return app._run_task("escalate", RAW, {})

    def test_cloud_route_sends_only_redacted_text_and_checks_reply(self):
        sent, replies = [], []

        def gen(model, prompt, *a, **k):
            sent.append(prompt)
            return _ollama_ok(model, prompt, *a, **k)

        result = self._run_escalate(lambda p: (SAFE, None), replies.append, gen)
        self.assertTrue(result["success"], result)
        self.assertEqual(sent, [SAFE])
        self.assertEqual(replies, ["fine"])

    def test_unavailable_guard_sends_nothing(self):
        sent = []

        def boom(_p):
            raise GuardrailsUnavailableError("llmsec venv not found")

        result = self._run_escalate(boom, lambda t: None, lambda *a, **k: sent.append(a) or _ollama_ok(*a))
        self.assertFalse(result["success"])
        self.assertEqual(sent, [])

    def test_blocked_prompt_sends_nothing(self):
        sent = []

        def block(_p):
            raise BlockedByGuardrailsError("input blocked")

        result = self._run_escalate(block, lambda t: None, lambda *a, **k: sent.append(a) or _ollama_ok(*a))
        self.assertFalse(result["success"])
        self.assertEqual(sent, [])

    def test_blocked_reply_is_not_returned(self):
        def block(_t):
            raise BlockedByGuardrailsError("output blocked")

        result = self._run_escalate(lambda p: (SAFE, None), block, _ollama_ok)
        self.assertFalse(result["success"])
        self.assertNotIn("response", result)

    def test_local_model_is_not_guarded(self):
        sent = []

        def gen(model, prompt, *a, **k):
            sent.append(prompt)
            return _ollama_ok(model, prompt, *a, **k)

        def must_not_run(*_a, **_k):
            raise AssertionError("guard must not run for a local model")

        with patch("app.secure_outbound_prompt", must_not_run), \
             patch("app.check_output_rail", must_not_run), \
             patch("app._ollama_generate", gen):
            result = app._run_task("classify-capture", RAW, {"skip_escalation": True})
        self.assertTrue(result["success"], result)
        self.assertEqual(sent, [RAW])


if __name__ == "__main__":
    unittest.main()
