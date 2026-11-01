"""USS-TJR-MSN-0412 Stream 6: local Ollama calls that bypass the model router must still be logged
(core/llm/call_log.py), in the router's call_log shape, without prompt text, and without
distorting the router's own health numbers. Ollama is faked; nothing touches the real log.
"""
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "core" / "model-router"))
sys.path.insert(0, str(REPO_ROOT / "platform-runtime"))
sys.path.insert(0, str(REPO_ROOT))

import app
import llm

from core.llm import call_log, provider_chain

PROMPT_MARKER = "marker text that must not be logged"


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _urlopen_returning(payload):
    return lambda req, timeout=None: _Resp(json.dumps(payload).encode())


class DirectLogTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log_path = Path(self.tmp.name) / "call_log.jsonl"
        patcher = patch.dict(os.environ, {"LLM_DIRECT_CALL_LOG": str(self.log_path)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        llm._direct_call_logger = None

    def entries(self):
        if not self.log_path.exists():
            return []
        return [json.loads(line) for line in self.log_path.read_text().splitlines()]


class CallLogHelperTest(DirectLogTestBase):
    def test_writes_router_shaped_line_without_prompt_text(self):
        call_log.log_direct_call(model="gemma3:4b", duration_ms=1234, success=True,
                                 prompt_len=40, response_len=12, prompt_eval_count=9, eval_count=3)
        (e,) = self.entries()
        for key in ("ts", "task_type", "model", "duration_ms", "success", "prompt_len",
                    "response_len", "token_info", "escalated", "route_tier"):
            self.assertIn(key, e)
        self.assertEqual(e["source"], "direct")
        self.assertTrue(e["caller"])
        self.assertEqual(e["token_info"], {"prompt_eval_count": 9, "eval_count": 3})

    def test_never_raises_when_log_unwritable(self):
        with patch.dict(os.environ, {"LLM_DIRECT_CALL_LOG": "/proc/nope/call_log.jsonl"}):
            call_log.log_direct_call(model="m", duration_ms=1, success=False, prompt_len=1)


class ProviderChainOllamaTest(DirectLogTestBase):
    def test_success_is_logged(self):
        payload = {"response": " hi ", "prompt_eval_count": 7, "eval_count": 2}
        with patch("urllib.request.urlopen", _urlopen_returning(payload)):
            provider_chain.call_ollama("sys", PROMPT_MARKER, base_url="http://x", model="gemma3:4b")
        (e,) = self.entries()
        self.assertTrue(e["success"])
        self.assertEqual(e["model"], "gemma3:4b")
        self.assertEqual(e["prompt_len"], len("sys") + len(PROMPT_MARKER))
        self.assertEqual(e["token_info"]["prompt_eval_count"], 7)
        self.assertNotIn(PROMPT_MARKER, self.log_path.read_text())

    def test_failure_is_logged_and_still_raises(self):
        def boom(req, timeout=None):
            raise TimeoutError("slow")
        with patch("urllib.request.urlopen", boom), self.assertRaises(TimeoutError):
            provider_chain.call_ollama("s", "p", base_url="http://x", model="m")
        (e,) = self.entries()
        self.assertFalse(e["success"])
        self.assertEqual(e["error"], "TimeoutError")

    def test_empty_response_is_logged_as_failure_and_raises(self):
        with patch("urllib.request.urlopen", _urlopen_returning({"response": "  "})), \
                self.assertRaises(RuntimeError):
            provider_chain.call_ollama("s", "p", base_url="http://x", model="m")
        (e,) = self.entries()
        self.assertFalse(e["success"])

    def test_log_failure_does_not_break_the_call(self):
        with patch.dict(os.environ, {"LLM_DIRECT_CALL_LOG": "/proc/nope/call_log.jsonl"}), \
                patch("urllib.request.urlopen", _urlopen_returning({"response": "ok"})):
            result = provider_chain.call_ollama("s", "p", base_url="http://x", model="m")
        self.assertEqual(result.text, "ok")


class PlatformRuntimeLlmTest(DirectLogTestBase):
    def test_success_is_logged(self):
        payload = {"message": {"content": "hello"}, "prompt_eval_count": 5, "eval_count": 1}
        with patch("urllib.request.urlopen", _urlopen_returning(payload)):
            out = llm.generate_with_ollama(PROMPT_MARKER, system_prompt="sys", model="gemma3:4b")
        self.assertEqual(out, "hello")
        (e,) = self.entries()
        self.assertTrue(e["success"])
        self.assertEqual(e["prompt_len"], len("sys") + len(PROMPT_MARKER))
        self.assertEqual(e["response_len"], 5)
        self.assertNotIn(PROMPT_MARKER, self.log_path.read_text())

    def test_failure_is_logged_and_wrapped(self):
        def boom(req, timeout=None):
            raise OSError("down")
        with patch("urllib.request.urlopen", boom), self.assertRaises(llm.LLMUnavailableError):
            llm.generate_with_ollama("p", model="m")
        (e,) = self.entries()
        self.assertFalse(e["success"])
        self.assertEqual(e["error"], "OSError")

    def test_log_failure_does_not_break_the_call(self):
        with patch.dict(os.environ, {"LLM_DIRECT_CALL_LOG": "/proc/nope/call_log.jsonl"}), \
                patch("urllib.request.urlopen", _urlopen_returning({"message": {"content": "ok"}})):
            self.assertEqual(llm.generate_with_ollama("p", model="m"), "ok")


class RouterHealthIgnoresDirectTest(unittest.TestCase):
    def test_direct_entries_are_listed_but_excluded_from_health(self):
        with tempfile.TemporaryDirectory() as d:
            log_file = Path(d) / "call_log.jsonl"
            lines = [
                {"success": True, "duration_ms": 100},
                {"success": True, "duration_ms": 300},
                {"success": False, "duration_ms": 9, "source": "direct"},
                {"success": True, "duration_ms": 999999, "source": "direct"},
            ]
            log_file.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
            with patch.object(app, "_LOG_FILE", log_file):
                everything = app._recent_calls(5)
                router_only = app._recent_calls(5, include_direct=False)
        self.assertEqual(len(everything), 4)
        self.assertEqual([c["duration_ms"] for c in router_only], [300, 100])
        self.assertTrue(all(c.get("source") != "direct" for c in router_only))


if __name__ == "__main__":
    unittest.main()
