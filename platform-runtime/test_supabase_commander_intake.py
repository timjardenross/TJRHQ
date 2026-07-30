"""Tests for MSN-0011A — supabase_commander_intake.py.

Covers:
  - is_commander_directed() trigger detection
  - _extract_synthesis() trailer stripping
  - run_supabase_commander() subprocess behaviour (mocked)
  - classify_commander_intent() INTENT_COMMANDER routing in commander_bridge
  - handle_slack_message() INTENT_COMMANDER end-to-end (mocked subprocess)

All tests are pure unit tests. No live Ollama or Supabase connection required.
"""

from __future__ import annotations

import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Ensure slack-bot/ modules are importable
# ---------------------------------------------------------------------------
_BOT_DIR = Path(__file__).resolve().parent
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

import supabase_commander_intake as _sci
from supabase_commander_intake import (
    _SLACK_HEADER,
    _extract_synthesis,
    is_commander_directed,
    run_supabase_commander,
)


# ---------------------------------------------------------------------------
# Shared stub builders for commander_bridge integration tests
# ---------------------------------------------------------------------------

def _make_stubs(run_commander_fn=None):
    """Return a dict of stub modules for commander_bridge imports."""
    fake_client = types.ModuleType("client")
    fake_client.SupabaseWriteResult = MagicMock
    fake_client.fetch_recent_context = lambda limit=3: {}
    fake_client.log_commander_event = lambda p: MagicMock(ok=True, enabled=True)
    fake_client.log_decision = lambda p: MagicMock(ok=False, enabled=False)
    fake_client.log_memory_event = lambda p: MagicMock(ok=False, enabled=False)
    fake_client.log_mission_candidate = lambda p: MagicMock(ok=False, enabled=False)
    fake_client.now_iso = lambda: "2026-06-06T00:00:00Z"

    fake_router = types.ModuleType("router")
    fake_router.route_request = lambda t: {
        "mission_domain": "Engineering",
        "assigned_specialists": ["Chief Engineer"],
        "priority": "P2",
        "status": "Active",
    }
    fake_router.score_specialists = lambda t: []

    fake_runtime = types.ModuleType("commander_runtime")
    fake_runtime.execute_commander_runtime = lambda **kw: "local runtime response"

    fake_intake = types.ModuleType("supabase_commander_intake")
    fake_intake.is_commander_directed = is_commander_directed  # real impl
    fake_intake.run_supabase_commander = (
        run_commander_fn or (lambda q, **kw: f"DI synthesis: {q}")
    )

    return {
        "client": fake_client,
        "router": fake_router,
        "commander_runtime": fake_runtime,
        "supabase_commander_intake": fake_intake,
    }


# ===========================================================================
# is_commander_directed
# ===========================================================================

class TestIsCommanderDirected(unittest.TestCase):
    """Trigger detection: only 'commander:' prefix (case-insensitive) returns True."""

    def test_lowercase_prefix(self):
        self.assertTrue(is_commander_directed("commander: should we build X?"))

    def test_titlecase_prefix(self):
        self.assertTrue(is_commander_directed("Commander: what is the bottleneck?"))

    def test_uppercase_prefix(self):
        self.assertTrue(is_commander_directed("COMMANDER: go"))

    def test_no_space_before_colon(self):
        self.assertTrue(is_commander_directed("commander:go"))

    def test_leading_whitespace(self):
        self.assertTrue(is_commander_directed("  commander: something"))

    def test_general_text_is_false(self):
        self.assertFalse(is_commander_directed("what is the bottleneck?"))

    def test_decision_prefix_is_false(self):
        self.assertFalse(is_commander_directed("decision: we choose X"))

    def test_remember_prefix_is_false(self):
        self.assertFalse(is_commander_directed("remember: use supabase for logging"))

    def test_mid_sentence_commander_is_false(self):
        # Only prefix match counts — mid-sentence does NOT trigger
        self.assertFalse(is_commander_directed("ask the commander: about X"))

    def test_empty_string_is_false(self):
        self.assertFalse(is_commander_directed(""))


# ===========================================================================
# _extract_synthesis
# ===========================================================================

class TestExtractSynthesis(unittest.TestCase):
    """Trailer stripping: metadata lines after the synthesis are removed."""

    def test_strips_collaboration_log(self):
        stdout = "Commander says X\nCollaboration log: /path/to/log"
        self.assertEqual(_extract_synthesis(stdout), "Commander says X")

    def test_strips_decision_register(self):
        stdout = "Synthesis here\nDecision register: /some/path\nRuntime latency: 500ms"
        self.assertEqual(_extract_synthesis(stdout), "Synthesis here")

    def test_strips_runtime_latency(self):
        stdout = "Body text\nRuntime latency: 1234.56ms"
        self.assertEqual(_extract_synthesis(stdout), "Body text")

    def test_strips_paperclip_log_lines(self):
        stdout = "Synthesis\n[paperclip] Issue created: STA-5"
        self.assertEqual(_extract_synthesis(stdout), "Synthesis")

    def test_strips_warning_lines(self):
        stdout = "Good output\nWarning: Notion sync skipped"
        self.assertEqual(_extract_synthesis(stdout), "Good output")

    def test_multi_line_synthesis_preserved(self):
        stdout = "# Commander Synthesis\n\nLine 1\nLine 2\nCollaboration log: /x"
        result = _extract_synthesis(stdout)
        self.assertIn("# Commander Synthesis", result)
        self.assertIn("Line 2", result)
        self.assertNotIn("Collaboration log", result)

    def test_empty_stdout_returns_message(self):
        result = _extract_synthesis("")
        self.assertIn("empty", result)

    def test_no_trailers_returns_full_content(self):
        stdout = "Just synthesis\nAnd more synthesis"
        self.assertEqual(_extract_synthesis(stdout), "Just synthesis\nAnd more synthesis")


# ===========================================================================
# run_supabase_commander (subprocess mocked via patch.object)
# ===========================================================================

class TestRunSupabaseCommander(unittest.TestCase):
    """Subprocess wrapper: behaviour on success, missing script, timeout, error."""

    def _make_result(
        self,
        stdout: str = "Commander synthesis",
        returncode: int = 0,
        stderr: str = "",
    ) -> MagicMock:
        r = MagicMock()
        r.stdout = stdout
        r.returncode = returncode
        r.stderr = stderr
        return r

    def _mock_script(self, exists: bool = True) -> MagicMock:
        """Return a MagicMock Path-like for _RUNTIME_SCRIPT."""
        m = MagicMock(spec=Path)
        m.exists.return_value = exists
        return m

    def test_happy_path_returns_synthesis(self):
        mock_script = self._mock_script(True)
        with patch.object(_sci, "_RUNTIME_SCRIPT", mock_script), \
             patch("subprocess.run", return_value=self._make_result(
                 "# Synthesis\n\nRecommend X\nCollaboration log: /x"
             )):
            result = run_supabase_commander("what is the priority?")
        self.assertIn(_SLACK_HEADER, result)
        self.assertIn("Recommend X", result)
        self.assertNotIn("Collaboration log", result)

    def test_happy_path_runs_correct_script(self):
        mock_script = self._mock_script(True)
        with patch.object(_sci, "_RUNTIME_SCRIPT", mock_script), \
             patch("subprocess.run", return_value=self._make_result()) as mock_run:
            run_supabase_commander("test question")
        args, kwargs = mock_run.call_args
        cmd = args[0]
        self.assertEqual(cmd[0], sys.executable)
        self.assertEqual(cmd[-1], "test question")

    def test_script_missing_returns_unavailable(self):
        mock_script = self._mock_script(False)  # exists() → False
        with patch.object(_sci, "_RUNTIME_SCRIPT", mock_script):
            result = run_supabase_commander("some question")
        self.assertIn("unavailable", result.lower())
        self.assertIn("Runtime script not found", result)

    def test_timeout_returns_timeout_message(self):
        mock_script = self._mock_script(True)
        with patch.object(_sci, "_RUNTIME_SCRIPT", mock_script), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=120)):
            result = run_supabase_commander("slow question", timeout_s=120)
        self.assertIn("timed out", result.lower())
        self.assertIn("120", result)
        self.assertIn(_SLACK_HEADER, result)

    def test_nonzero_exit_returns_error_message(self):
        mock_script = self._mock_script(True)
        with patch.object(_sci, "_RUNTIME_SCRIPT", mock_script), \
             patch("subprocess.run", return_value=self._make_result(
                 "", returncode=1, stderr="ImportError: no module"
             )):
            result = run_supabase_commander("question", timeout_s=30)
        self.assertIn("exited with code", result.lower())
        self.assertIn("1", result)
        self.assertIn("ImportError", result)

    def test_subprocess_oserror_returns_unavailable(self):
        mock_script = self._mock_script(True)
        with patch.object(_sci, "_RUNTIME_SCRIPT", mock_script), \
             patch("subprocess.run", side_effect=OSError("No such file")):
            result = run_supabase_commander("question")
        self.assertIn("unavailable", result.lower())
        self.assertIn("OSError", result)

    def test_cwd_set_to_runtime_dir(self):
        mock_script = self._mock_script(True)
        with patch.object(_sci, "_RUNTIME_SCRIPT", mock_script), \
             patch("subprocess.run", return_value=self._make_result()) as mock_run:
            run_supabase_commander("question")
        _, kwargs = mock_run.call_args
        self.assertIn("cwd", kwargs)

    def test_empty_synthesis_handled(self):
        mock_script = self._mock_script(True)
        with patch.object(_sci, "_RUNTIME_SCRIPT", mock_script), \
             patch("subprocess.run", return_value=self._make_result("")):
            result = run_supabase_commander("q")
        self.assertIsInstance(result, str)


# ===========================================================================
# commander_bridge.py integration: classify_commander_intent
# ===========================================================================

class TestClassifyCommanderIntent(unittest.TestCase):
    """INTENT_COMMANDER is classified before all other intents."""

    _original_modules: dict

    def setUp(self):
        import importlib
        self._original_modules = {}
        stubs = _make_stubs()
        for name, mod in stubs.items():
            self._original_modules[name] = sys.modules.get(name)
            sys.modules[name] = mod

        # Also stub out specialist_registry etc. needed by router indirectly
        for dep in ("specialist_registry", "github_awareness", "mission_registry",
                    "repository_awareness", "knowledge_retrieval", "mission_executor"):
            if dep not in sys.modules:
                fake = types.ModuleType(dep)
                # Add any attribute the router calls
                fake.match_specialists_to_request = lambda t: []
                fake.is_github_awareness_request = lambda t: False
                fake.is_mission_registry_request = lambda t: False
                fake.is_repository_awareness_request = lambda t: False
                fake.is_knowledge_retrieval_request = lambda t: False
                fake.identify_knowledge_domain = lambda t: "general"
                fake.is_mission_execution_request = lambda t: False
                self._original_modules[dep] = sys.modules.get(dep)
                sys.modules[dep] = fake

        if "commander_bridge" in sys.modules:
            del sys.modules["commander_bridge"]
        import commander_bridge as _cb
        importlib.reload(_cb)
        self.cb = _cb

    def tearDown(self):
        for name, original in self._original_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
        sys.modules.pop("commander_bridge", None)

    def test_commander_prefix_classified_as_commander(self):
        result = self.cb.classify_commander_intent("commander: what should we do?")
        self.assertEqual(result, self.cb.INTENT_COMMANDER)

    def test_commander_prefix_case_insensitive(self):
        result = self.cb.classify_commander_intent("Commander: status?")
        self.assertEqual(result, self.cb.INTENT_COMMANDER)

    def test_decision_prefix_unchanged(self):
        result = self.cb.classify_commander_intent("decision: we choose X")
        self.assertEqual(result, self.cb.INTENT_DECISION)

    def test_memory_prefix_unchanged(self):
        result = self.cb.classify_commander_intent("remember: supabase is the db")
        self.assertEqual(result, self.cb.INTENT_MEMORY)

    def test_mission_prefix_unchanged(self):
        result = self.cb.classify_commander_intent("create mission: build auth layer")
        self.assertEqual(result, self.cb.INTENT_MISSION_CANDIDATE)

    def test_general_text_unchanged(self):
        result = self.cb.classify_commander_intent("what is the priority?")
        self.assertEqual(result, self.cb.INTENT_GENERAL)

    def test_commander_wins_over_embedded_keywords(self):
        # 'commander:' prefix should win even if text contains 'decision'
        result = self.cb.classify_commander_intent("commander: decision time")
        self.assertEqual(result, self.cb.INTENT_COMMANDER)


# ===========================================================================
# handle_slack_message: INTENT_COMMANDER path returns DI synthesis
# ===========================================================================

class TestHandleSlackMessageCommanderIntent(unittest.TestCase):
    """End-to-end: commander: prefix → run_supabase_commander → response_text."""

    _original_modules: dict

    def setUp(self):
        import importlib
        self._original_modules = {}
        stubs = _make_stubs(run_commander_fn=lambda q, **kw: f"DI synthesis: {q}")
        for name, mod in stubs.items():
            self._original_modules[name] = sys.modules.get(name)
            sys.modules[name] = mod

        for dep in ("specialist_registry", "github_awareness", "mission_registry",
                    "repository_awareness", "knowledge_retrieval", "mission_executor"):
            if dep not in sys.modules:
                fake = types.ModuleType(dep)
                fake.match_specialists_to_request = lambda t: []
                fake.is_github_awareness_request = lambda t: False
                fake.is_mission_registry_request = lambda t: False
                fake.is_repository_awareness_request = lambda t: False
                fake.is_knowledge_retrieval_request = lambda t: False
                fake.identify_knowledge_domain = lambda t: "general"
                fake.is_mission_execution_request = lambda t: False
                self._original_modules[dep] = sys.modules.get(dep)
                sys.modules[dep] = fake

        sys.modules.pop("commander_bridge", None)
        import commander_bridge as _cb
        importlib.reload(_cb)
        self.handle = _cb.handle_slack_message
        self.INTENT_COMMANDER = _cb.INTENT_COMMANDER

    def tearDown(self):
        for name, original in self._original_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
        sys.modules.pop("commander_bridge", None)

    def test_commander_prefix_gets_di_response(self):
        result = self.handle(
            text="commander: should we prioritise Supabase?",
            user_id="U123",
            channel_id="C456",
        )
        self.assertEqual(result["intent"], self.INTENT_COMMANDER)
        self.assertIn("DI synthesis", result["response_text"])
        self.assertIn("should we prioritise Supabase", result["response_text"])

    def test_bot_mention_stripped_before_commander_check(self):
        result = self.handle(
            text="<@BOT123> commander: what's the bottleneck?",
            user_id="U123",
            channel_id="C456",
        )
        self.assertEqual(result["intent"], self.INTENT_COMMANDER)
        self.assertIn("what's the bottleneck", result["response_text"])

    def test_non_commander_message_unchanged(self):
        result = self.handle(
            text="what is the mission status?",
            user_id="U123",
            channel_id="C456",
        )
        self.assertNotEqual(result["intent"], self.INTENT_COMMANDER)

    def test_decision_prefix_routes_to_decision_not_commander(self):
        result = self.handle(text="decision: we choose Supabase", user_id="U", channel_id="C")
        self.assertNotEqual(result["intent"], self.INTENT_COMMANDER)

    def test_result_structure_complete(self):
        result = self.handle(
            text="commander: is this a good idea?",
            user_id="U1",
            channel_id="C1",
        )
        for key in ("ok", "response_text", "route", "confidence", "logged", "intent"):
            self.assertIn(key, result)

    def test_commander_without_question_still_responds(self):
        # Empty after stripping prefix — Commander should still run
        result = self.handle(text="commander:", user_id="U", channel_id="C")
        self.assertEqual(result["intent"], self.INTENT_COMMANDER)
        self.assertIsInstance(result["response_text"], str)


if __name__ == "__main__":
    unittest.main(verbosity=2)
