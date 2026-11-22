"""#661 failure paths: timeout, connection failure, misconfiguration, logging and error text.

These run the REAL router/cloud call functions and patch only urllib.request.urlopen, recording the
host of every request, so "no off-box request was attempted" is asserted at the network layer."""
from __future__ import annotations

import io
import json
import logging
import sys
import urllib.error
from pathlib import Path
from unittest import mock

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "platform-runtime"))

from core.security import personal_data_policy as pol

SECRET = "sleep=5.5h nervous_system=activated energy=low Captain's pain is worse"
PERSONAL_PROMPT = f"How am I doing? Wellness context: {SECRET}"


class _Net:
    """Records requested hosts; behaviour is chosen per host class."""
    def __init__(self, router="timeout"):
        self.hosts, self.bodies, self.router = [], [], router

    def __call__(self, req, timeout=None):
        from urllib.parse import urlparse
        host = urlparse(req.full_url).hostname
        self.hosts.append(host)
        self.bodies.append(req.data)
        if host in {"127.0.0.1", "localhost"}:
            if self.router == "timeout":
                raise TimeoutError("timed out")
            if self.router == "refused":
                raise urllib.error.URLError(ConnectionRefusedError(111, "refused"))
            if self.router == "garbage":
                return io.BytesIO(b"<html>not json</html>")
            if self.router == "empty":
                return io.BytesIO(json.dumps({"response": ""}).encode())
            return _Resp(json.dumps({"response": "local answer"}).encode())
        raise AssertionError(f"off-box request attempted to {host}")


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in (pol.FLAG, "OLLAMA_CLOUD_DISABLED", "LLM_PERSONAL_ROUTER_TIMEOUT", "MODEL_ROUTER_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("OLLAMA_API_KEY", "dummy-key")          # cloud tier fully configured


@pytest.fixture
def tl():
    import telegram_bots.llm as tl
    return tl


@pytest.mark.parametrize("mode", ["timeout", "refused", "garbage", "empty"])
@pytest.mark.parametrize("kwargs", [{"personal": True}, {"personal": False}, {"personal": True, "cloud_first": True}])
def test_local_router_failure_never_reaches_cloud(tl, mode, kwargs):
    prompt = PERSONAL_PROMPT if not kwargs.get("personal") else "hello"
    net = _Net(router=mode)
    with mock.patch.object(tl.urllib.request, "urlopen", net):
        assert tl.generate(prompt, "sys", **kwargs) is None
    assert net.hosts and set(net.hosts) <= {"127.0.0.1", "localhost"}


def test_router_success_returns_local_answer_without_cloud(tl):
    net = _Net(router="ok")
    with mock.patch.object(tl.urllib.request, "urlopen", net):
        assert tl.generate("x", "sys", personal=True) == "local answer"
    assert set(net.hosts) == {"127.0.0.1"}


def test_personal_route_uses_extended_timeout(tl, monkeypatch):
    seen = {}
    def fake(req, timeout=None):
        seen["t"] = timeout
        return _Resp(json.dumps({"response": "ok"}).encode())
    monkeypatch.setenv("LLM_PERSONAL_ROUTER_TIMEOUT", "75")
    with mock.patch.object(tl.urllib.request, "urlopen", fake):
        tl.generate("x", "sys", personal=True)
    assert seen["t"] == 75


@pytest.mark.parametrize("bad", ["abc", "", "-", "nan?"])
def test_bad_timeout_config_falls_back_to_default_and_stays_local(tl, monkeypatch, bad):
    monkeypatch.setenv("LLM_PERSONAL_ROUTER_TIMEOUT", bad)
    net = _Net(router="timeout")
    with mock.patch.object(tl.urllib.request, "urlopen", net):
        assert tl.generate("x", "sys", personal=True) is None
    assert set(net.hosts) <= {"127.0.0.1"}


@pytest.mark.parametrize("url", ["https://router.example.com", "http://8.8.8.8:8891", "http://evil.test", "not a url", ""])
def test_misconfigured_nonlocal_router_is_refused_for_personal_routes(tl, monkeypatch, url):
    monkeypatch.setenv("MODEL_ROUTER_URL", url)
    with mock.patch.object(tl.urllib.request, "urlopen") as net:
        assert tl.generate("x", "sys", personal=True) is None
        assert tl.generate(PERSONAL_PROMPT, None) is None
        net.assert_not_called()


@pytest.mark.parametrize("url", ["http://127.0.0.1:8891", "http://localhost:8891", "http://10.0.0.5:8891", "http://[::1]:8891"])
def test_local_and_private_router_addresses_are_accepted(tl, monkeypatch, url):
    monkeypatch.setenv("MODEL_ROUTER_URL", url)
    assert tl._router_is_local()


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe", "2", " "])
def test_unrecognised_flag_values_stay_closed(tl, monkeypatch, value):
    monkeypatch.setenv(pol.FLAG, value)
    assert not pol.external_ai_allowed()
    net = _Net(router="timeout")
    with mock.patch.object(tl.urllib.request, "urlopen", net):
        assert tl.generate("x", "sys", personal=True) is None
    assert set(net.hosts) <= {"127.0.0.1"}


def test_cloud_tier_unreachable_on_opt_in_still_returns_none_cleanly(tl, monkeypatch):
    monkeypatch.setenv(pol.FLAG, "1")
    def boom(req, timeout=None):
        raise urllib.error.URLError("network down")
    with mock.patch.object(tl.urllib.request, "urlopen", boom):
        assert tl.generate(PERSONAL_PROMPT, "sys") is None            # no exception escapes


def test_public_route_cloud_fallback_unchanged(tl):
    hosts = []
    def fake(req, timeout=None):
        from urllib.parse import urlparse
        hosts.append(urlparse(req.full_url).hostname)
        if hosts[-1] == "127.0.0.1":
            raise TimeoutError("t")
        return _Resp(json.dumps({"message": {"content": "cloud answer"}}).encode())
    with mock.patch.object(tl.urllib.request, "urlopen", fake):
        assert tl.generate("What is the capital of France?", "sys") == "cloud answer"
    assert hosts == ["127.0.0.1", "ollama.com"]


def test_no_personal_text_in_logs_or_exceptions(tl, caplog):
    caplog.set_level(logging.DEBUG)
    for mode in ("timeout", "refused", "garbage"):
        with mock.patch.object(tl.urllib.request, "urlopen", _Net(router=mode)):
            tl.generate(PERSONAL_PROMPT, "sys", personal=True)
            tl.generate(PERSONAL_PROMPT, "sys", cloud_first=True)
    with mock.patch.object(tl.urllib.request, "urlopen") as net:
        tl._call_cloud(PERSONAL_PROMPT, "sys")
        net.assert_not_called()
    text = "\n".join(r.getMessage() for r in caplog.records)
    for fragment in ("5.5h", "activated", "pain is worse", "How am I doing"):
        assert fragment not in text
    with pytest.raises(pol.PersonalDataBlockedError) as ei:
        pol.assert_may_leave_host(PERSONAL_PROMPT, route="test")
    for fragment in ("5.5h", "activated", "pain is worse"):
        assert fragment not in str(ei.value)


def test_provider_chain_failures_do_not_leak_or_connect(caplog):
    from core.llm import provider_chain as pc
    caplog.set_level(logging.DEBUG)
    with mock.patch.object(pc.urllib.request, "urlopen") as net:
        for fn, kw in ((pc.call_gemini, {"api_key": "k"}), (pc.call_mistral, {"api_key": "k"})):
            with pytest.raises(pol.PersonalDataBlockedError) as ei:
                fn("sys", PERSONAL_PROMPT, **kw)
            assert "5.5h" not in str(ei.value)
        net.assert_not_called()
    assert "5.5h" not in caplog.text


# ── Sixth pathway found during the #661 audit: commands/health_synthesis._llm_synthesis ─────────────
WEEKLY = ("*Weekly Health Brief — Medical Officer*\n*Nervous System*\n• Dysregulated: 3/5 days (60%)\n"
          "*Energy*\n• Low: 3/5\n*Sleep* — avg 5.9h over 5 night(s)\n*Recovery Posture*\n• rest: 2 day(s)")
MED_SYS = "The Captain has a chronic spinal condition and is in Stage 1 Stabilisation."


class TestWeeklyHealthSynthesisPathway:
    @pytest.fixture
    def hs(self):
        from commands import health_synthesis as hs
        return hs

    def test_detector_recognises_the_weekly_summary_and_system_prompt(self):
        assert pol.contains_personal_health(WEEKLY)
        assert pol.contains_personal_health(MED_SYS)

    def test_no_external_call_without_opt_in(self, hs):
        import llm
        with mock.patch.object(llm, "generate_with_gemini") as g:
            assert hs._llm_synthesis(WEEKLY) is None
            g.assert_not_called()

    def test_gemini_wrapper_itself_refuses_even_if_the_caller_forgets(self):
        import llm
        with mock.patch("urllib.request.urlopen") as net:
            with pytest.raises(llm.LLMUnavailableError):
                llm.generate_with_gemini(prompt=WEEKLY, system_prompt=MED_SYS)
            net.assert_not_called()

    def test_opt_in_restores_the_call(self, hs, monkeypatch):
        import llm
        monkeypatch.setenv(pol.FLAG, "1")
        with mock.patch.object(llm, "generate_with_gemini", return_value="ok") as g:
            assert hs._llm_synthesis(WEEKLY) == "ok"
            g.assert_called_once()

    @pytest.mark.parametrize("public", [
        "New review finds mindfulness reduces chronic pain",
        "Average sleep duration trends in adolescents: a meta-analysis",
        "Emotion dysregulation in ADHD adults: randomised trial",
        "Captain America film triggers ticketing outage",
    ])
    def test_public_research_text_is_not_flagged(self, public):
        assert not pol.contains_personal_health(public)


# ── Seventh gap found in the #661 audit: journal free text through HealthLLMProvider ────────────────
class TestHealthNarrativeProviderStandalone:
    """#661 must protect the narrative providers WITHOUT #660: journal free text has no structured
    markers the content detector could rely on, so the provider itself is local-only by default."""

    @pytest.fixture
    def h(self, monkeypatch):
        sys.path.insert(0, str(_REPO / "core" / "health"))
        import health_llm as h
        monkeypatch.setenv("GEMINI_API_KEY", "dummy")
        monkeypatch.setenv("MISTRAL_API_KEY", "dummy")
        return h

    def _count(self, h, monkeypatch, prompt):
        calls = {"gemini": 0, "mistral": 0, "ollama": 0}
        for name in calls:
            def make(n):
                def fn(*a, **k):
                    calls[n] += 1
                    raise RuntimeError("provider down")
                return fn
            monkeypatch.setattr(h, f"call_{name}", make(name))
        return calls, h.HealthLLMProvider().generate(prompt)

    def test_journal_free_text_never_reaches_cloud_and_falls_back(self, h, monkeypatch):
        prompt = "[2026-11-10] note: rough day, could not get out of bed | pain_triggers: stairs | coping: rest"
        assert not pol.contains_personal_health(prompt)       # the detector alone would NOT catch this
        calls, out = self._count(h, monkeypatch, prompt)
        assert calls["gemini"] == 0 and calls["mistral"] == 0
        assert out == (None, None)                            # deterministic fallback

    def test_real_weekly_prompt_never_reaches_cloud(self, h, monkeypatch):
        sys.path.insert(0, str(_REPO / "core" / "health"))
        import weekly_synthesis as ws
        prompt = ws._build_llm_prompt("2026-11-16", 6, 4.2, "stable", 6.1, "improving", "moderate", "ok", 55.0,
                                      ["poor sleep"], [], [], {}, {}, [], [], {}, {}, {})
        calls, _ = self._count(h, monkeypatch, prompt)
        assert calls["gemini"] == 0 and calls["mistral"] == 0

    def test_opt_in_is_the_only_way_to_enable_cloud(self, h, monkeypatch):
        monkeypatch.setenv(pol.FLAG, "1")
        calls, _ = self._count(h, monkeypatch, "neutral text")
        assert calls["gemini"] == 1


# ── Telemetry and visible fallback ─────────────────────────────────────────────────────────────────────
class TestTelemetryAndFallbackVisibility:
    def test_llm_spans_carry_no_prompt_or_response_content(self):
        import inspect

        from core.llm import provider_chain as pc
        src = inspect.getsource(pc._llm_span)
        assert '"llm.provider"' in src and '"llm.model"' in src and '"llm.task_type"' in src
        for forbidden in ("prompt", "response", "input.value", "output.value", "content"):
            assert forbidden not in src.split("attributes=")[1]

    def test_trace_export_endpoint_is_local(self):
        text = (_REPO / "platform-runtime" / "lib" / "telemetry.py").read_text()
        assert '_PHOENIX_ENDPOINT = "http://localhost:' in text

    def test_xo_chat_has_a_visible_fallback_when_the_local_model_returns_nothing(self):
        text = (_REPO / "telegram-bots" / "xo" / "app.py").read_text()
        i = text.index("personal=True)")
        tail = text[i:i + 700]
        assert "if reply:" in tail and "LLM unreachable" in tail and "/brief" in tail

    def test_no_repository_file_enables_the_external_health_flag(self):
        import subprocess
        out = subprocess.run(["git", "grep", "-n", "HEALTH_LLM_EXTERNAL_ALLOWED", "--", "deploy", "*.service", "*.env*", "*.sh", "*.yml"],
                             cwd=_REPO, capture_output=True, text=True, check=False).stdout
        assert "=1" not in out and "=true" not in out.lower()
