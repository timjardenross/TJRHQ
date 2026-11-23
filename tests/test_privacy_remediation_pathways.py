"""Remaining personal-health pathways (follow-up to #661): intelligence LLM provider, capture enrichment parity, shared detector."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "platform-runtime")]

from core.security import personal_data_policy as pdp
from intelligence.brief import llm_provider as lp

PERSONAL = "Captain pain 7/10, slept 4h, CPAP used, nervous system tense. Brief the day."
PUBLIC = "Summarise today's cyber incidents affecting Australian banks."


@pytest.fixture(autouse=True)
def _closed(monkeypatch):
    monkeypatch.delenv("HEALTH_LLM_EXTERNAL_ALLOWED", raising=False)


def _provider(monkeypatch, *, ollama="local text"):
    calls = []
    p = lp.LLMProvider()
    for name in ("_model_router", "_mistral_pipeline", "_gemini", "_mistral"):
        monkeypatch.setattr(p, name, lambda prompt, _n=name: calls.append(_n) or f"external via {_n}")
    monkeypatch.setattr(p, "_ollama", lambda prompt: calls.append("_ollama") or ollama)
    return p, calls


def test_personal_prompt_never_reaches_an_external_provider(monkeypatch):
    p, calls = _provider(monkeypatch)
    text, _name = p.generate(PERSONAL)
    assert text == "local text" and calls == ["_ollama"]


def test_personal_prompt_fails_closed_when_local_model_unavailable(monkeypatch):
    p, calls = _provider(monkeypatch, ollama=None)
    assert p.generate(PERSONAL) == (None, None) and calls == ["_ollama"]


def test_public_intelligence_workflow_keeps_the_cloud_chain(monkeypatch):
    p, calls = _provider(monkeypatch)
    text, _ = p.generate(PUBLIC)
    assert calls[0] == "_model_router" and text.startswith("external via")


def test_explicit_opt_in_restores_the_chain(monkeypatch):
    monkeypatch.setenv("HEALTH_LLM_EXTERNAL_ALLOWED", "1")
    p, calls = _provider(monkeypatch)
    p.generate(PERSONAL)
    assert calls[0] == "_model_router"


def test_unclassifiable_prompt_is_treated_as_personal(monkeypatch):
    monkeypatch.setattr(pdp, "contains_personal_health", lambda t: (_ for _ in ()).throw(RuntimeError("detector down")))
    p, calls = _provider(monkeypatch)
    p.generate(PUBLIC)
    assert calls == ["_ollama"]


def test_qa_and_risk_checks_skip_personal_briefs_but_run_for_public_ones(monkeypatch):
    monkeypatch.setattr(lp, "MISTRAL_API_KEY", "k")
    monkeypatch.setattr(lp, "MISTRAL_QA_AGENT_ID", "qa")
    monkeypatch.setattr(lp, "MISTRAL_CHALLENGE_AGENT_ID", "ch")
    p = lp.LLMProvider()
    seen = []
    monkeypatch.setattr(p, "_call_agent", lambda **k: seen.append(k["stage"]) or "OK")
    assert p.check_brief_quality(PERSONAL) is None and p.check_risk_rating(PERSONAL, "high") is None and seen == []
    assert p.check_brief_quality(PUBLIC) == "OK" and p.check_risk_rating(PUBLIC, "high") == "OK" and len(seen) == 2


def test_direct_provider_calls_are_blocked_by_the_backstop(monkeypatch):
    fake = type(sys)("mistralai")
    fake.Mistral = lambda **k: (_ for _ in ()).throw(AssertionError("client constructed for personal content"))
    monkeypatch.setitem(sys.modules, "mistralai", fake)
    monkeypatch.setattr(lp, "MISTRAL_API_KEY", "k")
    p = lp.LLMProvider()
    for fn in (lambda: p._call_agent("s", "a", 1, PERSONAL), lambda: p._gemini(PERSONAL), lambda: p._mistral(PERSONAL), lambda: p._model_router(PERSONAL)):
        with pytest.raises(pdp.PersonalDataBlockedError):
            fn()


def test_shared_pattern_file_is_the_single_source():
    doc = json.loads((_REPO / "core/security/personal_health_patterns.json").read_text())
    assert [n for n, _ in pdp._PATTERNS] == [e["name"] for e in doc["structured"]]
    assert doc["conservative_free_text"], "capture guard lexicon missing"


FIXTURES = json.loads((_REPO / "core/security/personal_health_fixtures.json").read_text())


@pytest.mark.parametrize("text", FIXTURES["structured_positive"])
def test_structured_detector_flags_shared_positive_fixtures(text):
    assert pdp.contains_personal_health(text)


@pytest.mark.parametrize("text", FIXTURES["structured_negative"])
def test_structured_detector_ignores_shared_negative_fixtures(text):
    assert not pdp.contains_personal_health(text)


def test_portal_pattern_copy_is_identical_to_the_shared_file():
    shared = (_REPO / "core/security/personal_health_patterns.json").read_text()
    assert (_REPO / "lcars-portal/src/lib/personal_health_patterns.json").read_text() == shared
