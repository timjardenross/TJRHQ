"""Private or unclassified content never reaches an external provider, under every fallback.

All data is synthetic. Every way out of the process is replaced by a recorder (urlopen, the Mistral
and Gemini SDKs) and a socket guard fails the test on any other connection attempt, so nothing here
can reach a real provider, the model router or Ollama.
"""
from __future__ import annotations

import io
import json
import re
import socket
import sys
import types
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import urlparse

import pytest

_REPO = Path(__file__).resolve().parents[1]
for _p in (_REPO, _REPO / "platform-runtime", _REPO / "platform-runtime" / "lib", _REPO / "tools" / "supabase",
           _REPO / "core" / "coordination"):
    if str(_p) not in sys.path:
        sys.path.append(str(_p))

sys.modules.setdefault("supabase", types.SimpleNamespace(create_client=lambda *a, **k: MagicMock()))

import mistral_agent_client as mac
import research_delegator as rd

from core.inbox import orchestrator
from core.llm import provider_chain
from core.security import personal_data_policy as pdp
from core.security.llm_guardrails import GuardrailsUnavailableError
from intelligence.brief import llm_provider as lp

HEALTH = "SYNTH-HEALTH: my pain is 7/10 and I slept 4h with CPAP."
CAPTURE = "SYNTH-CAPTURE: idea about the shed roof for Mr Example Person"
GOVERNANCE = "SYNTH-GOVERNANCE: decision D-999 to defer the internal programme"
PUBLIC = "SYNTH-PUBLIC: vendor advisory about a router vulnerability, contact Jane Public"
PRIVATE_TEXTS = [HEALTH, CAPTURE, GOVERNANCE]


class Outbound:
    """Records everything that would have left the process, and plays each provider's response."""

    def __init__(self):
        self.external: list[tuple[str, str]] = []
        self.local: list[tuple[str, str]] = []
        self.external_status = 200
        self.local_up = True

    def send(self, destination: str, payload: str):
        self.external.append((destination, payload))
        if self.external_status != 200:
            raise urllib.error.HTTPError(destination, self.external_status, "rejected", {}, io.BytesIO(b"rejected"))

    def urlopen(self, request, timeout=None, **_):
        url = request if isinstance(request, str) else request.full_url
        data = "" if isinstance(request, str) else (request.data or b"").decode()
        if urlparse(url).hostname in ("localhost", "127.0.0.1") and ":8891" not in url:
            self.local.append((url, data))
            if not self.local_up:
                raise urllib.error.URLError("local model down")
            body = {"response": '["local task one"]', "embedding": [0.1], "message": {"content": "{}"}}
        else:
            # The model router is a way off this host (its routes are cloud-backed), so it counts as external.
            self.send(url, data)
            body = {
                "response": "ok", "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "data": [{"index": 0, "embedding": [0.1]}], "message": {"content": "ok"},
            }
        response = io.BytesIO(json.dumps(body).encode())
        response.status = 200
        return response

    def text(self) -> str:
        return "\n".join(f"{d} {p}" for d, p in self.external)


class _Every(frozenset):
    def __contains__(self, item):
        return True


@pytest.fixture(autouse=True)
def authorised(monkeypatch):
    """Most tests exercise the gates behind authorisation, so they run as if the workload were authorised.
    The default (nothing authorised) is tested separately below."""
    monkeypatch.setattr(pdp, "AUTHORISED_HOSTED_WORKLOADS", _Every())


@pytest.fixture(autouse=True)
def out(monkeypatch, tmp_path):
    recorder = Outbound()

    def refuse(*args, **kwargs):
        raise AssertionError("socket guard: unexpected network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(urllib.request, "urlopen", recorder.urlopen)

    class FakeMistral:
        def __init__(self, **_):
            def start(**kwargs):
                recorder.send("mistral-sdk", json.dumps(kwargs["inputs"]))
                entry = types.SimpleNamespace(role="assistant", content="ok")
                return types.SimpleNamespace(outputs=[entry])

            self.beta = types.SimpleNamespace(conversations=types.SimpleNamespace(start=start))

    monkeypatch.setitem(sys.modules, "mistralai", types.SimpleNamespace(Mistral=FakeMistral))

    class FakeModel:
        def __init__(self, name):
            self.name = name

        def generate_content(self, prompt, **_):
            recorder.send(f"gemini-sdk:{self.name}", prompt)
            return types.SimpleNamespace(text="ok", usage_metadata=None, parts=[])

    genai = types.ModuleType("google.generativeai")
    genai.configure = lambda **_: None
    genai.GenerativeModel = FakeModel
    genai.types = types.SimpleNamespace(GenerationConfig=lambda **_: None)
    google = sys.modules.get("google") or types.ModuleType("google")
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setattr(google, "generativeai", genai, raising=False)
    monkeypatch.setitem(sys.modules, "google.generativeai", genai)

    # The existing guard, stubbed at its two entry points: redaction replaces the synthetic names.
    monkeypatch.setattr(provider_chain, "check_input_rail", lambda text: None)
    monkeypatch.setattr(provider_chain, "check_output_rail", lambda text: None)
    monkeypatch.setattr(
        provider_chain, "redact_pii",
        lambda text: types.SimpleNamespace(redacted_text=re.sub(r"(Jane Public|Example Person)", "<PERSON>", text)))
    monkeypatch.setenv("LLM_PROVIDER_CHAIN_GUARD_LOCK", str(tmp_path / "guard.lock"))

    # Every provider is fully configured: only the policy stands between the text and the provider.
    monkeypatch.delenv("HEALTH_LLM_EXTERNAL_ALLOWED", raising=False)
    for name in ("MISTRAL_API_KEY", "GEMINI_API_KEY", "OLLAMA_API_KEY", "GLM_API_KEY",
                 "MISTRAL_RESEARCH_AGENT_ID", "MISTRAL_BRIEFING_AGENT_ID"):
        monkeypatch.setenv(name, "synthetic")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    for name in ("MISTRAL_API_KEY", "GEMINI_API_KEY", "MISTRAL_RESEARCH_AGENT_ID", "MISTRAL_BRIEFING_AGENT_ID",
                 "MISTRAL_QA_AGENT_ID", "MISTRAL_CHALLENGE_AGENT_ID", "MISTRAL_TAO_AGENT_ID",
                 "MISTRAL_DECOMPOSITION_AGENT_ID"):
        monkeypatch.setattr(lp, name, "synthetic")
    monkeypatch.setattr(lp, "OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr(lp, "OLLAMA_MODEL", "qwen3:8b")
    monkeypatch.setattr(lp, "MODEL_ROUTER_URL", "http://localhost:8891")
    rd._mission_gemini_quotas.clear()
    return recorder


def _guard_down(monkeypatch):
    def down(*_):
        raise GuardrailsUnavailableError("synthetic: guard unavailable")

    monkeypatch.setattr(provider_chain, "check_input_rail", down)


def _research(monkeypatch, text: str) -> list[dict]:
    """Run the captured-item research job end to end; return the row updates it wrote."""
    from core.coordination import research_orchestration as ro

    monkeypatch.setattr(ro, "_daily_mission_cap_reached", lambda: (False, 0, 30))
    monkeypatch.setattr(ro.ResearchMetricsCollector, "finalize_and_store", lambda self: "")
    db = MagicMock()
    monkeypatch.setattr(orchestrator, "_db", db)
    orchestrator._run_research("synthetic-id", {"title": "note", "raw_text": text})
    return [c.args[2] for c in db.update.call_args_list]


# ── 1, 2, 5, 6: captured notes through the research chain ─────────────────────

@pytest.mark.parametrize("text", [HEALTH, CAPTURE, GOVERNANCE])
@pytest.mark.parametrize("local_up", [True, False])
def test_captured_item_research_never_leaves_the_host(monkeypatch, out, text, local_up):
    out.local_up = local_up
    updates = _research(monkeypatch, text)
    assert out.external == []
    assert out.local, "the local model is the only provider tried"
    assert updates[-1]["research_status"] == ("completed" if local_up else "pending")
    assert all(u.get("research_status") != "failed" for u in updates), "pending work is preserved"


def test_blocked_research_is_visible(monkeypatch, out, caplog):
    out.local_up = False
    _research(monkeypatch, CAPTURE)
    assert "left pending" in caplog.text and "private_or_unclassified" in caplog.text
    assert "SYNTH-CAPTURE" not in caplog.text, "captured text is not written to the log"


@pytest.mark.parametrize("claim", [False, None, "yes", 1, "public"])
def test_anything_but_an_explicit_true_is_private(out, claim):
    out.local_up = False
    result = rd.delegate_research_task(CAPTURE, public_source=claim)
    assert result.status == "error" and result.provider_attempted == ["ollama"]
    assert mac.call_agent("execute", mac.AGENT_RESEARCH, CAPTURE, public_source=claim) is None
    assert rd.call_gemini_2_5_flash_lite_research(CAPTURE, public_source=claim).status == "blocked"
    assert rd.call_gemini_2_flash_research(CAPTURE, public_source=claim).status == "blocked"
    assert rd.call_legacy_research_routing(CAPTURE).status == "blocked"
    assert out.external == []


def test_a_non_local_ollama_target_is_not_a_local_fallback(monkeypatch, out):
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://ollama.example")
    assert rd.delegate_research_task(CAPTURE).status == "error"
    _research(monkeypatch, CAPTURE)
    assert out.external == []


def test_adaptive_reordering_cannot_reintroduce_external_providers(monkeypatch, out):
    ranked = [types.SimpleNamespace(provider_name=n) for n in ("gemini", "mistral_agent", "ollama")]
    monkeypatch.setattr(rd, "adaptive_routing_service",
                        types.SimpleNamespace(get_routing_order=lambda: ranked), raising=False)
    out.local_up = False
    assert rd.delegate_research_task(CAPTURE).provider_attempted == ["ollama"]
    assert out.external == []


# ── 4, 5, 7, 8: public material may use the cloud, screened ──────────────────

def test_public_research_uses_the_cloud_only_after_redaction(out):
    result = rd.delegate_research_task(PUBLIC, public_source=True)
    assert result.status == "success" and result.provider == "mistral_agent"
    assert "SYNTH-PUBLIC" in out.text() and "<PERSON>" in out.text() and "Jane Public" not in out.text()


@pytest.mark.parametrize("status", [401, 402])
def test_provider_rejection_then_cloud_fallback_stays_screened(out, status):
    out.external_status = status
    out.local_up = False
    rd.delegate_research_task(PUBLIC, public_source=True)
    destinations = {d.split(":")[0] for d, _ in out.external}
    assert {"mistral-sdk", "gemini-sdk"} <= destinations, "fallback was exercised"
    assert "Jane Public" not in out.text()


def test_provider_rejection_of_private_work_never_happens_because_nothing_is_sent(out):
    out.external_status = 402
    out.local_up = False
    rd.delegate_research_task(CAPTURE)
    assert out.external == []


def test_screening_failure_sends_nothing_even_for_public_material(monkeypatch, out):
    _guard_down(monkeypatch)
    out.local_up = False
    result = rd.delegate_research_task(PUBLIC, public_source=True)
    assert result.status == "error" and out.external == []


def test_health_content_is_blocked_even_if_declared_public(out):
    out.local_up = False
    rd.delegate_research_task(HEALTH, public_source=True)
    assert out.external == []


# ── Hosted brief agents and the shared chain ─────────────────────────────────

def test_hosted_brief_agents_receive_only_screened_text(out):
    p = lp.LLMProvider()
    assert p.check_brief_quality(PUBLIC) == "ok" and p.check_risk_rating(PUBLIC, "high") == "ok"
    assert len(out.external) == 2 and "Jane Public" not in out.text() and "<PERSON>" in out.text()


def test_hosted_brief_agents_fail_closed_without_screening(monkeypatch, out, caplog):
    _guard_down(monkeypatch)
    p = lp.LLMProvider()
    assert p.check_brief_quality(PUBLIC) is None and p.check_risk_rating(PUBLIC, "high") is None
    with pytest.raises(GuardrailsUnavailableError):
        p._mistral_pipeline(PUBLIC)
    assert out.external == []
    assert "check failed" in caplog.text


def test_agent_tool_call_fallback_to_chat_completions_is_screened(monkeypatch, out):
    p = lp.LLMProvider()
    monkeypatch.setattr(p, "_extract_text", lambda response: "")  # agent returns no final message
    p.check_brief_quality(PUBLIC)
    assert any("chat/completions" in d for d, _ in out.external)
    assert "Jane Public" not in out.text()


@pytest.mark.parametrize("text", [HEALTH, CAPTURE])
def test_local_only_generation_has_no_external_fallback(out, text):
    out.local_up = False
    assert lp.LLMProvider().generate(text, local_only=True) == (None, None)
    assert out.external == []


def test_local_only_refuses_a_cloud_tagged_model(monkeypatch, out):
    monkeypatch.setattr(lp, "OLLAMA_MODEL", "synthetic:cloud")
    assert lp.LLMProvider().generate(CAPTURE, local_only=True) == (None, None)
    assert out.external == [] and out.local == []


def test_cloud_fallback_chain_for_public_material_with_screening_down(monkeypatch, out):
    _guard_down(monkeypatch)
    monkeypatch.setattr(lp.LLMProvider, "_model_router", lambda self, prompt: None)  # router has its own guard
    out.local_up = False
    assert lp.LLMProvider().generate(PUBLIC) == (None, None)
    assert out.external == []


@pytest.mark.parametrize("base,model", [("http://localhost:11434", "synthetic:cloud"),
                                        ("https://ollama.example", "plain-model")])
def test_cloud_ollama_calls_are_screened_or_refused(monkeypatch, out, base, model):
    with pytest.raises(pdp.ExternalEgressBlockedError):
        provider_chain.call_ollama("", CAPTURE, base_url=base, model=model, local_only=True)
    assert out.external == [] and out.local == []
    _guard_down(monkeypatch)
    with pytest.raises(GuardrailsUnavailableError):
        provider_chain.call_ollama("", PUBLIC, base_url=base, model=model)
    assert out.external == [] and out.local == []


# ── Internal records, personal tasks, drafts ─────────────────────────────────

@pytest.mark.parametrize("local_up", [True, False])
def test_internal_platform_summary_stays_local(out, local_up):
    from core.platform import infra_narrative

    out.local_up = local_up
    infra_narrative._generate(GOVERNANCE)
    assert out.external == [] and out.local


@pytest.mark.parametrize("local_up", [True, False])
def test_personal_task_decomposition_stays_local(out, local_up):
    from intelligence.adhd import task_decomposition

    out.local_up = local_up
    task_decomposition.TaskDecomposer().decompose(CAPTURE)
    assert out.external == [] and out.local


@pytest.mark.parametrize("local_up", [True, False])
def test_content_drafting_stays_local_and_leaves_the_item_queued(monkeypatch, out, local_up):
    from core.content import draft_worker

    out.local_up = local_up
    patched = []
    monkeypatch.setattr(draft_worker, "_sb_patch", lambda *a: patched.append(a))
    monkeypatch.setattr(draft_worker, "run_research", lambda item: GOVERNANCE)
    done = draft_worker.process_item({"id": "synthetic-id", "title": CAPTURE, "notes": CAPTURE})
    assert done is local_up and out.external == []
    assert bool(patched) is local_up, "nothing is written for an item that could not be drafted"


# ── Captured-item classification ─────────────────────────────────────────────

@pytest.mark.parametrize("local_up", [True, False])
@pytest.mark.parametrize("text", [HEALTH, CAPTURE])
def test_capture_classification_stays_local_and_queued(monkeypatch, out, local_up, text):
    from core.capture import enrichment_worker as ew

    monkeypatch.setattr(ew, "OLLAMA_BASE", "http://localhost:11434")
    monkeypatch.setattr(ew, "OLLAMA_MODEL", "qwen3:8b")
    out.local_up = local_up
    updates = []
    monkeypatch.setattr(ew, "_sb_patch", lambda table, match, update: updates.append(update))
    ew.enrich_item({"id": "synthetic-id", "raw_text": text}, dry_run=False)
    assert out.external == []
    assert all(u.get("ai_enrichment_status") != "failed" for u in updates)


@pytest.mark.parametrize("base,model", [("https://ollama.com", "qwen3:8b"),
                                        ("http://localhost:11434", "synthetic:cloud")])
def test_capture_classification_refuses_a_cloud_target(monkeypatch, out, base, model):
    from core.capture import enrichment_worker as ew

    monkeypatch.setattr(ew, "OLLAMA_BASE", base)
    monkeypatch.setattr(ew, "OLLAMA_MODEL", model)
    with pytest.raises(pdp.ExternalEgressBlockedError):
        ew._call_llm(CAPTURE)
    assert out.external == [] and out.local == []


# ── 9: embeddings ────────────────────────────────────────────────────────────

# The two transport methods are called directly: tests/conftest.py replaces EmbeddingClient.create for
# the whole session once any advisory test has run.
def _embedding_module(monkeypatch, provider="mistral"):
    from _local_import_supabase import import_sibling

    monkeypatch.setenv("EMBEDDING_PROVIDER", provider)
    return import_sibling("embedding_client")


@pytest.mark.parametrize("text", PRIVATE_TEXTS)
def test_private_text_is_never_sent_for_embedding(monkeypatch, out, text):
    ec = _embedding_module(monkeypatch)
    with pytest.raises(ec.EmbeddingError, match="blocked"):
        ec.EmbeddingClient()._create_openai([text])
    assert out.external == []


def test_non_local_ollama_embedding_is_refused(monkeypatch, out):
    ec = _embedding_module(monkeypatch, "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://ollama.example")
    with pytest.raises(ec.EmbeddingError, match="not local"):
        ec.EmbeddingClient()._create_ollama(CAPTURE)
    assert out.external == []


def test_public_embedding_is_screened_and_fails_closed(monkeypatch, out):
    ec = _embedding_module(monkeypatch)
    ec.EmbeddingClient(public_source=True)._create_openai([PUBLIC])
    assert "<PERSON>" in out.text() and "Jane Public" not in out.text()
    out.external.clear()
    _guard_down(monkeypatch)
    with pytest.raises(ec.EmbeddingError):
        ec.EmbeddingClient(public_source=True)._create_openai([PUBLIC])
    assert out.external == []


def test_episodic_recall_falls_back_without_sending(monkeypatch, out, caplog):
    from core.platform import episodic_memory

    monkeypatch.setenv("EMBEDDING_PROVIDER", "mistral")
    db = MagicMock()
    monkeypatch.setattr(episodic_memory, "_supabase_raw", lambda: db)
    episodic_memory.recall_similar(GOVERNANCE)
    assert out.external == []
    db.rpc.assert_not_called()
    assert "embedding generation failed" in caplog.text


def test_advisory_retrieval_uses_keyword_search_when_embedding_is_blocked(monkeypatch, out):
    import specialist_aware_retrieval as sar

    def blocked(*_):
        raise sar.EmbeddingError("Hosted embedding blocked")

    monkeypatch.setattr(sar, "semantic_results", blocked)
    monkeypatch.setattr(sar, "keyword_results", lambda client, q, doc_type, limit: [{"rank": 1, "title": doc_type}])
    rows, mode, _ = sar.retrieve_allowed_results(MagicMock(), GOVERNANCE, ["adr", "lesson"], 5, True, 0.5)
    assert [r["title"] for r in rows] == ["adr", "lesson"] and mode.startswith("keyword")
    assert out.external == []


# ── Hosted memory backends ───────────────────────────────────────────────────

def test_hosted_memory_backends_are_refused(monkeypatch, out):
    import asyncio

    from core.platform import memory_graph, unified_memory

    # Not imported for real: graphiti_core loads the nearest .env file into the process on import.
    nodes = types.SimpleNamespace(EpisodeType=types.SimpleNamespace(text="text"))
    monkeypatch.setitem(sys.modules, "graphiti_core", types.ModuleType("graphiti_core"))
    monkeypatch.setitem(sys.modules, "graphiti_core.nodes", nodes)

    with pytest.raises(pdp.ExternalEgressBlockedError):
        asyncio.run(memory_graph._build_graphiti())
    assert asyncio.run(memory_graph.add_fact(GOVERNANCE)) is False
    assert unified_memory._Mem0Backend()._ensure_ready() is False
    assert out.external == []


def test_turns_stay_unconsolidated_when_the_memory_backend_is_blocked(monkeypatch, out):
    import asyncio

    from core.platform import unified_memory
    from scripts.memory import nightly_consolidation as nc

    async def distilled(_):
        return [CAPTURE]

    monkeypatch.setattr(nc, "_distill", distilled)
    monkeypatch.setattr(unified_memory, "remember", lambda *a, **k: {})
    db = MagicMock()
    chain = db.table.return_value.select.return_value.is_.return_value
    chain.order.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"id": 1, "chat_id": 1, "role": "user", "text": CAPTURE, "created_at": "2000-01-01"}]
    result = asyncio.run(nc.consolidate_conversation_turns(db))
    assert result["chats_failed"] == 1 and out.external == []
    db.table.return_value.update.assert_not_called()


# ── No new way out without review ────────────────────────────────────────────

_MARKERS = re.compile(
    r"api\.mistral\.ai|generativelanguage\.googleapis\.com|ollama\.com|api\.openai\.com|api\.anthropic\.com"
    r"|from mistralai import|import google\.generativeai|from google import genai|\blitellm\.completion")

# Reviewed 27 Nov 2026. Adding a file here is a statement that its egress was reviewed.
_REVIEWED = {
    # screened in this file or via core.llm.provider_chain
    "core/llm/provider_chain.py", "intelligence/brief/llm_provider.py", "tools/supabase/embedding_client.py",
    "platform-runtime/lib/mistral_agent_client.py", "platform-runtime/lib/research_delegator.py",
    "core/engineering/providers/glm.py", "core/engineering/providers/gemini.py",
    "core/engineering/providers/kimi.py", "core/engineering/providers/qwen.py",
    "core/engineering/providers/mistral_batch.py", "core/engineering/providers/mistral_batch_api.py",
    # the model router (guards its own cloud dispatch)
    "core/model-router/app.py",
    # public-source or off by default; own controls
    "telegram-bots/llm.py",
    # NOT remediated: manual tools or code with no running caller found
    "platform-runtime/llm.py", "platform-runtime/commands/mission_brief.py",
    "tools/hierarchy/classify_missions.py", "tools/a5_catalogue/gemini_content_pass.py",
    "tools/supabase/commander_synthesis.py",
    "services/revs-content-agents/src/integrations/gemini_client.py",
}


def test_no_unreviewed_direct_provider_use():
    found = set()
    for path in _REPO.rglob("*.py"):
        rel = path.relative_to(_REPO).as_posix()
        if re.search(r"(^|/)(tests?|node_modules|\.venv[^/]*|platform_runtime)/|(^|/)test_[^/]*\.py$", rel):
            continue
        if _MARKERS.search(path.read_text(encoding="utf-8", errors="ignore")):
            found.add(rel)
    assert found - _REVIEWED == set(), "new direct provider use: route it through core.llm.provider_chain"


# ── authorisation: with nothing authorised (the shipped state), screened public text is not enough ────────────

@pytest.fixture
def nothing_authorised(monkeypatch):
    monkeypatch.setattr(pdp, "AUTHORISED_HOSTED_WORKLOADS", frozenset())


def test_shipped_allowlist_is_empty():
    import importlib.util
    spec = importlib.util.spec_from_file_location("pdp_shipped", pdp.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.AUTHORISED_HOSTED_WORKLOADS == frozenset()


def test_a_public_declaration_alone_is_refused(nothing_authorised):
    with pytest.raises(pdp.ExternalEgressBlockedError):
        pdp.assert_external_eligible(True, route="anything")


def test_brief_stays_local_and_sends_nothing_without_authorisation(nothing_authorised, out):
    llm = lp.LLMProvider()
    llm.generate(PUBLIC)
    llm.generate(PUBLIC, use_mistral_pipeline=False)
    assert llm.check_brief_quality(PUBLIC) is None and llm.check_risk_rating(PUBLIC, "low") is None
    for call in (llm._model_router, llm._gemini, llm._mistral, llm._mistral_pipeline):
        with pytest.raises(pdp.ExternalEgressBlockedError):
            call(PUBLIC)
    assert out.external == []


def test_shared_provider_chain_refuses_without_authorisation(nothing_authorised, out):
    for call in (provider_chain.call_gemini, provider_chain.call_mistral):
        with pytest.raises(pdp.ExternalEgressBlockedError):
            call("", PUBLIC, api_key="synthetic")
    with pytest.raises(pdp.ExternalEgressBlockedError):
        provider_chain.screen_outbound("", PUBLIC)
    assert out.external == []
