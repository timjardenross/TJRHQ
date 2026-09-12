#!/usr/bin/env python3
"""
core/quality/ragas_eval.py — ragas RAG-metric evaluation harness.

USS-TJR-MSN-0366 Stream 4 ("Stage 2A: New Open-Source Tool Adoption"). Instruments
the RAG pipeline with ragas (faithfulness, context precision, context recall) before
it goes live — the mission registry lists this pipeline as having zero live callers.

Honesty about what "the RAG pipeline" actually is in this codebase, as of this
mission: tools/supabase/retrieve_knowledge.py is a real, working RETRIEVAL module
(keyword search via Meilisearch with Supabase RPC/ilike fallbacks, plus a separate
--semantic vector-similarity path) with its own access-control and logging. But
nothing in the repo combines that retrieval output with an LLM call to produce a
generated answer — grep for callers of retrieve()/semantic_results()/keyword_results()
turns up only tests/supabase_retrieval scripts and this module. "The RAG pipeline" is
retrieval scaffolding, not a wired retrieval+generation loop. This module is, as far
as a repo-wide grep can tell, the first thing in the repo that actually performs
retrieval -> generation -> RAG-metric scoring end to end — built for this mission
specifically so there is something real to gate on before a live caller exists.
See knowledge/missions/RAGAS-RAG-EVAL-20260912-knowledge-record.md for the full
write-up, including the sandbox limitations below.

Conventions kept identical to this platform's existing eval wiring, on purpose:
  - Judge model: a LangChain-compatible LLM backed by this platform's own Model
    Router (core/model-router/app.py, http://127.0.0.1:8891), calling its
    "escalate" task — the exact same router + task deepeval's own judge
    (platform-runtime/lib/quality_scoring_service.py::_ModelRouterJudge) already
    uses. No new API key, no cloud dependency, matches the existing pattern instead
    of inventing a second one. See ModelRouterLLM below.
  - Isolation: ragas is NOT declared in platform-runtime/requirements.txt. It pulls
    ~90 packages (the full langchain stack + datasets/pyarrow/huggingface_hub) that
    the live serving path has no other use for, and pins a langchain-community
    version ragas itself is incompatible with unless corrected (see
    core/quality/requirements-ragas.txt for the confirmed, real conflict). Installed
    into its own venv, same pattern as garak (core/quality/requirements-garak.txt,
    core/quality/garak_gate.py):
        python3 -m venv platform-runtime/.venv-ragas
        platform-runtime/.venv-ragas/bin/pip install -r core/quality/requirements-ragas.txt
  - Reports: saved under reports/ragas/, one timestamped JSON + Markdown pair per run
    (same as reports/garak/).
  - Scope: this module only wires ragas's RAG-specific metrics (faithfulness, context
    precision, context recall). It deliberately does NOT duplicate
    quality_scoring_service.py's deepeval-based score_output() (general
    hallucination scoring for arbitrary LLM outputs, not RAG-context-aware) — the two
    are complementary, not overlapping.

SANDBOX LIMITATION (confirmed, not assumed): this module was built and run in an
environment with no reachable Supabase project (no SUPABASE_URL/SUPABASE_*_KEY set),
no reachable Model Router (http://127.0.0.1:8891 refuses the connection), no local
Ollama, no OpenAI/Anthropic API key, and an egress policy that blocks
huggingface.co (so no local HF model could be pulled either) — see the knowledge
record for the exact checks run. Every "real" path below (live Supabase retrieval,
live Model Router generation, Model-Router-backed ragas judge) is implemented and is
what this module uses whenever those services ARE reachable (e.g. in a real deploy).
When they are not reachable, each stage falls back to a clearly-labelled, real
(non-random, non-placeholder) substitute:
  - Retrieval falls back to two verbatim excerpts of actual repository documentation
    about this very tool (retrieve_knowledge.py's own module docstring, and the
    OSS-Gap-Solutions GAP 4 writeup that flagged it as uncalled) — real text, just not
    fetched via the live retrieval RPC.
  - Generation falls back to a hand-written grounded answer plus a deliberately
    hallucinated variant (one fabricated, unsupported sentence appended) — used to
    prove faithfulness actually discriminates grounded vs. ungrounded output, not
    just to have *an* answer to score.
  - The judge falls back to OfflineLexicalOverlapJudge (below): a deterministic,
    input-dependent lexical-overlap heuristic that answers ragas's own structured
    judge prompts (parsed from the real prompt text ragas sends) instead of an LLM.
    This is NOT a semantic/entailment judge and must never be used as a real
    go/no-go gate — it exists only to prove ragas's real scoring/aggregation code
    (statement decomposition, verdict counting, precision/recall arithmetic) runs
    end-to-end against real, input-dependent data when no real LLM is reachable.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import logging
import os
import re
import sys
import urllib.error
import urllib.request
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ragas 0.4.x's own recommended replacement for the LLM-wrapper API used below
# (ragas.metrics.collections + llm_factory) is built around an OpenAI-client-shaped
# InstructorBaseRagasLLM — it expects something that looks like `OpenAI(api_key=...)`
# / `AsyncOpenAI`, not an arbitrary REST endpoint. This platform's Model Router has no
# OpenAI-compatible /v1/chat/completions surface (see core/quality/garak_gate.py's own
# note on this — every route speaks the router's own {"prompt"} -> {"response"}
# contract), so the older LangchainLLMWrapper + a custom langchain_core LLM subclass
# (ModelRouterLLM below) is the one that actually fits this platform, not a stylistic
# preference. Still fully functional in 0.4.3, just deprecated for v1.0 — silencing
# the warning here rather than at every call site.
warnings.filterwarnings("ignore", category=DeprecationWarning, message=r".*[Rr]agas.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, message=r".*LangchainLLMWrapper.*")

logging.basicConfig(level=os.environ.get("RAGAS_EVAL_LOGLEVEL", "INFO"))
log = logging.getLogger("ragas_eval")

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = REPO_ROOT / "reports" / "ragas"

_MODEL_ROUTER_URL = os.environ.get("MODEL_ROUTER_URL", "http://127.0.0.1:8891").rstrip("/")
_MODEL_ROUTER_TIMEOUT = int(os.environ.get("MODEL_ROUTER_TIMEOUT_SECONDS", "300"))
_MODEL_ROUTER_CONNECT_TIMEOUT = 5


# ---------------------------------------------------------------------------
# Module import helper (this repo has no package __init__.py files, and several
# tools/ filenames collide with unrelated modules elsewhere — mirrors
# tools/supabase/_local_import_supabase.py's import_sibling() rather than
# reinventing that fix).
# ---------------------------------------------------------------------------

def _import_repo_module(relative_path: str, unique_key: str):
    cached = sys.modules.get(unique_key)
    if cached is not None:
        return cached
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(unique_key, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique_key] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Model Router connectivity + LangChain-compatible LLM client
# ---------------------------------------------------------------------------

def check_model_router() -> tuple[bool, str]:
    """Return (reachable, message). Never raises. Same shape as
    core/engineering/providers/model_router.py::check_connectivity()."""
    url = f"{_MODEL_ROUTER_URL}/health"
    try:
        with urllib.request.urlopen(url, timeout=_MODEL_ROUTER_CONNECT_TIMEOUT) as resp:  # nosec B310 - url derived from MODEL_ROUTER_URL env var / fixed http://127.0.0.1:8891 constant, not user input - reviewed 2026-09-12
            data = json.loads(resp.read().decode())
        return True, f"Model Router reachable at {_MODEL_ROUTER_URL}: status={data.get('status', 'ok')}"
    except Exception as exc:  # noqa: BLE001 - deliberately broad, this must never raise
        return False, f"Model Router not reachable at {_MODEL_ROUTER_URL}: {exc}"


# Imported lazily (after the .venv-ragas install) so this file can still be read/
# linted without ragas/langchain installed.
from langchain_core.language_models.llms import LLM


class ModelRouterLLM(LLM):
    """LangChain-compatible LLM backed by this platform's Model Router.

    Deliberately mirrors platform-runtime/lib/quality_scoring_service.py's
    _ModelRouterJudge — same router, same "escalate" task (reasoning-capable,
    already availability-guarded with a local fallback in core/model-router/app.py)
    — so ragas's judge and deepeval's judge share one calling convention against
    this platform instead of a second one being invented here. Also used, via
    .invoke(), as the answer-generation model for a real RAG turn: the router has
    no OpenAI-style /v1/chat/completions endpoint (see core/quality/garak_gate.py's
    own note on this), only its own {"prompt": str} -> {"success", "response"}
    contract, so both roles go through the same plain-text call.
    """

    router_url: str = _MODEL_ROUTER_URL
    timeout: int = _MODEL_ROUTER_TIMEOUT

    @property
    def _llm_type(self) -> str:
        return "uss-tjr-model-router"

    def _call(self, prompt: str, stop: list[str] | None = None, run_manager=None, **kwargs: Any) -> str:
        body = json.dumps({"prompt": prompt}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.router_url}/api/model/escalate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310 - self.router_url defaults to MODEL_ROUTER_URL env var / fixed localhost constant, not user input - reviewed 2026-09-12
            data = json.loads(resp.read())
        if not data.get("success"):
            raise RuntimeError(f"model-router escalate call failed: {data}")
        return data.get("response", "")


# ---------------------------------------------------------------------------
# Offline judge: a deterministic, real (non-random) stand-in for the LLM judge,
# used only when no real LLM is reachable. Understands the exact structured
# prompt shapes ragas 0.4.3's legacy Faithfulness / LLMContextPrecisionWithReference
# / LLMContextRecall metrics send (confirmed by instrumenting a probe LLM and
# reading the real prompts+schemas ragas generated, not guessed from docs).
# ---------------------------------------------------------------------------

_SCHEMA_RE = re.compile(r"JSON Schema:\n(\{.*?\})Do not use single quotes", re.DOTALL)
_INPUT_RE = re.compile(r"\ninput: (\{.*\})\nOutput:\s*$", re.DOTALL)
_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "to", "of", "in",
    "on", "for", "and", "or", "not", "it", "this", "that", "with", "as", "by",
    "at", "from", "has", "have", "had", "its", "there", "also", "since", "if",
    "then", "does", "do", "did", "so", "but", "than", "into", "over", "up",
}


def _words(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall((text or "").lower()) if w not in _STOPWORDS}


def _overlap_ratio(statement: str, source: str) -> float:
    """Fraction of statement's (non-stopword) words that also appear in source.
    Crude lexical proxy for "is this statement grounded in this text?" — real
    arithmetic on real input, not a canned number, but NOT semantic entailment."""
    s_words = _words(statement)
    if not s_words:
        return 0.0
    src_words = _words(source)
    return len(s_words & src_words) / len(s_words)


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def _generic_schema_fill(schema: dict, defs: dict | None = None) -> Any:
    """Best-effort minimally-valid filler for a JSON-schema node, used only as a
    last resort for a prompt shape this judge doesn't specifically recognise
    (logged loudly — see OfflineLexicalOverlapJudge._call)."""
    defs = defs if defs is not None else schema.get("$defs", {})

    def fill(node: dict) -> Any:
        if "$ref" in node:
            return fill(defs[node["$ref"].split("/")[-1]])
        t = node.get("type")
        if t == "object" or "properties" in node:
            return {k: fill(v) for k, v in node.get("properties", {}).items()}
        if t == "array":
            return [fill(node["items"])]
        if t == "integer":
            return 0
        if t == "number":
            return 0.0
        if t == "boolean":
            return False
        return "unavailable"

    return fill(schema)


class OfflineLexicalOverlapJudge(LLM):
    """Deterministic stand-in for the ragas LLM judge (see module docstring's
    SANDBOX LIMITATION section for why this exists here). Answers each of ragas's
    structured judge prompts using real lexical overlap between the actual
    statement/context/answer text embedded in that prompt — never a constant —
    so ragas's own downstream aggregation math is exercised for real. Never wire
    this in as a production go/no-go judge; it has no semantic understanding.
    """

    threshold: float = 0.28

    @property
    def _llm_type(self) -> str:
        return "offline-lexical-overlap-judge"

    def _call(self, prompt: str, stop: list[str] | None = None, run_manager=None, **kwargs: Any) -> str:
        schema_match = _SCHEMA_RE.search(prompt)
        schema = json.loads(schema_match.group(1)) if schema_match else {}
        title = schema.get("title")
        input_match = _INPUT_RE.search(prompt)
        payload = json.loads(input_match.group(1)) if input_match else {}

        if title == "StatementGeneratorOutput":
            statements = _split_sentences(payload.get("answer", ""))
            return json.dumps({"statements": statements or [payload.get("answer", "")]})

        if title == "NLIStatementOutput":
            context = payload.get("context", "")
            out = []
            for stmt in payload.get("statements", []):
                ratio = _overlap_ratio(stmt, context)
                out.append(
                    {
                        "statement": stmt,
                        "reason": f"lexical overlap with retrieved context = {ratio:.2f} (threshold {self.threshold})",
                        "verdict": 1 if ratio >= self.threshold else 0,
                    }
                )
            return json.dumps({"statements": out})

        if title == "Verification":
            ratio = _overlap_ratio(payload.get("answer", ""), payload.get("context", ""))
            return json.dumps(
                {
                    "reason": f"lexical overlap of reference answer with this context chunk = {ratio:.2f}",
                    "verdict": 1 if ratio >= self.threshold else 0,
                }
            )

        if title == "ContextRecallClassifications":
            context = payload.get("context", "")
            statements = _split_sentences(payload.get("answer", ""))
            out = []
            for stmt in statements:
                ratio = _overlap_ratio(stmt, context)
                out.append(
                    {
                        "statement": stmt,
                        "reason": f"lexical overlap with retrieved context = {ratio:.2f}",
                        "attributed": 1 if ratio >= self.threshold else 0,
                    }
                )
            return json.dumps({"classifications": out})

        log.warning("[ragas-eval] offline judge saw an unrecognised prompt schema title=%r; using a generic (unscored) fill", title)
        return json.dumps(_generic_schema_fill(schema))


def build_judge_llm():
    """Returns (LangchainLLMWrapper, mode) — mode is 'live-model-router' or
    'offline-lexical-overlap'."""
    from ragas.llms import LangchainLLMWrapper

    reachable, msg = check_model_router()
    if reachable:
        log.info("[ragas-eval] %s — using it as the ragas judge", msg)
        return LangchainLLMWrapper(ModelRouterLLM()), "live-model-router"
    log.warning("[ragas-eval] %s — falling back to OfflineLexicalOverlapJudge (see module docstring)", msg)
    return LangchainLLMWrapper(OfflineLexicalOverlapJudge()), "offline-lexical-overlap"


# ---------------------------------------------------------------------------
# Retrieval: real tools/supabase/retrieve_knowledge.py path, with an honestly
# labelled real-repo-content fallback when Supabase isn't reachable.
# ---------------------------------------------------------------------------

# Verbatim excerpt of tools/supabase/retrieve_knowledge.py's own module docstring.
_FALLBACK_CONTEXT_1 = (
    "Keyword search now routes through Meilisearch (http://localhost:7700) as the "
    "primary path. If Meilisearch is unavailable or returns no hits, the call falls "
    "back automatically to the Supabase keyword_search_documents RPC and then to the "
    "ilike fallback_search — preserving full backward compatibility."
)

# Verbatim (whitespace-normalised) excerpt of knowledge/OSS-Gap-Solutions-2026-08-23.md,
# GAP 4 section.
_FALLBACK_CONTEXT_2 = (
    "GAP 4 — Search fragmented (6 incompatible implementations). 6 separate search "
    "implementations. retrieve_knowledge.py never called. Wave 4 consolidation mission "
    "not assigned. Recommendation: Meilisearch for search consolidation — single "
    "binary, hybrid search, replaces all 6 implementations with one client. Assign "
    "Wave 4 mission to wire retrieve_knowledge.py to Meilisearch."
)

_FALLBACK_CONTEXTS = [_FALLBACK_CONTEXT_1, _FALLBACK_CONTEXT_2]

DEFAULT_QUESTION = (
    "Does retrieve_knowledge.py have a live caller today, and how does its keyword "
    "search actually work?"
)
DEFAULT_REFERENCE = (
    "retrieve_knowledge.py has no live caller — the OSS gap analysis (GAP 4) says it "
    "is never called and recommended wiring it to Meilisearch. Its keyword search now "
    "routes through Meilisearch as the primary path, falling back to the Supabase "
    "keyword_search_documents RPC and then to the ilike fallback_search."
)
_FABRICATED_CLAIM = (
    " This retrieval pipeline has already been deployed as the live answer-generation "
    "path behind the Command Layer chat interface since August 2026."
)


def get_context(question: str, document_type: str | None = None, limit: int = 5) -> tuple[list[str], str]:
    """Real retrieval via tools/supabase/retrieve_knowledge.py's semantic/keyword
    paths against a real Supabase project when one is reachable. Falls back to two
    verbatim excerpts of real repository documentation about this exact tool when
    Supabase isn't reachable (never synthetic text) — see module docstring."""
    try:
        rk = _import_repo_module("tools/supabase/retrieve_knowledge.py", "_ragas_eval__retrieve_knowledge")
        client = rk.SupabaseClient()  # raises SupabaseError if SUPABASE_URL/KEY unset
        try:
            results, _model = rk.semantic_results(client, question, document_type, limit, 0.0)
            chunks = [r.get("snippet") or "" for r in results if r.get("snippet")]
            if chunks:
                return chunks, "live-supabase-semantic"
        except Exception as exc:
            log.warning("[ragas-eval] semantic retrieval failed (%s); trying keyword path", exc)
        results = rk.keyword_results(client, question, document_type, limit)
        chunks = [r.get("snippet") or "" for r in results if r.get("snippet")]
        if chunks:
            return chunks, "live-supabase-keyword"
        log.warning("[ragas-eval] Supabase reachable but returned no chunks; using repo-doc fallback context")
    except Exception as exc:
        log.warning("[ragas-eval] live retrieval unavailable (%s); using repo-doc fallback context", exc)
    return _FALLBACK_CONTEXTS, "fallback-repo-docs"


def _build_rag_prompt(question: str, contexts: list[str]) -> str:
    numbered = "\n".join(f"[{i+1}] {c}" for i, c in enumerate(contexts))
    return (
        "You are the USS TJR knowledge assistant. Answer the question using ONLY the "
        "provided context. Be concise (2-4 sentences). If the context does not answer "
        "the question, say so plainly.\n\n"
        f"Context:\n{numbered}\n\n"
        f"Question: {question}\n\n"
        "Answer:"
    )


_FALLBACK_GROUNDED_ANSWER = (
    "retrieve_knowledge.py is not called by anything live in production. Its keyword "
    "search primarily uses Meilisearch, falling back to the Supabase "
    "keyword_search_documents RPC and then an ilike-based fallback_search if that RPC "
    "fails. This matches GAP 4's recommendation to wire retrieve_knowledge.py to "
    "Meilisearch for search consolidation."
)


def generate_answer(question: str, contexts: list[str]) -> tuple[str, str]:
    """Real generation via the Model Router when reachable; a fixed, honestly
    labelled fixture answer otherwise. Either way the caller also builds a
    deliberately-hallucinated variant from this answer (see main()) to prove
    faithfulness discriminates grounded vs. ungrounded output."""
    reachable, msg = check_model_router()
    if reachable:
        try:
            llm = ModelRouterLLM()
            answer = llm.invoke(_build_rag_prompt(question, contexts))
            answer = (answer or "").strip()
            if answer:
                return answer, "live-model-router"
            log.warning("[ragas-eval] Model Router returned an empty answer; using fixture answer")
        except Exception as exc:
            log.warning("[ragas-eval] Model Router generation failed (%s); using fixture answer", exc)
    else:
        log.warning("[ragas-eval] %s; using fixture answer", msg)
    return _FALLBACK_GROUNDED_ANSWER, "fallback-fixture"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

async def _score_faithfulness(judge, question: str, answer: str, contexts: list[str]) -> dict:
    from ragas.dataset_schema import SingleTurnSample
    from ragas.metrics import Faithfulness

    sample = SingleTurnSample(user_input=question, response=answer, retrieved_contexts=contexts)
    metric = Faithfulness(llm=judge)
    try:
        score = await metric.single_turn_ascore(sample)
        return {"score": score, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"score": None, "error": str(exc)}


async def _score_retrieval_metrics(judge, question: str, contexts: list[str], reference: str) -> dict:
    from ragas.dataset_schema import SingleTurnSample
    from ragas.metrics import LLMContextPrecisionWithReference, LLMContextRecall

    sample = SingleTurnSample(user_input=question, retrieved_contexts=contexts, reference=reference)
    out = {}
    for name, cls in [
        ("context_precision", LLMContextPrecisionWithReference),
        ("context_recall", LLMContextRecall),
    ]:
        metric = cls(llm=judge)
        try:
            out[name] = {"score": await metric.single_turn_ascore(sample), "error": None}
        except Exception as exc:  # noqa: BLE001
            out[name] = {"score": None, "error": str(exc)}
    return out


# ---------------------------------------------------------------------------
# Report writing
# ---------------------------------------------------------------------------

def _write_report(report: dict) -> tuple[Path, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = report["timestamp_compact"]
    json_path = REPORT_DIR / f"{timestamp}.json"
    md_path = REPORT_DIR / f"{timestamp}.md"

    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    cp = report["retrieval_scores"]["context_precision"]
    cr = report["retrieval_scores"]["context_recall"]
    fg = report["cases"]["grounded"]["faithfulness"]
    fh = report["cases"]["hallucinated"]["faithfulness"]

    def fmt(m: dict) -> str:
        return "n/a (error)" if m["score"] is None else f"{m['score']:.4f}"

    md = f"""# ragas RAG evaluation — {report['timestamp_iso']}

Mission: USS-TJR-MSN-0366 Stream 4. See
`knowledge/missions/RAGAS-RAG-EVAL-20260912-knowledge-record.md` for full context on
what "the RAG pipeline" turned out to be, and why the modes below may show fallback
paths.

| Setting | Mode |
|---|---|
| Retrieval | `{report['retrieval_mode']}` |
| Generation | `{report['generation_mode']}` |
| Judge | `{report['judge_mode']}` |

**Question:** {report['question']}

**Reference (ground truth):** {report['reference']}

**Retrieved contexts:**
{chr(10).join(f"- {c}" for c in report['retrieved_contexts'])}

## Scores

Context precision and context recall are retriever-quality metrics — they depend on
the question, retrieved contexts, and reference, not on which generated answer is
being judged, so they are computed once.

| Metric | Score |
|---|---|
| context_precision | {fmt(cp)} |
| context_recall | {fmt(cr)} |

Faithfulness depends on the generated answer, so it's computed once per case to show
the metric actually discriminating grounded vs. hallucinated output:

| Case | Answer | faithfulness |
|---|---|---|
| grounded | {report['cases']['grounded']['answer']} | {fmt(fg)} |
| hallucinated | {report['cases']['hallucinated']['answer']} | {fmt(fh)} |
"""
    md_path.write_text(md, encoding="utf-8")
    return json_path, md_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--document-type", default=None)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    contexts, retrieval_mode = get_context(args.question, args.document_type, args.limit)
    log.info("[ragas-eval] retrieval_mode=%s contexts=%d", retrieval_mode, len(contexts))

    grounded_answer, generation_mode = generate_answer(args.question, contexts)
    hallucinated_answer = grounded_answer + _FABRICATED_CLAIM
    log.info("[ragas-eval] generation_mode=%s", generation_mode)

    judge, judge_mode = build_judge_llm()

    retrieval_scores = asyncio.run(_score_retrieval_metrics(judge, args.question, contexts, args.reference))
    grounded_faithfulness = asyncio.run(_score_faithfulness(judge, args.question, grounded_answer, contexts))
    hallucinated_faithfulness = asyncio.run(_score_faithfulness(judge, args.question, hallucinated_answer, contexts))

    now = datetime.now(timezone.utc)
    report = {
        "mission": "USS-TJR-MSN-0366",
        "stream": "Stream 4 — ragas RAG evaluation",
        "timestamp_iso": now.isoformat(),
        "timestamp_compact": now.strftime("%Y%m%dT%H%M%SZ"),
        "retrieval_mode": retrieval_mode,
        "generation_mode": generation_mode,
        "judge_mode": judge_mode,
        "question": args.question,
        "reference": args.reference,
        "retrieved_contexts": contexts,
        "retrieval_scores": retrieval_scores,
        "cases": {
            "grounded": {"answer": grounded_answer, "faithfulness": grounded_faithfulness},
            "hallucinated": {"answer": hallucinated_answer, "faithfulness": hallucinated_faithfulness},
        },
    }

    json_path, md_path = _write_report(report)

    print(json.dumps(report, indent=2))
    print(f"\nWrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
