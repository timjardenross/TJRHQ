-- Advisory Workbench UX review (2026-08-09): document_chunks.embedding was
-- vector(768) (0003_ollama_nomic_embeddings.sql, nomic-embed-text), but the
-- live EMBEDDING_PROVIDER is mistral (mistral-embed, 1024 dimensions) — every
-- semantic retrieval call (tools/supabase/retrieve_knowledge.py's
-- match_document_chunks RPC, used by the Advisory Board's specialist-aware
-- retrieval) has been failing with "different vector dimensions 768 and
-- 1024" as a result. Same pattern as 0003's own 1536->768 migration:
-- drop the function first (references the old vector shape), replace the
-- column, recreate the function and index at the new dimension. The actual
-- 1206 chunks are re-embedded separately via generate_embeddings.py once
-- embedding is nulled out below (its fetch_chunks() filter is
-- `embedding is null`).

drop index if exists idx_document_chunks_embedding_hnsw;

drop function if exists match_document_chunks(vector,double precision,integer,text);

alter table document_chunks
  drop column if exists embedding;

alter table document_chunks
  add column embedding vector(1024);

update document_chunks
set
  embedding_model = null,
  embedded_at = null;

create index if not exists idx_document_chunks_embedding_hnsw
  on document_chunks
  using hnsw (embedding vector_cosine_ops)
  where embedding is not null;

create or replace function match_document_chunks(
  query_embedding vector(1024),
  match_threshold float default 0.0,
  match_count int default 10,
  requested_document_type text default null
)
returns table (
  document_id uuid,
  chunk_id uuid,
  source_path text,
  title text,
  document_type text,
  chunk_index integer,
  snippet text,
  similarity float
)
language sql
stable
as $$
  select
    kd.id as document_id,
    dc.id as chunk_id,
    kd.source_path,
    kd.title,
    kd.document_type,
    dc.chunk_index,
    left(dc.chunk_text, 700) as snippet,
    1 - (dc.embedding <=> query_embedding) as similarity
  from document_chunks dc
  join knowledge_documents kd on kd.id = dc.document_id
  where
    dc.embedding is not null
    and (requested_document_type is null or kd.document_type = requested_document_type)
    and 1 - (dc.embedding <=> query_embedding) >= match_threshold
  order by dc.embedding <=> query_embedding
  limit match_count;
$$;
