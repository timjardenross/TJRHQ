# Knowledge Record — USS-TJR-MSN-0378 (Streams 1, 3, 4, 5, 6)

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0378 |
| Title | Living Memory Across the Ship — consolidation arc (Streams 1, 3, 4, 5, 6) |
| Date | 2026-09-14 |
| Source | TJR HQ Capability Brief (2026-09-14), Play B. Cross-refs MEM-1 (rank 1/25), XO-1 (rank 3/25) |
| Related | [Stream 2 record](USS-TJR-MSN-0378-stream2-knowledge-record.md) (filed separately — standalone/independent per mission's Reporting instruction) |
| Commits | `b6c1a1702` (Stream 3), `bc0d2d752` (Stream 4 partial), `a3e369626` (remember() write-path fix), `572737c15` (Stream 5), `d5ebe9823` (registry) |

These five streams are reported together per the mission's own instruction — they're one dependent consolidation arc, unlike Stream 2.

## Stream 1 — Store count and embedding-model spread

Confirmed via direct code audit (fork agent, `select:` grounded, file:line cited throughout): **4 real, distinct embedding stores**, matching the top of the Pre-flight's "three or four" range — not fewer, so no mission-scope-down was triggered.

| Store | Embedding model | Table/index | Callers |
|---|---|---|---|
| `document_chunks` | mistral-embed, 1024d | `document_chunks.embedding`, HNSW idx, `match_document_chunks` RPC (migration 0102) | `generate_embeddings.py`, `retrieve_knowledge.py`, `semantic_retrieval.py`, `meilisearch_client.py` |
| `research_memory` | nomic-embed-text, 768d, via local Model Router | `research_memory.embedding` (migration 0162) | `episodic_memory.py` only |
| mem0 + Qdrant | Gemini `gemini-embedding-001`, 768d | local file-based Qdrant collection `starship_memory` | `unified_memory.py` SEMANTIC/FACTUAL |
| Graphiti/FalkorDB | same Gemini model, separate store | `data/memory_graph.db` | `unified_memory.py` RELATIONSHIPS (via `memory_graph.py`) |

Recommendation (adopted): **mistral-embed**, already the most-adopted model, only one with a proven dimension-migration history (1536→768→1024 across migrations 0002/0003/0102).

## Stream 3 — Embedding convergence

`research_memory` had **zero live rows** at conversion time (confirmed via direct count, not assumed) — this made it a no-backfill, additive column change rather than a real migration. Added `embedding_mistral vector(1024)` + `match_research_memories_mistral` RPC alongside the legacy nomic column/RPC (kept, unused). `episodic_memory.py` now embeds via `tools/supabase/embedding_client.py`, same client `document_chunks` uses.

An in-place `ALTER COLUMN TYPE` on the live table was attempted first and correctly **blocked by this session's own DB-safety classifier** ("Modify Shared Resources") — switched to the additive column instead. 23 unit tests updated and passing.

## Stream 4 — Repoint mem0 backend + workbench tag

**Workbench tag: shipped.** `memory_graph.py` writes a `workbench` field into episode content and `source_description`; `search()` resolves it per-result (via a batched `EpisodicNode.get_by_uuids()` lookup — `EntityEdge` itself carries no `source_description`, only the originating episode does) and accepts an optional filter. 8 unit tests, offline.

**mem0 backend repoint: deliberately NOT done, documented not dropped.** Two real blockers hit:
1. mem0's native `supabase` vector-store backend uses the `vecs` library directly against a raw Postgres connection string — not the existing `SUPABASE_URL`/`SUPABASE_KEY` client. Attempting to even grep for a connection string tripped this session's own credential-materialization guardrail — correctly, since that's exactly the kind of secret that shouldn't get pulled into a model's context casually.
2. mem0 has no native mistral embedder. The alternative — configuring its generic `openai` embedder provider against Mistral's OpenAI-compatible endpoint — sends a `dimensions` API parameter mem0's own `EmbeddingClient` doesn't send, and its compatibility with Mistral's actual endpoint is unverified.

Shipping either against mem0's real, currently-working Qdrant+Gemini backend — the live memory behind XO's SEMANTIC/FACTUAL conversational recall — without end-to-end test ability in this session was judged too risky. Filed as open Technical Debt in the SUOC Platform Registry, not silently scoped out.

**Real gap found and fixed along the way:** the mission's Stream 5 instruction ("writes distilled facts into Graphiti via unified_memory.py's remember()") assumed that write path already existed. It didn't — `remember()` only ever wrote to mem0 (SEMANTIC/FACTUAL); RELATIONSHIPS was silently a no-op. Added `memory_graph.add_fact()` (generic single-episode writer) and wired `remember(RELATIONSHIPS, ...)` to it. 4 new unit tests.

## Stream 5 — Nightly consolidation job

`scripts/memory/nightly_consolidation.py`: reads unconsolidated `conversation_turns` (per-chat, marked via `consolidated_at`) and a trailing-24h window of Command Memory (`decisions`), asks the LLM to distil each into standalone facts, writes them via `remember(RELATIONSHIPS, ...)`.

Installed live as `deploy/memory-nightly-consolidation.{service,timer}` (systemd oneshot + timer, matching the repo's existing convention — `delivery-reconciler.timer` et al. — not a session-scoped tool, since this needs to survive independently of any Claude session). **Enabled and active**; first scheduled fire 2026-09-15 02:17 local.

Known, accepted limitation: `decisions` has no `consolidated_at`-style marker (adding one was out of this mission's scope), so the Command Memory side re-reads a trailing 24h window every run rather than tracking exactly what's been distilled — some re-processing across nights is possible. `conversation_turns` IS properly deduplicated. 12 offline unit tests.

## Stream 6 — Validation benchmark (actual scores)

Built `scripts/memory/benchmark_locomo.py` — a private, small LoCoMo-style eval, per the mission's explicit instruction that this is the real acceptance gate, not a nice-to-have.

**Honesty note on method:** the nightly job's trailing-24h window means it has never touched this mission's real historical Command Memory (65 rows, oldest from 2026-06-14) and, by design, never will in one run. So the benchmark does its own one-time seed step (`seed_graphiti()`), separate from the nightly job's ongoing behaviour, to get a real number today instead of waiting on organic accumulation. Scoring is a simple token-overlap heuristic (≥3 shared non-stopword tokens between a returned fact and the expected outcome), not an LLM-judge pipeline — documented as an approximation in the script itself.

**Actual run** (sample=8 real Command Memory decisions, 2026-09-14):

| Condition | Hits | Total | Rate |
|---|---|---|---|
| Graphiti (`memory_graph.search()`, post-seed) | 5 | 8 | **62.5%** |
| Pre-existing COMMAND route (`recall(MemoryType.COMMAND, query=...)`) | 0 | 8 | **0%** |

The 0% baseline isn't a modeling artifact — it's a real, confirmed finding: `unified_memory._recall_table()` only supports exact-match `.eq()` filters, and `"query"` isn't a real column on `decisions`, so there was never any natural-language recall capability on that path at all. The consolidated architecture's 62.5% is a genuine improvement from a genuine zero, on a small real sample — not a large-N statistically rigorous result, and stated as such.

**Recommendation for a follow-up:** re-run `scripts/memory/benchmark_locomo.py` after the nightly job has fired several times against real accumulating XO conversation history, to see whether the hit rate holds, improves, or degrades once retrieval is competing against a larger, organically-grown (not hand-seeded) graph.

## Acceptance checklist (mission's own criteria)

- Stream 2 ships independently, verifiably live — ✅ shipped/live; Telegram-exchange verification still pending real Captain usage (see Stream 2's own record).
- Stream 1's table exists and is cited in every later stream's PR — ✅ (this record + all Stream 3/4/5 commit messages cite it).
- No existing caller of any of the four original stores breaks, reads migrated not deleted — ✅ (additive columns/RPCs throughout; old `embedding`/`match_research_memories` on `research_memory` untouched; `knowledge_edges` untouched).
- `unified_memory.py`'s docstring corrected — ✅ (separate commit `fe46d86f8`, landed before Stream 3).
- Stream 6's benchmark report exists with actual scores — ✅ (this record, above).
- SUOC Platform Registry updated for Streams 3-5 — ✅ (`d5ebe9823`).
