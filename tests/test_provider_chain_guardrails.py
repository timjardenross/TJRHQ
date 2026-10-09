"""USS-TJR-MSN-0412 Stream 5: call_gemini / call_mistral must pass every outbound prompt
through the same guard the model router uses (input rail, Presidio redaction, output rail)
and FAIL CLOSED, i.e. nothing reaches the provider unless the guard allowed it.

The guard functions and urlopen are faked: no test touches the network or the real worker.
"""
from __future__ import annotations

import fcntl
import io
import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from core.llm import provider_chain as pc
from core.security.llm_guardrails import (
    BlockedByGuardrailsError,
    GuardrailsUnavailableError,
    RedactionResult,
)

SYSTEM = "You are a careful analyst."
PROMPT = "Summarise the note from Jane Citizen (jane@example.org)."
REDACTED_SYSTEM = SYSTEM
REDACTED_PROMPT = "Summarise the note from <PERSON> (<EMAIL_ADDRESS>)."

GEMINI_RESPONSE = {
    "candidates": [{"content": {"parts": [{"text": " ok "}]}}],
    "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1},
}
MISTRAL_RESPONSE = {
    "choices": [{"message": {"content": " ok "}}],
    "model": "mistral-small-latest",
    "usage": {"prompt_tokens": 3, "completion_tokens": 1},
}


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def _private_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_CHAIN_GUARD_LOCK", str(tmp_path / "guard.lock"))


@pytest.fixture
def guard(monkeypatch):
    """Fake guard that records calls and redacts by simple replacement."""
    calls = {"input": [], "redact": [], "output": []}

    def fake_input(text, **_kw):
        calls["input"].append(text)

    def fake_redact(text):
        calls["redact"].append(text)
        out = text.replace("Jane Citizen", "<PERSON>").replace("jane@example.org", "<EMAIL_ADDRESS>")
        return RedactionResult(redacted_text=out, findings=[])

    def fake_output(text, **_kw):
        calls["output"].append(text)

    monkeypatch.setattr(pc, "check_input_rail", fake_input)
    monkeypatch.setattr(pc, "redact_pii", fake_redact)
    monkeypatch.setattr(pc, "check_output_rail", fake_output)
    return calls


def _provider(monkeypatch, payload):
    sent = []

    def fake_urlopen(req, timeout=None):
        sent.append(req.data.decode())
        return _Resp(json.dumps(payload).encode())

    monkeypatch.setattr(pc.urllib.request, "urlopen", fake_urlopen)
    return sent


CALLS = [
    pytest.param(lambda: pc.call_gemini(SYSTEM, PROMPT, api_key="k"), GEMINI_RESPONSE, id="gemini"),
    pytest.param(lambda: pc.call_mistral(SYSTEM, PROMPT, api_key="k"), MISTRAL_RESPONSE, id="mistral"),
]


@pytest.mark.parametrize(("call", "payload"), CALLS)
def test_guard_runs_and_only_redacted_text_is_sent(call, payload, guard, monkeypatch):
    sent = _provider(monkeypatch, payload)
    result = call()
    assert result.text == "ok"
    assert len(guard["input"]) == 1 and PROMPT in guard["input"][0]      # input rail saw the real prompt
    assert len(guard["redact"]) == 1                                      # one Presidio call for both parts
    assert guard["output"] == ["ok"]                                      # output rail saw the response
    assert len(sent) == 1
    assert "<PERSON>" in sent[0] and "<EMAIL_ADDRESS>" in sent[0]
    assert "Jane Citizen" not in sent[0] and "jane@example.org" not in sent[0]
    assert pc._PART_BOUNDARY.strip() not in sent[0]                       # marker never leaks to the provider


@pytest.mark.parametrize(("call", "payload"), CALLS)
def test_unavailable_guard_refuses_and_nothing_is_sent(call, payload, guard, monkeypatch):
    sent = _provider(monkeypatch, payload)

    def boom(_text):
        raise GuardrailsUnavailableError("llmsec venv not found")

    monkeypatch.setattr(pc, "redact_pii", boom)
    with pytest.raises(GuardrailsUnavailableError):
        call()
    assert sent == []


@pytest.mark.parametrize(("call", "payload"), CALLS)
def test_blocked_input_refuses_and_nothing_is_sent(call, payload, guard, monkeypatch):
    sent = _provider(monkeypatch, payload)

    def block(_text, **_kw):
        raise BlockedByGuardrailsError("input blocked by jailbreak rail")

    monkeypatch.setattr(pc, "check_input_rail", block)
    with pytest.raises(BlockedByGuardrailsError):
        call()
    assert sent == [] and guard["redact"] == []                           # blocked before redaction, as in the router


@pytest.mark.parametrize(("call", "payload"), CALLS)
def test_overlong_text_is_never_sent_raw(call, payload, guard, monkeypatch):
    """The spaCy E088 case: text the redactor cannot handle must be refused, not sent as-is."""
    sent = _provider(monkeypatch, payload)
    monkeypatch.setattr(pc, "_MAX_GUARDED_CHARS", 100)
    with pytest.raises(BlockedByGuardrailsError, match="limit"):
        pc.call_gemini(SYSTEM, "x" * 200, api_key="k") if payload is GEMINI_RESPONSE else pc.call_mistral(
            SYSTEM, "x" * 200, api_key="k"
        )
    assert sent == [] and guard["input"] == [] and guard["redact"] == []  # refused before any worker or send


@pytest.mark.parametrize(("call", "payload"), CALLS)
def test_blocked_output_is_not_returned(call, payload, guard, monkeypatch):
    _provider(monkeypatch, payload)

    def block(_text, **_kw):
        raise BlockedByGuardrailsError("output blocked by leak rail")

    monkeypatch.setattr(pc, "check_output_rail", block)
    with pytest.raises(BlockedByGuardrailsError):
        call()


@pytest.mark.parametrize(("call", "payload"), CALLS)
def test_altered_boundary_refuses(call, payload, guard, monkeypatch):
    sent = _provider(monkeypatch, payload)
    monkeypatch.setattr(pc, "redact_pii", lambda text: RedactionResult(redacted_text="mangled, no boundary"))
    with pytest.raises(BlockedByGuardrailsError, match="boundary"):
        call()
    assert sent == []


def test_missing_key_fails_before_the_guard_runs(guard):
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        pc.call_gemini(SYSTEM, PROMPT, api_key="")
    with pytest.raises(RuntimeError, match="MISTRAL_API_KEY"):
        pc.call_mistral(SYSTEM, PROMPT, api_key="")
    assert guard == {"input": [], "redact": [], "output": []}


def test_guard_errors_are_runtime_errors_so_callers_fall_through():
    assert issubclass(GuardrailsUnavailableError, RuntimeError) and issubclass(BlockedByGuardrailsError, RuntimeError)


def test_ollama_is_local_and_unguarded(guard, monkeypatch):
    sent = _provider(monkeypatch, {"response": "ok", "prompt_eval_count": 1, "eval_count": 1})
    result = pc.call_ollama(SYSTEM, PROMPT, base_url="http://localhost:11434", model="m")
    assert result.text == "ok" and len(sent) == 1
    assert guard == {"input": [], "redact": [], "output": []}
    assert "Jane Citizen" in sent[0]                                      # local: unchanged by design


def test_busy_guard_lock_fails_closed(guard, monkeypatch, tmp_path):
    sent = _provider(monkeypatch, GEMINI_RESPONSE)
    monkeypatch.setattr(pc, "_GUARD_LOCK_WAIT_S", 0.3)
    holder = os.open(pc._guard_lock_path(), os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(holder, fcntl.LOCK_EX)
    try:
        with pytest.raises(GuardrailsUnavailableError, match="busy"):
            pc.call_gemini(SYSTEM, PROMPT, api_key="k")
    finally:
        os.close(holder)
    assert sent == [] and guard["input"] == []


def test_guard_lock_is_released_after_each_call(guard, monkeypatch):
    _provider(monkeypatch, GEMINI_RESPONSE)
    pc.call_gemini(SYSTEM, PROMPT, api_key="k")
    pc.call_gemini(SYSTEM, PROMPT, api_key="k")                           # would block/raise if the first leaked the lock
    assert len(guard["input"]) == 2


def test_lock_is_released_when_the_guard_raises(guard, monkeypatch):
    _provider(monkeypatch, GEMINI_RESPONSE)
    monkeypatch.setattr(pc, "check_input_rail", mock.Mock(side_effect=BlockedByGuardrailsError("no")))
    monkeypatch.setattr(pc, "_GUARD_LOCK_WAIT_S", 0.3)
    for _ in range(2):
        with pytest.raises(BlockedByGuardrailsError):
            pc.call_gemini(SYSTEM, PROMPT, api_key="k")                   # second call proves the lock was freed
