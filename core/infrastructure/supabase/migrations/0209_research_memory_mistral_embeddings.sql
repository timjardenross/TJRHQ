-- 0209_research_memory_mistral_embeddings.sql
--
-- USS-TJR-MSN-0378 Stream 3 ("Living Memory Across the Ship"). Stream 1's
-- grounding audit (this mission) confirmed four real, distinct embedding
-- stores with no shared contract: document_chunks (mistral-embed, 1024-dim,
-- migration 0102), research_memory (nomic-embed-text, 768-dim via the local
-- Model Router, migration 0162), mem0+Qdrant (Gemini gemini-embedding-001,
-- 768-dim), and Graphiti/FalkorDB (same Gemini model, separate store).
-- document_chunks has the most production callers (generate_embeddings.py,
-- retrieve_knowledge.py, semantic_retrieval.py, meilisearch_client.py) and
-- the only proven dimension-migration history (1536 -> 768 -> 1024 across
-- migrations 0002/0003/0102), so per Stream 3's instruction ("recommend the
-- one already used by the most callers, to minimise churn") mistral-embed
-- is the target model for the two real Postgres pgvector stores.
--
-- Additive, not destructive: adds embedding_mistral (1024-dim) alongside
-- the existing nomic-embed-text `embedding` column rather than converting
-- it in place. research_memory has ZERO live rows as of this migration, so
-- there is no real data at stake either way, but the additive column keeps
-- the legacy column/RPC (match_research_memories) intact and queryable —
-- consistent with the mission's "don't delete existing tables, leave
-- read-only until a follow-up confirms parity" instruction, and with this
-- session's own DB-safety guardrail treating an in-place ALTER COLUMN TYPE
-- on a live shared table as a blocked action.

alter table public.research_memory
  add column if not exists embedding_mistral vector(1024);

create index if not exists idx_research_memory_embedding_mistral_hnsw
  on public.research_memory
  using hnsw (embedding_mistral vector_cosine_ops)
  with (m = 16, ef_construction = 64)
  where embedding_mistral is not null;

comment on column public.research_memory.embedding_mistral is
  'mistral-embed 1024-dim vector over (original_question + findings[:500]), generated via tools/supabase/embedding_client.py -- same model/client as document_chunks (migration 0102), converged in USS-TJR-MSN-0378 Stream 3. Populated asynchronously by episodic_memory.store_memory(); NULL until embedded. Additive alongside the legacy nomic-embed-text embedding column (migration 0162), which is kept read-only per mission scope (no destructive schema changes).';

create or replace function public.match_research_memories_mistral(
  query_embedding  vector(1024),
  match_threshold  float   default 0.7,
  match_count      int     default 10
)
returns table (
  id                    uuid,
  original_question     text,
  consolidated_findings text,
  recommendation        text,
  confidence_level      double precision,
  tags                  text[],
  reuse_count           int,
  created_at            timestamptz,
  similarity            float
)
language sql stable
as $$
  select
    id,
    original_question,
    consolidated_findings,
    recommendation,
    confidence_level,
    tags,
    reuse_count,
    created_at,
    1 - (embedding_mistral <=> query_embedding) as similarity
  from public.research_memory
  where embedding_mistral is not null
    and execution_status = 'success'
    and 1 - (embedding_mistral <=> query_embedding) > match_threshold
  order by embedding_mistral <=> query_embedding
  limit match_count;
$$;

comment on function public.match_research_memories_mistral is
  'Semantic nearest-neighbour search over completed research_memory rows using the mistral-embed 1024-dim column (USS-TJR-MSN-0378 Stream 3). New RPC alongside the legacy match_research_memories (nomic-embed-text, kept unchanged/read-only). Returns rows with cosine similarity above match_threshold, ordered by similarity desc.';
