-- USS-TJR-MSN-0005A: Local Ollama + nomic-embed-text embeddings.
-- Preserves knowledge_documents and document_chunks rows while replacing only incompatible vector data.

create extension if not exists vector;

drop index if exists idx_document_chunks_embedding_hnsw;

-- Required before replacing the embedding column because the old function references the existing vector shape.
drop function if exists match_document_chunks(vector,double precision,integer,text);

-- Required because nomic-embed-text returns 768 dimensions; existing 1536-dimension vectors cannot be cast.
alter table document_chunks
  drop column if exists embedding;

alter table document_chunks
  add column embedding vector(768);

alter table document_chunks
  add column if not exists embedding_model text;

alter table document_chunks
  add column if not exists embedded_at timestamptz;

update document_chunks
set
  embedding_model = null,
  embedded_at = null;

create index if not exists idx_document_chunks_embedding_hnsw
  on document_chunks
  using hnsw (embedding vector_cosine_ops)
  where embedding is not null;

create or replace function match_document_chunks(
  query_embedding vector(768),
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
