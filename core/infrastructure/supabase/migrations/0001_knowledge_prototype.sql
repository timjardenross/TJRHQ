-- USS-TJR-MSN-0004: Supabase knowledge prototype schema.
-- This migration is intentionally small and local-run friendly.

create extension if not exists pgcrypto;

do $$
begin
  create extension if not exists vector;
exception
  when undefined_file then
    raise notice 'pgvector is not available in this Supabase project. TODO: enable the vector extension before semantic retrieval.';
  when insufficient_privilege then
    raise notice 'Current role cannot enable pgvector. TODO: enable vector in Supabase extensions before semantic retrieval.';
end
$$;

create table if not exists knowledge_documents (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  source_path text not null unique,
  document_type text not null check (
    document_type in (
      'ADR',
      'Architecture',
      'Crew',
      'Mission',
      'Capability',
      'Knowledge Base',
      'Specialist',
      'Unknown'
    )
  ),
  content text not null,
  metadata jsonb not null default '{}'::jsonb,
  tags text[] not null default '{}'::text[],
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists document_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references knowledge_documents(id) on delete cascade,
  chunk_index integer not null,
  chunk_text text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (document_id, chunk_index)
);

-- TODO: If pgvector was unavailable when this migration ran, rerun this block after enabling it.
do $$
begin
  if exists (select 1 from pg_extension where extname = 'vector') then
    alter table document_chunks
      add column if not exists embedding vector(1536);
  else
    raise notice 'Skipping document_chunks.embedding. TODO: enable pgvector and add embedding vector(1536).';
  end if;
end
$$;

create table if not exists specialists (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  role text not null unique,
  source_path text,
  metadata jsonb not null default '{}'::jsonb,
  tags text[] not null default '{}'::text[],
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists specialist_permissions (
  id uuid primary key default gen_random_uuid(),
  specialist_id uuid not null references specialists(id) on delete cascade,
  allowed_document_types text[] not null default '{}'::text[],
  restricted_document_types text[] not null default '{}'::text[],
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (specialist_id)
);

create table if not exists retrieval_logs (
  id uuid primary key default gen_random_uuid(),
  specialist_id uuid references specialists(id) on delete set null,
  specialist_role text,
  query text not null,
  document_type text,
  allowed boolean not null default true,
  blocked_reason text,
  result_count integer not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_knowledge_documents_document_type
  on knowledge_documents (document_type);

create index if not exists idx_knowledge_documents_tags
  on knowledge_documents using gin (tags);

create index if not exists idx_document_chunks_document_id
  on document_chunks (document_id);

create index if not exists idx_document_chunks_text_search
  on document_chunks using gin (to_tsvector('english', chunk_text));

create index if not exists idx_specialists_role
  on specialists (role);

create index if not exists idx_retrieval_logs_created_at
  on retrieval_logs (created_at desc);

create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists set_knowledge_documents_updated_at on knowledge_documents;
create trigger set_knowledge_documents_updated_at
before update on knowledge_documents
for each row execute function set_updated_at();

drop trigger if exists set_document_chunks_updated_at on document_chunks;
create trigger set_document_chunks_updated_at
before update on document_chunks
for each row execute function set_updated_at();

drop trigger if exists set_specialists_updated_at on specialists;
create trigger set_specialists_updated_at
before update on specialists
for each row execute function set_updated_at();

drop trigger if exists set_specialist_permissions_updated_at on specialist_permissions;
create trigger set_specialist_permissions_updated_at
before update on specialist_permissions
for each row execute function set_updated_at();

create or replace function keyword_search_documents(
  search_query text,
  requested_document_type text default null,
  match_limit integer default 10
)
returns table (
  document_id uuid,
  source_path text,
  title text,
  document_type text,
  chunk_index integer,
  snippet text,
  rank real
)
language sql
stable
as $$
  select
    kd.id as document_id,
    kd.source_path,
    kd.title,
    kd.document_type,
    dc.chunk_index,
    left(dc.chunk_text, 500) as snippet,
    ts_rank_cd(to_tsvector('english', dc.chunk_text), plainto_tsquery('english', search_query)) as rank
  from document_chunks dc
  join knowledge_documents kd on kd.id = dc.document_id
  where
    (requested_document_type is null or kd.document_type = requested_document_type)
    and to_tsvector('english', dc.chunk_text) @@ plainto_tsquery('english', search_query)
  order by rank desc, kd.source_path, dc.chunk_index
  limit match_limit;
$$;

-- TODO: Generate embeddings during ingestion, then use this function for semantic retrieval.
do $$
begin
  if exists (select 1 from pg_extension where extname = 'vector') then
    execute $fn$
      create or replace function match_document_chunks(
        query_embedding vector(1536),
        match_threshold float default 0.7,
        match_count int default 10,
        requested_document_type text default null
      )
      returns table (
        document_id uuid,
        source_path text,
        title text,
        document_type text,
        chunk_index integer,
        snippet text,
        similarity float
      )
      language sql
      stable
      as $sql$
        select
          kd.id as document_id,
          kd.source_path,
          kd.title,
          kd.document_type,
          dc.chunk_index,
          left(dc.chunk_text, 500) as snippet,
          1 - (dc.embedding <=> query_embedding) as similarity
        from document_chunks dc
        join knowledge_documents kd on kd.id = dc.document_id
        where
          dc.embedding is not null
          and (requested_document_type is null or kd.document_type = requested_document_type)
          and 1 - (dc.embedding <=> query_embedding) >= match_threshold
        order by dc.embedding <=> query_embedding
        limit match_count;
      $sql$;
    $fn$;
  end if;
end
$$;
