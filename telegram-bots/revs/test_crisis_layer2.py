#!/usr/bin/env python3
"""Tests for crisis_layer2.py — REVS Layer-2 crisis confirmation.

Run from repo root:
    python -m pytest telegram-bots/revs/test_crisis_layer2.py -v

No Supabase connection, no live LLM credentials required — every provider
call is mocked.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

import crisis_layer2

# ── should_run_layer2 (Stage 1 pre-filter) ──────────────────────────────────

class TestShouldRunLayer2:
    def test_empty_text_never_runs(self):
        assert crisis_layer2.should_run_layer2("") is False
        assert crisis_layer2.should_run_layer2(None) is False

    def test_ordinary_message_does_not_trigger(self):
        assert crisis_layer2.should_run_layer2("I went for a walk today, feeling okay") is False

    def test_ambiguous_method_nouns_trigger(self):
        for text in [
            "I've been saving up my pills",
            "took a bunch of tablets earlier",
            "thinking about the bridge near my place",
            "have a rope in the garage",
            "bought a gun yesterday",
            "how many pills would it take",
        ]:
            assert crisis_layer2.should_run_layer2(text) is True, text

    def test_case_insensitive(self):
        assert crisis_layer2.should_run_layer2("I BOUGHT A GUN") is True

    def test_ordinary_medical_context_still_trips_prefilter(self):
        """Stage 1 is deliberately broad — it only gates an LLM call, not
        an escalation, so an everyday "took my tablets" message correctly
        reaches Stage 2, which is where the real disambiguation happens."""
        assert crisis_layer2.should_run_layer2("took my tablets for my headache") is True


# ── _parse_verdict ───────────────────────────────────────────────────────────

class TestParseVerdict:
    def test_valid_json(self):
        assert crisis_layer2._parse_verdict('{"verdict": "crisis", "reasoning": "x"}') == "crisis"

    def test_valid_json_not_crisis(self):
        assert crisis_layer2._parse_verdict('{"verdict": "not_crisis"}') == "not_crisis"

    def test_markdown_fenced_json(self):
        raw = '```json\n{"verdict": "uncertain", "reasoning": "ambiguous"}\n```'
        assert crisis_layer2._parse_verdict(raw) == "uncertain"

    def test_plain_fence_without_language_tag(self):
        raw = '```\n{"verdict": "not_crisis"}\n```'
        assert crisis_layer2._parse_verdict(raw) == "not_crisis"

    def test_invalid_json_returns_none(self):
        assert crisis_layer2._parse_verdict("this is not json at all") is None

    def test_non_dict_json_returns_none(self):
        assert crisis_layer2._parse_verdict('["crisis"]') is None

    def test_missing_verdict_field_returns_none(self):
        assert crisis_layer2._parse_verdict('{"reasoning": "no verdict key"}') is None

    def test_invalid_verdict_value_returns_none(self):
        """A hallucinated/out-of-enum value must never be trusted as-is —
        same shape-validation discipline as router_client.py."""
        assert crisis_layer2._parse_verdict('{"verdict": "definitely_fine"}') is None

    def test_verdict_wrong_type_returns_none(self):
        assert crisis_layer2._parse_verdict('{"verdict": 1}') is None


# ── _call_provider_chain ─────────────────────────────────────────────────────

class TestCallProviderChain:
    def test_first_provider_success_short_circuits(self):
        with patch.object(crisis_layer2, "call_gemini") as mock_gemini, \
             patch.object(crisis_layer2, "call_mistral") as mock_mistral:
            mock_gemini.return_value.text = '{"verdict": "not_crisis"}'
            result = crisis_layer2._call_provider_chain("some prompt")
        assert result == '{"verdict": "not_crisis"}'
        mock_mistral.assert_not_called()

    def test_falls_through_on_provider_failure(self):
        with patch.object(crisis_layer2, "call_gemini", side_effect=RuntimeError("no key")), \
             patch.object(crisis_layer2, "call_mistral") as mock_mistral:
            mock_mistral.return_value.text = '{"verdict": "crisis"}'
            result = crisis_layer2._call_provider_chain("some prompt")
        assert result == '{"verdict": "crisis"}'

    def test_all_providers_fail_returns_none(self):
        with patch.object(crisis_layer2, "call_gemini", side_effect=RuntimeError()), \
             patch.object(crisis_layer2, "call_mistral", side_effect=RuntimeError()), \
             patch.object(crisis_layer2, "call_ollama", side_effect=RuntimeError()):
            result = crisis_layer2._call_provider_chain("some prompt")
        assert result is None

    def test_empty_text_response_treated_as_failure_falls_through(self):
        with patch.object(crisis_layer2, "call_gemini") as mock_gemini, \
             patch.object(crisis_layer2, "call_mistral") as mock_mistral:
            mock_gemini.return_value.text = ""
            mock_mistral.return_value.text = '{"verdict": "not_crisis"}'
            result = crisis_layer2._call_provider_chain("some prompt")
        assert result == '{"verdict": "not_crisis"}'


# ── confirm_crisis_context (fail-open behaviour) ─────────────────────────────

def _run(coro):
    return asyncio.run(coro)


class TestConfirmCrisisContext:
    def test_returns_valid_verdict_on_success(self):
        with patch.object(crisis_layer2, "_call_provider_chain", return_value='{"verdict": "not_crisis"}'):
            result = _run(crisis_layer2.confirm_crisis_context("took my tablets for my headache"))
        assert result == "not_crisis"

    def test_all_providers_down_fails_open_to_uncertain(self):
        """The core safety property: a total provider outage must never be
        indistinguishable from a genuine 'not_crisis' determination."""
        with patch.object(crisis_layer2, "_call_provider_chain", return_value=None):
            result = _run(crisis_layer2.confirm_crisis_context("bought a gun yesterday"))
        assert result == "uncertain"

    def test_unparseable_llm_response_fails_open_to_uncertain(self):
        with patch.object(crisis_layer2, "_call_provider_chain", return_value="I cannot help with that."):
            result = _run(crisis_layer2.confirm_crisis_context("bought a gun yesterday"))
        assert result == "uncertain"

    def test_hallucinated_verdict_value_fails_open_to_uncertain(self):
        with patch.object(crisis_layer2, "_call_provider_chain", return_value='{"verdict": "maybe"}'):
            result = _run(crisis_layer2.confirm_crisis_context("bought a gun yesterday"))
        assert result == "uncertain"

    def test_genuine_crisis_verdict_passes_through(self):
        with patch.object(crisis_layer2, "_call_provider_chain", return_value='{"verdict": "crisis"}'):
            result = _run(crisis_layer2.confirm_crisis_context("I've been saving up my pills, can't do this anymore"))
        assert result == "crisis"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
