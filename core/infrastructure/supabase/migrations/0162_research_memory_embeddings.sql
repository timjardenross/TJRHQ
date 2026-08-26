-- 0162_research_memory_embeddings.sql
-- Episodic Memory v1: add pgvector embedding to research_memory for semantic
-- recall. Additive only — existing rows and write paths are unchanged.
--
-- Embedding model: nomic-embed-text via Model Router (768 dims, confirmed in
-- migration 0003). HNSW index pattern mirrors migration 0002.
--
-- Writer: core/platform/episodic_memory.py :: store_memory
-- Reader: core/platform/episodic_memory.py :: recall_similar  (via match_research_memories RPC)

ALTER TABLE public.research_memory
  ADD COLUMN IF NOT EXISTS embedding vector(768);

-- HNSW index for cosine similarity — partial index on embedded rows only,
-- matching the pattern in migration 0002 (idx_document_chunks_embedding_hnsw).
CREATE INDEX IF NOT EXISTS idx_research_memory_embedding_hnsw
  ON public.research_memory
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64)
  WHERE embedding IS NOT NULL;

COMMENT ON COLUMN public.research_memory.embedding IS
  'nomic-embed-text 768-dim vector over (original_question + findings[:500]). '
  'Populated asynchronously by episodic_memory.store_memory(); NULL until embedded.';

-- Semantic search RPC — mirrors match_document_chunks pattern (migration 0002).
-- Returns rows with cosine similarity above threshold, ordered closest-first.
-- Only returns rows that were successfully completed and have been embedded.
--
-- NOTE: execution_status='success' matches the values written by research_command.py.
-- The ticket spec used 'completed' but the live write path uses 'success'.
CREATE OR REPLACE FUNCTION public.match_research_memories(
  query_embedding  vector(768),
  match_threshold  float   DEFAULT 0.7,
  match_count      int     DEFAULT 10
)
RETURNS TABLE (
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
LANGUAGE sql STABLE
AS $$
  SELECT
    id,
    original_question,
    consolidated_findings,
    recommendation,
    confidence_level,
    tags,
    reuse_count,
    created_at,
    1 - (embedding <=> query_embedding) AS similarity
  FROM public.research_memory
  WHERE embedding IS NOT NULL
    AND execution_status = 'success'
    AND 1 - (embedding <=> query_embedding) > match_threshold
  ORDER BY embedding <=> query_embedding
  LIMIT match_count;
$$;

COMMENT ON FUNCTION public.match_research_memories IS
  'Semantic nearest-neighbour search over completed research_memory rows. '
  'Mirrors match_document_chunks (migration 0002). '
  'Returns rows with cosine similarity above match_threshold, ordered by similarity desc. '
  'Only rows with embedding IS NOT NULL and execution_status = ''success'' are considered.';
