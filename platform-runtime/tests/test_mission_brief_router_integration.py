"""
Tests for the Engineering Router integration in /mission-brief.

Covers:
- _parse_router_args: mission ID detection, flag parsing, alias resolution
- handle_mission_brief routing: mission ID → router, free text → Mistral Scribe
- handle_mission_brief_from_router: success, unknown ID, missing key, provider failure
- _format_router_slack_response: message structure
- _extract_router_sections: section extraction
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Repo root on sys.path ──────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Stub heavy slack-bolt dependency before importing mission_brief
_slack_stub = types.ModuleType("slack_bolt")
_slack_stub.App = object
sys.modules.setdefault("slack_bolt", _slack_stub)

BOT_DIR = REPO_ROOT / "slack-bot"
if str(BOT_DIR) not in sys.path:
    sys.path.insert(0, str(BOT_DIR))

from commands.mission_brief import (
    _extract_router_sections,
    _format_router_slack_response,
    _parse_router_args,
    handle_mission_brief,
    handle_mission_brief_from_router,
)


# ─── _parse_router_args ───────────────────────────────────────────────────────

class TestParseRouterArgs:
    def test_bare_mission_id(self):
        mid, backend, mode = _parse_router_args("MSN-0056")
        assert mid == "USS-TJR-MSN-0056"
        assert backend == "mistral"
        assert mode == "plan"

    def test_full_mission_id(self):
        mid, backend, mode = _parse_router_args("USS-TJR-MSN-0048")
        assert mid == "USS-TJR-MSN-0048"

    def test_backend_flag(self):
        mid, backend, mode = _parse_router_args("MSN-0056 --backend gemini")
        assert mid == "USS-TJR-MSN-0056"
        assert backend == "gemini"

    def test_mode_flag(self):
        mid, backend, mode = _parse_router_args("MSN-0048 --mode review")
        assert mode == "review"

    def test_both_flags(self):
        mid, backend, mode = _parse_router_args("MSN-0048 --backend vm-ollama --mode patch")
        assert backend == "vm-ollama"
        assert mode == "patch"

    def test_free_text_not_detected(self):
        mid, backend, mode = _parse_router_args("Build a new dashboard widget")
        assert mid is None

    def test_empty_string(self):
        mid, backend, mode = _parse_router_args("")
        assert mid is None

    def test_case_insensitive_msn(self):
        mid, _, _ = _parse_router_args("msn-0012")
        assert mid == "USS-TJR-MSN-0012"

    def test_extra_whitespace(self):
        mid, _, _ = _parse_router_args("  MSN-0056  ")
        assert mid == "USS-TJR-MSN-0056"


# ─── _extract_router_sections ─────────────────────────────────────────────────

class TestExtractRouterSections:
    _SAMPLE = (
        "## Summary\nThis fixes the auth bug.\n"
        "## Implementation Steps\n1. Edit auth.py\n2. Run tests\n"
        "## Risks\nRace condition possible.\n"
        "## Acceptance Criteria\nAll tests pass.\n"
    )

    def test_summary_extracted(self):
        s = _extract_router_sections(self._SAMPLE)
        assert "auth bug" in s["summary"]

    def test_steps_extracted(self):
        s = _extract_router_sections(self._SAMPLE)
        assert "Edit auth.py" in s["steps"]

    def test_empty_when_no_headings(self):
        s = _extract_router_sections("Just some plain text without any headings.")
        assert all(v == "" for v in s.values())


# ─── _format_router_slack_response ────────────────────────────────────────────

class TestFormatRouterSlackResponse:
    def test_contains_mission_id(self):
        msg = _format_router_slack_response(
            mission_id="USS-TJR-MSN-0056",
            title="Test mission",
            backend="gemini",
            model_used="gemini-2.5-flash",
            mode="plan",
            output_text="## Summary\nDo the thing.",
            evidence_path="/tmp/evidence.json",
            warnings=None,
        )
        assert "USS-TJR-MSN-0056" in msg

    def test_adr030_notice_present(self):
        msg = _format_router_slack_response(
            mission_id="USS-TJR-MSN-0056",
            title="T",
            backend="mistral",
            model_used="m",
            mode="plan",
            output_text="plain text",
            evidence_path="/tmp/e.json",
            warnings=None,
        )
        assert "ADR-030" in msg

    def test_warnings_shown(self):
        msg = _format_router_slack_response(
            mission_id="USS-TJR-MSN-0056",
            title="T",
            backend="mistral",
            model_used="m",
            mode="plan",
            output_text="plain text",
            evidence_path="/tmp/e.json",
            warnings=["POSSIBLE_HALLUCINATION: invented path"],
        )
        assert "POSSIBLE_HALLUCINATION" in msg

    def test_evidence_path_shown(self):
        msg = _format_router_slack_response(
            mission_id="USS-TJR-MSN-0056",
            title="T",
            backend="mistral",
            model_used="m",
            mode="plan",
            output_text="plain text",
            evidence_path="/tmp/e.json",
            warnings=None,
        )
        assert "/tmp/e.json" in msg


# ─── handle_mission_brief routing ────────────────────────────────────────────

class TestHandleMissionBriefRouting:
    """handle_mission_brief should route mission IDs to router and free text to Scribe."""

    def test_free_text_calls_mistral_scribe(self):
        with patch("commands.mission_brief._call_mistral_mission_scribe") as mock_scribe, \
             patch("commands.mission_brief._normalize_brief_output", side_effect=lambda x: x):
            mock_scribe.return_value = "A brief"
            result = handle_mission_brief("Build a cool feature", "U123", "C456")
        mock_scribe.assert_called_once()
        assert "BRIEF" in result

    def test_mission_id_routes_to_router(self):
        router_output = "*ENGINEERING BRIEF — USS-TJR-MSN-0056*\nTitle: something\n..."
        with patch("commands.mission_brief.handle_mission_brief_from_router", return_value=router_output) as mock_router:
            result = handle_mission_brief("MSN-0056 --backend gemini", "U123", "C456")
        mock_router.assert_called_once_with("USS-TJR-MSN-0056", "gemini", "plan")
        assert result == router_output

    def test_empty_text_returns_usage(self):
        result = handle_mission_brief("", "U123", "C456")
        assert "USS-TJR-MSN-XXXX" in result or "MSN-XXXX" in result

    def test_unknown_mission_id_returns_error(self):
        with patch("commands.mission_brief.handle_mission_brief_from_router",
                   side_effect=ValueError("Mission 'USS-TJR-MSN-9999' not found")):
            result = handle_mission_brief("MSN-9999", "U123", "C456")
        assert ":x:" in result
        assert "not found" in result.lower()

    def test_missing_api_key_returns_config_error(self):
        with patch("commands.mission_brief.handle_mission_brief_from_router",
                   side_effect=RuntimeError("GEMINI_API_KEY is not set")):
            result = handle_mission_brief("MSN-0056 --backend gemini", "U123", "C456")
        assert ":x:" in result
        assert "configuration" in result.lower() or "api key" in result.lower() or "API_KEY" in result

    def test_provider_timeout_returns_unreachable_error(self):
        with patch("commands.mission_brief.handle_mission_brief_from_router",
                   side_effect=RuntimeError("connection refused")):
            result = handle_mission_brief("MSN-0056 --backend vm-ollama", "U123", "C456")
        assert ":x:" in result
        assert "unreachable" in result.lower() or "connect" in result.lower()

    def test_backend_override_passed_through(self):
        with patch("commands.mission_brief.handle_mission_brief_from_router", return_value="ok") as mock_router:
            handle_mission_brief("USS-TJR-MSN-0048 --backend vm-ollama --mode review", "U123", "C456")
        mock_router.assert_called_once_with("USS-TJR-MSN-0048", "vm-ollama", "review")


# ─── handle_mission_brief_from_router unit tests ─────────────────────────────

class TestHandleMissionBriefFromRouter:
    """
    Test the router helper in isolation.

    handle_mission_brief_from_router does lazy imports inside the function body,
    so we patch sys.modules entries that will be resolved at call time.
    """

    def _make_resp(self, success=True, error=None, warnings=None):
        resp = MagicMock()
        resp.success = success
        resp.error = error
        resp.output_text = "## Summary\nDo the thing.\n## Acceptance Criteria\nPasses."
        resp.model_used = "mistral-small-2503"
        resp.warnings = warnings
        resp.evidence_path = "/tmp/ev.json"
        return resp

    def _inject_engineering_mocks(self, resp, ctx=None):
        """Inject fake core.engineering modules into sys.modules for one test."""
        if ctx is None:
            ctx = MagicMock()
            ctx.title = "Test Mission"

        # Schemas stub
        schemas_stub = types.ModuleType("core.engineering.schemas")
        class Backend(str):
            MISTRAL = "mistral"; VM_OLLAMA = "vm-ollama"; GEMINI = "gemini"
            def __new__(cls, v):
                valid = ["mistral", "vm-ollama", "gemini"]
                if v not in valid:
                    raise ValueError(f"Unknown backend `{v}`")
                return str.__new__(cls, v)
        class ExecutionMode(str):
            PLAN = "plan"; PATCH = "patch"; REVIEW = "review"
            def __new__(cls, v):
                valid = ["plan", "patch", "review"]
                if v not in valid:
                    raise ValueError(f"Unknown mode `{v}`")
                return str.__new__(cls, v)
        schemas_stub.Backend = Backend
        schemas_stub.ExecutionMode = ExecutionMode
        schemas_stub.RouterRequest = MagicMock(return_value=MagicMock())

        router_stub = types.ModuleType("core.engineering.engineering_router")
        router_stub.load_mission_context = MagicMock(return_value=ctx)
        router_stub.route = MagicMock(return_value=resp)

        pkg_stub = types.ModuleType("core.engineering")

        return {
            "core.engineering": pkg_stub,
            "core.engineering.schemas": schemas_stub,
            "core.engineering.engineering_router": router_stub,
        }

    def test_success_returns_formatted_message(self):
        resp = self._make_resp()
        mocks = self._inject_engineering_mocks(resp)
        saved = {k: sys.modules.get(k) for k in mocks}
        sys.modules.update(mocks)
        try:
            import commands.mission_brief as mb
            result = mb.handle_mission_brief_from_router("USS-TJR-MSN-0056", "mistral", "plan")
            assert "USS-TJR-MSN-0056" in result
            assert "ADR-030" in result
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def test_invalid_backend_raises_value_error(self):
        resp = self._make_resp()
        mocks = self._inject_engineering_mocks(resp)
        saved = {k: sys.modules.get(k) for k in mocks}
        sys.modules.update(mocks)
        try:
            import commands.mission_brief as mb
            with pytest.raises(ValueError, match="Unknown backend"):
                mb.handle_mission_brief_from_router("USS-TJR-MSN-0056", "nonexistent_backend", "plan")
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def test_invalid_mode_raises_value_error(self):
        resp = self._make_resp()
        mocks = self._inject_engineering_mocks(resp)
        saved = {k: sys.modules.get(k) for k in mocks}
        sys.modules.update(mocks)
        try:
            import commands.mission_brief as mb
            with pytest.raises(ValueError, match="Unknown mode"):
                mb.handle_mission_brief_from_router("USS-TJR-MSN-0056", "mistral", "nonexistent_mode")
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
