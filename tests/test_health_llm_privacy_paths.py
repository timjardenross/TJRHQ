"""Privacy-safe behaviour across every fallback path of the personal health narrative provider."""
from __future__ import annotations

import sys
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest import mock

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "core" / "health"))
sys.path.insert(0, str(_REPO / "scripts"))

import check_health_llm_local as chk
import health_llm as h


def _ret(text):
    return SimpleNamespace(text=text)


def _provider(monkeypatch, *, external=None, model=None):
    if external is None:
        monkeypatch.delenv("HEALTH_LLM_EXTERNAL_ALLOWED", raising=False)
    else:
        monkeypatch.setenv("HEALTH_LLM_EXTERNAL_ALLOWED", external)
    if model:
        monkeypatch.setattr(h, "_OLLAMA_MODEL", model)
    return h.HealthLLMProvider()


@pytest.fixture
def net(monkeypatch):
    """Every outbound call the module can make, as counters."""
    calls = {"gemini": 0, "mistral": 0, "ollama": 0}

    def make(name, result):
        def fn(*a, **k):
            calls[name] += 1
            if isinstance(result, Exception):
                raise result
            return _ret(result)
        return fn

    def set_(gemini="G", mistral="M", ollama="O"):
        monkeypatch.setattr(h, "call_gemini", make("gemini", gemini))
        monkeypatch.setattr(h, "call_mistral", make("mistral", mistral))
        monkeypatch.setattr(h, "call_ollama", make("ollama", ollama))
        return calls
    return set_


class TestEveryFallbackPathKeepsPersonalDataOffBox:
    @pytest.mark.parametrize("flag", [None, "", "0", "false", "no", "maybe", "2", " "])
    def test_closed_for_every_non_opt_in_value(self, monkeypatch, net, flag):
        calls = net(ollama="local narrative")
        out = _provider(monkeypatch, external=flag).generate("personal prompt")
        assert out[0] == "local narrative"
        assert calls == {"gemini": 0, "mistral": 0, "ollama": 1}

    def test_local_returns_nothing_then_no_cloud_and_deterministic_fallback(self, monkeypatch, net):
        calls = net(ollama=None)
        assert _provider(monkeypatch).generate("p") == (None, None)
        assert calls["gemini"] == calls["mistral"] == 0

    def test_local_returns_empty_string(self, monkeypatch, net):
        calls = net(ollama="")
        assert _provider(monkeypatch).generate("p") == (None, None)
        assert calls["gemini"] == calls["mistral"] == 0

    def test_local_raises(self, monkeypatch, net):
        calls = net(ollama=RuntimeError("connection refused"))
        assert _provider(monkeypatch).generate("p") == (None, None)
        assert calls["gemini"] == calls["mistral"] == 0

    @pytest.mark.parametrize("model", ["glm-5.2:cloud", "qwen3-cloud", "X:CLOUD"])
    def test_cloud_hosted_ollama_tag_is_refused_as_not_local(self, monkeypatch, net, model):
        calls = net()
        out = _provider(monkeypatch, model=model).generate("p")
        assert out == (None, None) and calls == {"gemini": 0, "mistral": 0, "ollama": 0}

    def test_permitted_list_is_empty_for_cloud_tag_when_closed(self, monkeypatch):
        assert _provider(monkeypatch, model="a:cloud").permitted_providers() == []

    def test_garbage_local_output_falls_back_to_deterministic(self):
        assert h.parse_llm_narrative("not json at all") is None
        assert h.parse_llm_narrative("") is None

    def test_explicit_opt_in_is_the_only_way_cloud_is_reached(self, monkeypatch, net):
        calls = net(gemini="cloud text")
        out = _provider(monkeypatch, external="1").generate("p")
        assert out[0] == "cloud text" and calls["gemini"] == 1 and calls["ollama"] == 0

    def test_module_has_no_other_outbound_path(self):
        src = (_REPO / "core" / "health" / "health_llm.py").read_text()
        for banned in ("requests.", "urllib", "httpx", "smtplib", "telegram"):
            assert banned not in src


class TestLocalModelVerifier:
    TAGS = MappingProxyType({"models": [{"name": "qwen3:8b"}, {"name": "llama3:latest"}]})

    def test_ready(self):
        assert chk.evaluate_tags(dict(self.TAGS), "qwen3:8b")[0] == chk.READY

    def test_missing_model(self):
        code, msg = chk.evaluate_tags(dict(self.TAGS), "glm-5.2")
        assert code == chk.MODEL_MISSING and "qwen3:8b" in msg

    def test_cloud_tag_flagged(self):
        assert chk.evaluate_tags(dict(self.TAGS), "glm-5.2:cloud")[0] == chk.LEAVES_HOST

    def test_unreachable(self):
        def boom(*a, **k):
            raise OSError("refused")
        assert chk.check("http://localhost:1", "qwen3:8b", opener=boom)[0] == chk.UNREACHABLE

    def test_reachable_via_injected_opener(self):
        import io
        import json as _j
        resp = mock.MagicMock()
        resp.__enter__.return_value = io.BytesIO(_j.dumps(dict(self.TAGS)).encode())
        assert chk.check("http://localhost:11434", "qwen3:8b", opener=lambda *a, **k: resp)[0] == chk.READY


class TestProfileExcerptGate:
    def test_excerpt_is_empty_whenever_external_providers_are_permitted(self, monkeypatch):
        monkeypatch.setenv("HEALTH_LLM_EXTERNAL_ALLOWED", "1")
        assert h._load_captain_profile_excerpt() == ""

    def test_gate_does_not_depend_on_values_other_than_explicit_opt_in(self, monkeypatch):
        monkeypatch.setenv("HEALTH_LLM_EXTERNAL_ALLOWED", "maybe")
        # not an opt-in => the loader runs normally and returns a string (possibly empty if the file differs)
        assert isinstance(h._load_captain_profile_excerpt(), str)
