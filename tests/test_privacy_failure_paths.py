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
