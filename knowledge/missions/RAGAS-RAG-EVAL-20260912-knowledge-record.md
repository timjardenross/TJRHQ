# Knowledge Record — ragas RAG evaluation, 2026-09-12

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0366 |
| Title | "The RAG pipeline" turned out to be retrieval-only scaffolding with zero live callers, a real ragas/langchain-community version conflict blocked a vanilla install, and the eval sandbox itself had no reachable LLM at all |
| Date | 2026-09-12 |
| Lesson | LL-158 |

## Outcome

Added `core/quality/ragas_eval.py` — a real retrieval → generation → ragas-scoring
harness for USS-TJR-MSN-0366 Stream 4 (RAG-specific eval: faithfulness, context
precision, context recall), plus `core/quality/requirements-ragas.txt` and an
isolated `platform-runtime/.venv-ragas`. Reports land under `reports/ragas/`
(JSON + Markdown per run, same convention as `reports/garak/`).

**What "the RAG pipeline" actually is, confirmed by reading the code, not assuming
it from the mission title**: `tools/supabase/retrieve_knowledge.py` is a real,
working retrieval module — keyword search via Meilisearch with a Supabase RPC then
ilike fallback chain, a separate `--semantic` vector-similarity path, specialist
access control, and retrieval logging. Grepping the repo for callers of
`retrieve()`/`semantic_results()`/`keyword_results()`/`get_specialist()` turns up
only test scripts (`tools/supabase/test_semantic_retrieval.py`,
`tools/supabase/validate_specialist_access.py`) and this new eval module — nothing
combines that retrieval output with an LLM call to produce a generated answer.
"The RAG pipeline" is retrieval scaffolding, not a wired retrieval+generation loop,
matching the mission registry's "zero live callers" note exactly.
`core/quality/ragas_eval.py` is, as far as a repo-wide grep can tell, the first
thing in the repo that actually performs retrieval → generation → RAG-metric
scoring end to end.

**Judge model, matching this platform's existing convention rather than inventing
a new one**: `platform-runtime/lib/quality_scoring_service.py` already wires
deepeval's `HallucinationMetric` to a custom `_ModelRouterJudge` that calls this
platform's Model Router (`core/model-router`, port 8891) `/api/model/escalate`
task instead of deepeval's OpenAI default (no `OPENAI_API_KEY` exists anywhere on
this platform). `ragas_eval.py`'s `ModelRouterLLM` does the exact same thing —
same router, same task, same REST contract (`{"prompt": str} -> {"success",
"response"}`) — wrapped for ragas via `ragas.llms.LangchainLLMWrapper` instead of
`DeepEvalBaseLLM`. ragas is scoped to RAG-specific metrics only (faithfulness,
context precision, context recall); it does not duplicate
`quality_scoring_service.py`'s general hallucination scoring — the two are
complementary.

**A real, confirmed `pip install ragas` breakage, not a theoretical one**: a
vanilla `pip install ragas` resolves `langchain-community` to its latest (0.4.2),
but ragas==0.4.3's own `ragas/llms/base.py` unconditionally does
`from langchain_community.chat_models.vertexai import ChatVertexAI` at import
time — checked across ragas 0.4.3, 0.3.9, and 0.2.15, all three do the same
unconditional import — and that submodule does not exist in langchain-community
0.4.2 (confirmed present in the 0.3.31 wheel, absent from the 0.4.2 wheel; moved
upstream into the separate `langchain-google-vertexai` package). `import ragas`
raised `ModuleNotFoundError` before any eval code ran. Pinning
`langchain-community<0.4` in `core/quality/requirements-ragas.txt` fixes it, with
no cascading downgrade: `langchain-core` 1.6.3 (what ragas's own `langchain`/
`langchain-core` requirements resolve to) still satisfies langchain-community
0.3.31's own `langchain-core<2.0.0,>=0.3.78` constraint. Separately, `pip
install --dry-run` of ragas alongside every pin in
`platform-runtime/requirements.txt` together resolved cleanly with no forced
downgrade of `openai`, `pydantic`, `anyio`, or `typing_extensions` — but it still
pulled ~90 new packages (the full langchain stack, `datasets`, `pyarrow`,
`huggingface_hub`, `boto3`, `qdrant-client`, `neo4j`, ...) and forced ragas itself
down to the ancient 0.3.1 to satisfy the joint constraint set. Isolated into
`platform-runtime/.venv-ragas` instead, same reasoning as garak's isolation
(`core/quality/requirements-garak.txt`): footprint and version churn the live
serving path has no other use for, kept off the one shared venv every live
service depends on.

**The eval sandbox had no reachable LLM at all — confirmed, not assumed**: no
`SUPABASE_URL`/`SUPABASE_*_KEY` set (so the real retrieval RPC path can't run),
`http://127.0.0.1:8891` (Model Router) refuses the connection
(`ConnectionRefusedError`), no `ollama` binary and nothing listening on
`127.0.0.1:11434`, no `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`, and the sandbox's
egress policy returns a hard 403 on `huggingface.co` (checked via the agent
proxy's own status endpoint), so even pulling a small local HF model to serve as
judge was not possible. Given that, `ragas_eval.py` implements the real path for
every stage (live Supabase retrieval, live Model-Router generation, a
Model-Router-backed ragas judge) — what it will actually use the moment those
services are reachable — and falls back, only when a stage is unreachable, to a
real substitute rather than a placeholder: two verbatim excerpts of actual
repository documentation as retrieved context (`retrieve_knowledge.py`'s own
module docstring plus the OSS-Gap-Solutions GAP 4 writeup, both about this exact
tool), a hand-written grounded answer plus a deliberately-hallucinated variant for
generation, and — because no real LLM was reachable to serve as judge —
`OfflineLexicalOverlapJudge`: a deterministic LangChain `LLM` that parses ragas's
own structured judge prompts (schema + echoed input, confirmed by instrumenting a
probe LLM and reading ragas's real prompts rather than guessing them from docs)
and answers each with real lexical-overlap arithmetic over the actual
statement/context text, instead of an LLM's semantic judgment. This is explicitly
not a semantic/entailment judge and the code says so loudly at every relevant
point — it exists only to prove ragas's real scoring and aggregation math
(statement decomposition, verdict counting, precision/recall arithmetic) runs
end-to-end against real, input-dependent data, not to stand in for a production
gate.

**The real computed scores from the run committed under `reports/ragas/`**
(retrieval_mode=`fallback-repo-docs`, generation_mode=`fallback-fixture`,
judge_mode=`offline-lexical-overlap` — all three fallbacks active, per the
sandbox limitation above): `context_precision` = 0.99999999995, `context_recall`
= 1.0 (both computed once — they depend on the question/context/reference, not
on which generated answer is being judged), and `faithfulness` = 1.0 for the
grounded answer vs. 0.75 for the same answer with one fabricated, unsupported
sentence appended. The 1.0 → 0.75 drop is the metric genuinely doing its job: the
offline judge classified 3 of 4 decomposed statements as grounded and the 1
fabricated one as not, and ragas's own arithmetic (supported/total) turned that
into 0.75 — real computation on real per-input variation, not a hardcoded number.

## Lesson

A tool described as "the RAG pipeline" in a mission brief or registry is a claim
about intent, not architecture — confirm what actually combines retrieval with
generation (grep for real callers, don't infer from a module's docstring or
filename) before instrumenting it, and say plainly when a "pipeline" turns out to
be one stage of a pipeline with no second stage wired up yet. Separately: a
library's own PyPI metadata (`Requires-Dist: langchain-community`, unpinned) can
be fully satisfiable by pip's resolver while the library's actual code still hard
breaks against whatever version pip picks — declared dependency ranges and
hard-coded imports inside the package are two different (and here,
contradictory) sources of truth, and only actually running `import <package>`
after a fresh install catches the gap between them. And when a sandbox has zero
reachable LLM surface of any kind (no local model, no router, no API key, and
egress policy blocks the one remaining escape hatch), the honest move is to build
every real production code path anyway, prove the non-LLM-dependent parts (retrieval
fallback content, report generation, metric aggregation arithmetic) for real, and
be explicit and loud — in the code, the report, and here — about exactly which
piece had to use a deterministic non-LLM stand-in and why, rather than either
skipping the deliverable or quietly presenting a heuristic's output as if it were
a real judge's.

## Future Guidance

Before wiring `ragas_eval.py`'s judge or generation calls to a live Model Router
in a real deploy, re-run this harness there first (`retrieval_mode` and
`generation_mode` in the JSON report immediately show whether it actually reached
Supabase/the router, or silently fell back) — the fallback paths exist so the
harness never crashes when a dependency is down, which also means a misconfigured
`MODEL_ROUTER_URL` or missing `SUPABASE_URL` fails *quietly* into a fixture
answer rather than an error, so check the mode fields, don't just check the
scores. Before wiring an actual RAG caller (the still-missing second half of "the
RAG pipeline"), rerun `ragas_eval.py` against it directly rather than assuming
today's fallback-mode numbers transfer — `OfflineLexicalOverlapJudge`'s scores
are a proof of the scoring code path, not a quality baseline for real generated
answers. Any future `pip install ragas` into any venv (this one or a fresh one)
should keep `langchain-community<0.4` pinned alongside it until ragas's own
`ragas/llms/base.py` stops hard-importing `langchain_community.chat_models.
vertexai` — check `core/quality/requirements-ragas.txt`'s comment for how to
verify whether that's still true of whatever ragas version is current then.
