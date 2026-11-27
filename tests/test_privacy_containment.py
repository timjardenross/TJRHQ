"""Privacy containment R1-R8: personal health data is processed locally unless the Captain opts in.

Every test counts outbound calls so "nothing left the machine" is asserted, not assumed."""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest import mock

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "platform-runtime"))

from core.llm import provider_chain as pc
from core.security import personal_data_policy as pol

PERSONAL = "Wellness context: sleep=5.5h (CPAP ✗), nervous_system=activated, energy=low"
PUBLIC = "New review finds mindfulness reduces chronic pain; CPAP therapy trial results published"


@pytest.fixture(autouse=True)
def _workload_authorised(monkeypatch):
    """These tests exercise behaviour behind workload authorisation (screening, fallback, parsing)."""
    from core.security import personal_data_policy

    class _Every(frozenset):
        def __contains__(self, item):
            return True

    monkeypatch.setattr(personal_data_policy, "AUTHORISED_HOSTED_WORKLOADS", _Every())


@pytest.fixture(autouse=True)
def _closed(monkeypatch):
    monkeypatch.delenv(pol.FLAG, raising=False)
    monkeypatch.delenv("OLLAMA_CLOUD_DISABLED", raising=False)


def _optin(monkeypatch):
    monkeypatch.setenv(pol.FLAG, "1")


class TestDetectorAndFlag:
    @pytest.mark.parametrize("text", [PERSONAL, "pain_score: 6", "Recovery confidence: 40%", "my sleep was bad",
                                      "Captain's pain is worse today", "capacity_state=orange", "risk_flags: poor sleep"])
    def test_personal_forms_detected(self, text):
        assert pol.contains_personal_health(text)

    @pytest.mark.parametrize("text", [PUBLIC, "Trial of CPAP in sleep apnoea", "Burnout in child protection workers",
                                      "APRA operational resilience standard CPS 230", "Telco outage complaints surge"])
    def test_public_health_and_business_text_not_blocked(self, text):
        assert pol.contains_personal_health(text) == []

    @pytest.mark.parametrize("v,expected", [("1", True), ("true", True), ("ON", True), (" yes ", True),
                                            ("", False), ("0", False), ("false", False), ("maybe", False), ("2", False)])
    def test_flag_is_closed_unless_explicit(self, monkeypatch, v, expected):
        monkeypatch.setenv(pol.FLAG, v)
        assert pol.external_ai_allowed() is expected

    def test_assert_blocks_personal_and_passes_public(self):
        with pytest.raises(pol.PersonalDataBlockedError):
            pol.assert_may_leave_host(PERSONAL, route="x")
        pol.assert_may_leave_host(PUBLIC)

    def test_opt_in_allows(self, monkeypatch):
        _optin(monkeypatch)
        pol.assert_may_leave_host(PERSONAL)


class TestChokePointProviderChain:                       # R6 (covers router/guarded Gemini+Mistral callers)
    def test_guard_blocks_personal_before_any_other_work(self):
        with mock.patch.object(pc, "check_input_rail") as rail, mock.patch.object(pc, "redact_pii") as red:
            with pytest.raises(pol.PersonalDataBlockedError):
                pc._guard_outbound("sys", PERSONAL)
            rail.assert_not_called()
            red.assert_not_called()

    def test_call_gemini_and_mistral_never_open_a_connection_for_personal_text(self):
        with mock.patch.object(pc.urllib.request, "urlopen") as net:
            for fn, kw in ((pc.call_gemini, {"api_key": "k"}), (pc.call_mistral, {"api_key": "k"})):
                with pytest.raises(pol.PersonalDataBlockedError):
                    fn("sys", PERSONAL, **kw)
            net.assert_not_called()

    def test_public_text_still_reaches_the_guard(self):
        with mock.patch.object(pc, "_guard_lock"), mock.patch.object(pc, "check_input_rail") as rail, \
             mock.patch.object(pc, "redact_pii", return_value=SimpleNamespace(
                 redacted_text="s" + pc._PART_BOUNDARY + "p")):
            assert pc._guard_outbound("s", "p") == ("s", "p")
            rail.assert_called_once()

    def test_opt_in_lets_personal_text_to_the_guard(self, monkeypatch):
        _optin(monkeypatch)
        with mock.patch.object(pc, "_guard_lock"), mock.patch.object(pc, "check_input_rail"), \
             mock.patch.object(pc, "redact_pii", return_value=SimpleNamespace(
                 redacted_text="s" + pc._PART_BOUNDARY + "p")):
            assert pc._guard_outbound("s", PERSONAL) == ("s", "p")

    def test_cloud_tagged_ollama_blocked_for_personal_but_local_tag_is_not(self):
        with mock.patch.object(pc.urllib.request, "urlopen") as net:
            with pytest.raises(pol.PersonalDataBlockedError):
                pc.call_ollama("s", PERSONAL, base_url="http://localhost:11434", model="glm-5.2:cloud")
            net.assert_not_called()


class TestXoChatAndConsolidation:                        # R1, R3
    @pytest.fixture
    def tl(self):
        import telegram_bots.llm as tl
        return tl

    def test_personal_route_never_calls_cloud_even_when_cloud_first(self, tl):
        with mock.patch.object(tl, "_call_cloud") as cloud, mock.patch.object(tl, "_call_router", return_value="local") as r:
            assert tl.generate("hi", "sys", cloud_first=True, personal=True) == "local"
            cloud.assert_not_called()
            assert r.call_args.kwargs["timeout"] == tl._personal_router_timeout()

    def test_local_router_down_gives_none_not_cloud(self, tl):
        with mock.patch.object(tl, "_call_cloud") as cloud, mock.patch.object(tl, "_call_router", return_value=None):
            assert tl.generate("hi", "sys", cloud_first=True, personal=True) is None
            cloud.assert_not_called()

    def test_unmarked_route_with_personal_content_is_treated_as_personal(self, tl):
        with mock.patch.object(tl, "_call_cloud") as cloud, mock.patch.object(tl, "_call_router", return_value=None):
            assert tl.generate("how am I", PERSONAL, cloud_first=True) is None
            cloud.assert_not_called()

    def test_direct_cloud_call_refuses_personal_content_without_a_connection(self, tl):
        with mock.patch.object(tl.urllib.request, "urlopen") as net:
            assert tl._call_cloud(PERSONAL, "sys") is None
            net.assert_not_called()

    def test_public_unmarked_route_behaviour_unchanged(self, tl):
        with mock.patch.object(tl, "_call_cloud", return_value="cloud") as cloud, \
             mock.patch.object(tl, "_call_router", return_value=None):
            assert tl.generate("summarise this news", "sys", cloud_first=True) == "cloud"
            cloud.assert_called_once()

    def test_opt_in_restores_cloud_first(self, tl, monkeypatch):
        _optin(monkeypatch)
        with mock.patch.object(tl, "_call_cloud", return_value="cloud") as cloud, mock.patch.object(tl, "_call_router"):
            assert tl.generate("hi", "sys", cloud_first=True, personal=True) == "cloud"
            cloud.assert_called_once()

    def test_xo_chat_and_nightly_consolidation_mark_their_routes_personal(self):
        xo = (_REPO / "telegram-bots" / "xo" / "app.py").read_text()
        assert re.search(r"generate_async\(text, _xo_system_prompt\([^)]*\), cloud_first=True, personal=True\)", xo)
        nc = (_REPO / "scripts" / "memory" / "nightly_consolidation.py").read_text()
        assert "generate_async(transcript, _DISTILL_SYSTEM_PROMPT, personal=True)" in nc


class TestDebriefEngine:                                  # R4
    @pytest.fixture
    def de(self):
        spec = importlib.util.spec_from_file_location("debrief_engine_t", _REPO / "telegram-bots" / "xo" / "debrief_engine.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def _count(self, de, ollama):
        calls = {"gemini": 0, "mistral": 0, "ollama": 0}

        def mk(n, r):
            def f(*a, **k):
                calls[n] += 1
                if isinstance(r, Exception):
                    raise r
                return SimpleNamespace(text=r)
            return f
        de.call_gemini, de.call_mistral, de.call_ollama = mk("gemini", "G"), mk("mistral", "M"), mk("ollama", ollama)
        return calls

    def test_local_only_by_default(self, de):
        calls = self._count(de, "local")
        assert de._call_provider_chain("s", "p") == "local"
        assert calls == {"gemini": 0, "mistral": 0, "ollama": 1}

    def test_local_down_returns_none_for_the_deterministic_fallback_question(self, de):
        calls = self._count(de, RuntimeError("down"))
        assert de._call_provider_chain("s", "p") is None
        assert calls["gemini"] == calls["mistral"] == 0

    def test_opt_in_restores_chain(self, de, monkeypatch):
        _optin(monkeypatch)
        calls = self._count(de, "local")
        assert de._call_provider_chain("s", "p") == "G"
        assert calls["gemini"] == 1


class TestCorrelationSynthesis:                           # R2
    DATA = MappingProxyType({"status": "ok", "correlations": [{"x": 1}], "data_quality": {}})

    def _run(self):
        from intelligence.brief import correlation_synthesis as cs
        prov = mock.MagicMock()
        prov.generate.return_value = (None, None)
        cs.synthesize_correlation_insights(dict(self.DATA), prov)
        return prov

    def test_local_only_by_default(self):
        prov = self._run()
        assert prov.generate.call_args.kwargs.get("local_only") is True

    def test_opt_in_removes_the_restriction(self, monkeypatch):
        _optin(monkeypatch)
        assert self._run().generate.call_args.kwargs.get("local_only") is False


class TestDirectGemini:                                   # R5
    def test_personal_text_refused_without_a_connection(self, monkeypatch):
        import llm
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        with mock.patch.object(llm.urllib.request, "urlopen") as net:
            ok, msg = llm.ask_gemini_safe("sys", PERSONAL)
            assert ok is False and "local-only" in msg
            net.assert_not_called()

    def test_public_text_not_refused_by_the_policy(self, monkeypatch):
        import llm
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        with mock.patch.object(llm.urllib.request, "urlopen", side_effect=OSError("offline")) as net:
            ok, _ = llm.ask_gemini_safe("sys", PUBLIC)
            assert ok is False and net.called          # reached the network layer => policy did not block it


class TestMorningBriefEmail:                              # R7
    BRIEF = ("<b>📊 MORNING BRIEF</b>\n\nRisks today: outage watch\n\n<b>⚡ CAPACITY TODAY</b>\n  "
             "🟠 Capacity <b>Orange</b> · pain 6\n  Recovery confidence 40%\n\n<b>🛰 TECH OSINT</b>\n  2 items\n")

    def _send(self, text):
        import intelligence.captains_brief as cb
        sent = []
        fake = SimpleNamespace(send_email=lambda to, subj, html: sent.append(html) or True)
        with mock.patch.dict(sys.modules, {"core.notifications.resend_email": fake}):
            cb._email_morning_brief(text)
        return sent

    def test_capacity_block_removed_and_rest_kept(self):
        sent = self._send(self.BRIEF)
        assert len(sent) == 1
        assert "CAPACITY" not in sent[0].upper() and "Recovery confidence" not in sent[0]
        assert "TECH OSINT" in sent[0] and "outage watch" in sent[0]

    def test_email_withheld_if_personal_content_survives_stripping(self):
        assert self._send("<b>Brief</b>\n\nToday sleep=4h and pain_score: 7 noted\n") == []

    def test_clean_brief_unchanged_in_substance(self):
        assert len(self._send("<b>Brief</b>\n\nTech outage watch\n")) == 1


class TestProfileExcerpt:                                 # R8
    def test_health_profile_excerpt_withheld_when_external_ai_permitted(self, monkeypatch):
        _optin(monkeypatch)
        from core.health import narrative_intelligence as ni
        assert ni._load_health_exec_excerpt() == ""

    def test_excerpt_gate_flag(self, monkeypatch):
        assert pol.profile_excerpt_allowed() is True
        _optin(monkeypatch)
        assert pol.profile_excerpt_allowed() is False
