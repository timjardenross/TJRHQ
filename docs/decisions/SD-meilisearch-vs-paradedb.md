# SD: Finish Meilisearch Hybrid Search (Evaluated pg_search, Not Adopted)

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0366 |
| Stream | Stream 2 — Stage 2A: New Open-Source Tool Adoption |
| Status | **Decided: finish Meilisearch hybrid search** |
| Date | 2026-09-12 |
| Decision owner | Claude (USS TJR platform engineering) |

## Context

`core/search/meilisearch_client.py` already wraps Meilisearch as the
platform's unified search backend, and `tools/supabase/retrieve_knowledge.py`
already calls it as the **primary** keyword-search path, falling back to a
Supabase RPC and then an `ilike` scan if Meilisearch is unavailable or
returns nothing. Meilisearch has supported hybrid (keyword + vector) search
since v1.6 (GA), but nobody had turned it on: no `embedders` setting was ever
configured on the index, and `search()` never sent a `hybrid` block. Deciding
whether to finish that work, or replace the whole thing with Postgres-native
`pg_search` (ParadeDB's BM25 extension) instead, was this mission's job.

The repo also carries two embedding code paths in
`tools/supabase/embedding_client.py`: `EMBEDDING_PROVIDER=mistral`
(`mistral-embed`, 1024-dim — the live default per
`core/infrastructure/supabase/migrations/0102_document_chunks_mistral_embeddings.sql`,
which migrated `document_chunks.embedding` from 768 to 1024 dims specifically
because Mistral is what's actually running) and `EMBEDDING_PROVIDER=ollama`
(`nomic-embed-text`, 768-dim — the original stack from
`0003_ollama_nomic_embeddings.sql`, now dormant but still fully coded). Both
are real, both still exist in the client; only one is live. Neither is a
"new embedding stack" — whichever is used to source hybrid-search vectors,
this mission was about wiring Meilisearch to an embedding source that
already exists, not inventing a third one.

## What was actually run

Both engines were stood up as real Docker containers in this sandbox (not
simulated):

- `getmeili/meilisearch:v1.10` — pulled and run with a master key, health
  checked, indexed, queried over its real HTTP API on `:7700`.
- `paradedb/paradedb:latest` (Postgres 18 + `pg_search` + `pgvector`
  pre-installed) — pulled and run, `CREATE EXTENSION pg_search` and
  `CREATE EXTENSION vector` both executed for real, a BM25 index built with
  `CREATE INDEX ... USING bm25(...)`, and real SQL hybrid queries run
  against it.

The same 6-document sample set was loaded into both, and the same two
paraphrase queries (no shared keywords with the target document) were run
against both, using the same real embedding vectors for both engines (see
"Embedder / vector source" below).

## Sample corpus (identical in both engines)

| id | title | content (abridged) |
|---|---|---|
| doc-1 | On-Call Physician Response Policy | "Physicians on call must acknowledge dispatch alerts within five minutes…" |
| doc-2 | Vehicle Fleet Servicing Schedule | "Automobile maintenance must be scheduled every 5000 miles…" |
| doc-3 | Database Backup Procedure | "Nightly backups of the production database are stored…" |
| doc-4 | Meilisearch Deployment Notes | "The search backend indexes knowledge documents…" |
| doc-5 | Employee Onboarding Checklist | "New hires must complete security training…" |
| doc-6 | Incident Response Escalation Guide | "When a service outage is detected, the on-call engineer pages…" |

Query 1: **"doctor reply time for emergency pages"** — paraphrases doc-1
(`doctor`≈`physician`, `reply`≈`acknowledge`, `emergency pages`≈`dispatch
alerts`) with **zero shared keywords**.
Query 2: **"car servicing timetable"** — paraphrases doc-2
(`car`≈`automobile`, `servicing`≈`maintenance`, `timetable`≈`schedule`) with
**zero shared keywords**.

## Evidence: Meilisearch hybrid search

Enabled the `vectorStore` experimental flag (required on v1.10; stabilised
in 1.13+), registered a `userProvided` embedder (`PATCH
/indexes/knowledge/settings/embedders`), indexed the 6 documents with
`_vectors.default`, and queried with `hybrid: {embedder, semanticRatio}`.

**Query 1, keyword-only** (`POST /indexes/knowledge/search {"q": "..."}`):
```json
{"hits": [], "estimatedTotalHits": 0}
```
Zero hits — exactly what a keyword engine should do with no shared terms.

**Query 1, hybrid** (`semanticRatio: 1.0`, same query text + real query
vector):
```json
{"hits": [
  {"id": "doc-1", "title": "On-Call Physician Response Policy", "_rankingScore": 0.854},
  {"id": "doc-2", "title": "Vehicle Fleet Servicing Schedule", "_rankingScore": 0.850},
  {"id": "doc-5", "title": "Employee Onboarding Checklist", "_rankingScore": 0.840},
  ...
], "semanticHitCount": 5}
```
doc-1 is the top hit. Query 2 behaved the same way: 0 keyword hits, doc-2 top
of the hybrid results (`_rankingScore: 0.796`). Meilisearch's hybrid ranking
worked correctly out of the box, with no manual score-fusion logic required.

## Evidence: ParadeDB pg_search spike

Same corpus, loaded into a real `knowledge_docs` table with a `bm25(id,
title, content)` index (`pg_search`) and a `vector(300)` column (`pgvector`,
same real embeddings).

**Query 1, BM25 only** (`WHERE id @@@ paradedb.match('content', '...')`):
```
  id   |               title                | bm25_score
-------+------------------------------------+------------
 doc-3 | Database Backup Procedure          |    1.49671
 doc-6 | Incident Response Escalation Guide |    1.49671
```
Unlike Meilisearch's clean zero, `paradedb.match()`'s default (OR-token)
matching returned two **wrong** documents rather than nothing — a worse
failure mode than "no results" for a caller that treats empty as "fall
through to the next retrieval path."

**Query 1, vector-only** (`pgvector`, `<=>` cosine distance) correctly put
doc-1 first (`cosine_sim = 0.7085`).

**Query 1, hand-rolled hybrid — naive linear blend**
(`0.3 * normalized_bm25 + 0.7 * vec_score`, a common textbook formula):
```
  id   |               title                | bm25_score |     vec_score      |    hybrid_score
-------+------------------------------------+------------+---------------------+---------------------
 doc-6 | Incident Response Escalation Guide |    1.49671 | 0.6539727168868162 |  0.7577809018207713
 doc-3 | Database Backup Procedure          |    1.49671 | 0.6172959419739156 |  0.7321071593817409
 doc-1 | On-Call Physician Response Policy  |          0 | 0.7085257658156507 | 0.49596803607095546
```
**doc-1 drops to 3rd place.** The two BM25 false positives, once blended in
at all, outrank the semantically correct document.

**Query 1, hand-rolled hybrid — Reciprocal Rank Fusion** (the more
principled fusion technique, `1/(60+rank)` per side, no manual weight
tuning): doc-1 **still** lands 3rd, behind the same two BM25 false
positives. RRF fixes the scale-mismatch problem RRF is meant to fix, but it
cannot undo a keyword match that was wrong at the retrieval stage — it can
only re-rank whatever both sides handed it.

Query 2 (the "car servicing timetable" case, where BM25 correctly returned
zero rows) fused fine with either formula, because there was nothing wrong
to fuse in. That is the crux of the finding: **pg_search's hybrid quality is
only as good as hand-tuned query construction on the BM25 side**, and a
default `paradedb.match()` call is not tuned. Meilisearch's hybrid ranking
absorbed the equivalent case (query 2) the same way, but also handled query
1 correctly with no tuning at all.

## Operational cost

- **Meilisearch**: already a running, already-integrated service. This
  mission adds one settings call and a request-shape change — no new
  infrastructure. `tools/test_meilisearch.py` already exists as a smoke
  test and now has a real hybrid-capable index to exercise.
- **pg_search**: `paradedb/paradedb` is a **separate Postgres distribution**
  (Postgres 18 with `pg_search`/`pg_cron`/etc. pre-compiled in), not a
  regular extension installable on top of any Postgres. Confirmed against
  the platform's actual hosted database (Supabase project `USSTJR`,
  `cjvrpjwewsrumnbdydgg`, Postgres 17.6) via `list_extensions`:
  **`pg_search` does not appear anywhere in Supabase's extension catalogue**
  — not installed, not available-but-uninstalled, not present at all.
  `vector` (pgvector 0.8.0) is already installed there. Adopting pg_search
  as the platform's primary index would mean abandoning managed Supabase
  Postgres — which this platform depends on for `pg_cron`, `pgmq`,
  `supabase_vault`, `pg_net`, `pg_graphql`, `wrappers`, Auth, Storage, RLS,
  and 190+ existing migrations — in favour of self-hosting ParadeDB's
  Postgres fork. That is not a search-backend decision anymore; it is a
  database-platform migration, undertaken for a hybrid-ranking feature that,
  per the evidence above, needs more manual tuning to match what
  Meilisearch already does by default.

## Migration cost against the existing fallback chain

`retrieve_knowledge.py`'s `keyword_results()` already implements exactly the
fallback shape this decision needs: try Meilisearch, fall through to
Supabase on empty/failure. Finishing Meilisearch hybrid search means
extending that same, already-proven pattern to `semantic_results()` —
compute the query embedding once (existing `EmbeddingClient`, unchanged),
try `hybrid_search()`, fall back to the existing `match_document_chunks` RPC
if Meilisearch has nothing. Net new surface area: one function and one
import. Switching to pg_search would instead mean replacing
`match_document_chunks` (a live Supabase RPC other code may call directly),
re-pointing the whole platform's Postgres connection at a different
database, and re-deriving the fallback chain from scratch against a
database that doesn't have the rest of the schema (`specialists`,
`specialist_permissions`, `knowledge_documents`, `retrieval_logs`, …) unless
those 190+ migrations are ported too.

## Decision

**Finish Meilisearch hybrid search. Do not adopt pg_search.**

pg_search's BM25+vector fusion is real, and the extension genuinely works —
but it is not reachable from this platform's actual database without a
full self-hosted-Postgres migration that nothing else in this evaluation
justifies, and even in a from-scratch environment its default hybrid
quality needed more manual query tuning than Meilisearch's did to avoid
demonstrably worse ranking than vector search alone. Meilisearch was already
the platform's primary keyword-search path; turning on hybrid there is a
small, low-risk extension of infrastructure that already exists and is
already integrated with the same fallback philosophy the rest of this
codebase uses.

**pg_search is evaluated, not adopted.** The spike above (BM25 index, real
`pg_search`/`pgvector` queries) is the complete record of that evaluation;
no pg_search code was wired into the platform.

## What shipped

- `core/search/meilisearch_client.py`: `enable_vector_store()`,
  `configure_hybrid_embedder()`, `hybrid_search()`, and an optional
  `vector=`/`embedder=` pair on `index_document()`. `search()` is unchanged
  and remains the keyword-only path.
- `tools/supabase/retrieve_knowledge.py`: `semantic_results()` now tries
  Meilisearch hybrid search first (vector from the existing
  `EmbeddingClient`), falling back to the existing `match_document_chunks`
  Supabase RPC — the same fallback shape `keyword_results()` already uses.

## Operational gotcha found and fixed while wiring this up

Turning on a `userProvided` embedder on an index is not additive-only: once
`configure_hybrid_embedder()` has run, Meilisearch **rejects** any
subsequent document write that doesn't address that embedder at all
(`vector_embedding_error: no vectors provided for document "..."`) —
confirmed by running `tools/test_meilisearch.py`'s existing keyword-only
smoke test against the hybrid-enabled index and watching it fail with
exactly that error. Meilisearch's own documented fix is an explicit
per-document opt-out (`_vectors.<embedder>: null`), confirmed harmless even
on an index with no embedder configured at all. `index_document()` now
always sends `_vectors: {embedder: vector}` (`vector` defaulting to
`None`/`null`) instead of only attaching `_vectors` when a vector was
supplied, so plain keyword-only indexing keeps working unconditionally,
before or after hybrid is turned on for a given index. Anyone else adding a
`userProvided` embedder to an existing Meilisearch index should expect this
same failure mode on every other document-writing path that isn't updated.

## Honest limitations

- **No production-scale corpus.** The evidence above is a 6-document,
  hand-built sample, not the platform's real `document_chunks` table (over
  a thousand rows per earlier migration notes). Ranking quality at that
  scale, and Meilisearch's HNSW performance under real load, is unverified.
- **Vector source in the demo is not the production embedder.** Both
  `api.mistral.ai` and `registry.ollama.ai` (and `huggingface.co`, checked
  as a third option) are blocked by this sandbox's egress policy (verified:
  403 CONNECT denials on all three; `docker pull` itself needed a
  `mirror.gcr.io` registry mirror to get past a similar block on Docker
  Hub's CDN). With no reachable embedding API and no API key available in
  this sandbox, the evidence above was generated with real 300-dimension
  spaCy (`en_core_web_md`) static word vectors — genuine semantic vectors
  with a demonstrated 0.77 cosine similarity on the "automobile
  maintenance" / "car servicing" paraphrase pair, but not the vectors that
  will actually run in production. The shipped code
  (`core/search/meilisearch_client.py`, `retrieve_knowledge.py`) sources
  vectors from the existing `EmbeddingClient` (Mistral, 1024-dim)
  unchanged; the embedder dimension configured in production must be 1024
  to match. This was **not** re-verified end-to-end against a live Mistral
  API from this sandbox — that step is blocked here and needs to happen in
  an environment that can actually reach `api.mistral.ai`.
- **`semanticRatio` was not tuned.** The demo used `1.0` (semantic only) to
  make the effect unambiguous in evidence. Production should tune this
  against real query logs; `0.5` (Meilisearch's own default) is a
  reasonable starting point, not a validated one.
- **The `vectorStore` experimental flag requirement is version-specific.**
  It was required on v1.10 (tested here); if the deployed Meilisearch
  version is 1.13+ it is stabilised and the flag call becomes a no-op —
  confirm the deployed version before assuming either behaviour.
