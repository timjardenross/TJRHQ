-- USS-TJR-MSN-0005: Embedding and semantic retrieval upgrade.
-- Uses Supabase-supported pgvector patterns only.

create extension if not exists vector;

alter table document_chunks
  add column if not exists embedding vector(1536);

alter table document_chunks
  add column if not exists embedding_model text;

alter table document_chunks
  add column if not exists embedded_at timestamptz;

create index if not exists idx_document_chunks_embedding_hnsw
  on document_chunks
  using hnsw (embedding vector_cosine_ops)
  where embedding is not null;

-- Required because PostgreSQL cannot change an existing function's return table shape.
drop function if exists match_document_chunks(vector,double precision,integer,text);

create or replace function match_document_chunks(
  query_embedding vector(1536),
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

create or replace function document_chunk_embedding_stats()
returns table (
  chunk_count bigint,
  embedded_chunk_count bigint,
  oversized_chunk_count bigint,
  duplicate_chunk_count bigint
)
language sql
stable
as $$
  with aggregate_counts as (
    select
      count(*) as chunk_count,
      count(*) filter (where embedding is not null) as embedded_chunk_count,
      count(*) filter (where length(chunk_text) > 1800) as oversized_chunk_count
    from document_chunks
  ),
  duplicate_counts as (
    select coalesce(sum(duplicate_total), 0)::bigint as duplicate_chunk_count
    from (
      select md5(chunk_text), count(*) as duplicate_total
      from document_chunks
      group by md5(chunk_text)
      having count(*) > 1
    ) duplicates
  )
  select
    aggregate_counts.chunk_count,
    aggregate_counts.embedded_chunk_count,
    aggregate_counts.oversized_chunk_count,
    duplicate_counts.duplicate_chunk_count
  from aggregate_counts
  cross join duplicate_counts;
$$;

create or replace function poor_semantic_retrieval_candidates(max_length integer default 1800)
returns table (
  chunk_id uuid,
  source_path text,
  title text,
  document_type text,
  chunk_index integer,
  issue text,
  chunk_length integer
)
language sql
stable
as $$
  select
    dc.id as chunk_id,
    kd.source_path,
    kd.title,
    kd.document_type,
    dc.chunk_index,
    case
      when dc.embedding is null then 'missing_embedding'
      when length(dc.chunk_text) > max_length then 'oversized_chunk'
      else 'duplicate_chunk'
    end as issue,
    length(dc.chunk_text) as chunk_length
  from document_chunks dc
  join knowledge_documents kd on kd.id = dc.document_id
  where
    dc.embedding is null
    or length(dc.chunk_text) > max_length
    or md5(dc.chunk_text) in (
      select md5(chunk_text)
      from document_chunks
      group by md5(chunk_text)
      having count(*) > 1
    )
  order by issue, chunk_length desc, kd.source_path, dc.chunk_index
  limit 25;
$$;
