-- USS-TJR-MSN-0205C: VM Knowledge Processing Engine — document processing pipeline.
--
-- Authorised exception to ADR-0020 (reuse before create): dedicated
-- processing/lifecycle tables required for the document processing state
-- machine, following the same exception precedent as D-068
-- (`intelligence_notes` — "dedicated intake table required for lifecycle
-- state tracking"). These tables are deliberately separate from
-- `knowledge_documents` / `document_chunks` (MSN-0004/0005A): those are the
-- durable Command Memory / Working Memory corpus scoped to repo governance
-- knowledge (document_type IN ADR/Architecture/Crew/Mission/...); these are
-- a pre-approval staging area for personal files transferred from the Mac
-- Collector Agent (MSN-0205A/B). MSN-0205D's approval queue is the only
-- path from `processing_documents` into `knowledge_documents` — no
-- document enters durable memory without explicit Captain approval.

create extension if not exists pgcrypto;
create extension if not exists vector;

create table if not exists processing_documents (
  id uuid primary key default gen_random_uuid(),
  source_name text not null,
  source_path text not null unique,
  filename text not null,
  file_type text not null,
  size_bytes bigint,
  status text not null default 'received' check (
    status in (
      'received',
      'extracted',
      'ocr_required',
      'ocr_complete',
      'classified',
      'summarised',
      'embedded',
      'failed',
      'awaiting_review'
    )
  ),
  extracted_text text,
  ocr_used boolean not null default false,
  ocr_engine text,
  category text check (
    category is null or category in (
      'Financial', 'Legal', 'Health', 'Correspondence', 'Reference',
      'Identity', 'Property', 'Photo', 'Administrative', 'Other'
    )
  ),
  tags text[] not null default '{}'::text[],
  summary text,
  sensitivity text not null default 'standard' check (
    sensitivity in ('standard', 'sensitive', 'restricted')
  ),
  memory_recommendation text check (
    memory_recommendation is null or memory_recommendation in (
      'recommend_full', 'recommend_summary_only', 'recommend_metadata_only',
      'recommend_reject', 'needs_review'
    )
  ),
  chunk_count integer not null default 0,
  failure_reason text,
  processing_log jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  memory_document_id uuid references knowledge_documents(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists processing_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references processing_documents(id) on delete cascade,
  chunk_index integer not null,
  chunk_text text not null,
  embedding vector(768),
  embedding_model text,
  embedded_at timestamptz,
  created_at timestamptz not null default now(),
  unique (document_id, chunk_index)
);

create index if not exists idx_processing_documents_status
  on processing_documents (status);

create index if not exists idx_processing_documents_source_name
  on processing_documents (source_name);

create index if not exists idx_processing_documents_sensitivity
  on processing_documents (sensitivity);

create index if not exists idx_processing_chunks_document_id
  on processing_chunks (document_id);

create index if not exists idx_processing_chunks_embedding_hnsw
  on processing_chunks
  using hnsw (embedding vector_cosine_ops)
  where embedding is not null;

-- Reuses the set_updated_at() trigger function defined in 0001_knowledge_prototype.sql.
drop trigger if exists set_processing_documents_updated_at on processing_documents;
create trigger set_processing_documents_updated_at
before update on processing_documents
for each row execute function set_updated_at();

alter table processing_documents enable row level security;
alter table processing_chunks enable row level security;

create policy "service_role_full_access" on processing_documents
  for all to service_role using (true) with check (true);
create policy "anon_read" on processing_documents
  for select to anon using (true);

create policy "service_role_full_access" on processing_chunks
  for all to service_role using (true) with check (true);
create policy "anon_read" on processing_chunks
  for select to anon using (true);
