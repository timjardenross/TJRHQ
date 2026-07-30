-- Migration 0063 — Captain Memory Security & Information Governance
-- (MSN-0333)
--
-- MSN-0332 found: `sensitivity` (standard/sensitive/restricted) is
-- classified correctly at ingestion, faithfully copied onto
-- knowledge_documents.metadata on approval, and then completely inert
-- from that point on -- no RLS predicate, no retrieval filter, no
-- downstream distinction anywhere. This migration is the DB-level half
-- of the fix (the other half is the RPC-function change below, which
-- is the actual single authoritative enforcement point for the two
-- real search functions every retrieval consumer uses).
--
-- Deliberately does NOT redesign Command Memory or touch Captain
-- Intelligence -- confirmed by a separate audit that the Insight/
-- Reasoning Engine pipeline never reads knowledge_documents/
-- document_chunks content at all, only structured core_events fields.

-- ---------------------------------------------------------------------
-- 1. Officer clearance table -- the auth.uid()-keyed identity anchor
-- this platform never had (confirmed: no RLS policy anywhere in this
-- repo references auth.uid(), only role names authenticated/anon/
-- service_role). One row exists today (the Captain); this is what
-- makes "multi-user later without a redesign" true, not aspirational --
-- a second officer is added by inserting a second row, no schema change.
-- ---------------------------------------------------------------------

create table if not exists officer_clearances (
    id           uuid        primary key default gen_random_uuid(),
    auth_uid     uuid        not null unique references auth.users(id) on delete cascade,
    clearance    text        not null check (clearance in ('standard', 'sensitive', 'restricted')),
    granted_by   text        not null default 'Captain',
    granted_at   timestamptz not null default now(),
    note         text
);

comment on table officer_clearances is
  'MSN-0333: auth.uid() -> clearance level for Command Memory governance. '
  'clearance is the ceiling of what sensitivity level that identity may '
  'retrieve via general search/listing/export. A single-document lookup '
  'by ID (e.g. the Knowledge Library review detail view) is a separate, '
  'narrower access pattern this table does not gate -- reviewing what '
  'you just approved is not "general access".';

alter table officer_clearances enable row level security;

-- Only a real, already-cleared officer (or service_role, for seeding/
-- admin) may read or change clearances -- this table is itself
-- sensitive. No self-service elevation.
create policy "officer_clearances_service_role" on officer_clearances
  for all to service_role using (true) with check (true);

create policy "officer_clearances_self_read" on officer_clearances
  for select to authenticated using (auth_uid = auth.uid());

-- Seed: both real auth.users rows found for this Captain (2 email
-- logins, timjardenross@outlook.com and .sg) get full clearance. Not
-- guessing which is "the real one" -- both are treated as the Captain
-- until/unless a real second officer is ever introduced.
insert into officer_clearances (auth_uid, clearance, granted_by, note)
select id, 'restricted', 'MSN-0333 seed', 'Captain -- seeded at governance activation, real auth.users row'
from auth.users
on conflict (auth_uid) do nothing;

-- ---------------------------------------------------------------------
-- 2. Lookup function -- SECURITY DEFINER so it can read
-- officer_clearances regardless of the calling role's own RLS grants,
-- callable from RLS predicates on other tables.
-- ---------------------------------------------------------------------

create or replace function current_officer_clearance()
returns text
language sql
stable
security definer
set search_path = public
as $$
  select coalesce(
    (select clearance from officer_clearances where auth_uid = auth.uid()),
    'standard'  -- unregistered/unknown identity: lowest clearance, fail closed
  );
$$;

comment on function current_officer_clearance() is
  'MSN-0333: the calling identity''s Command Memory clearance ceiling. '
  'Unregistered auth.uid() (or no session at all) resolves to ''standard'' '
  '-- fail closed, never fail open.';

-- ---------------------------------------------------------------------
-- 3. RLS foundation on knowledge_documents/document_chunks -- replaces
-- the prior blanket `using (true)` (migration 0044) with a real
-- classification check. This is defense-in-depth for the LCARS web
-- session path specifically (createSupabaseServerClient, which DOES
-- respect RLS) -- it does NOT protect service_role-connected backend
-- scripts (those bypass RLS by default; that's why the RPC-function fix
-- below and the Python-side accessor module are the real authoritative
-- points for those consumers, not this policy).
-- ---------------------------------------------------------------------

drop policy if exists "authenticated_read" on knowledge_documents;
create policy "authenticated_read_by_clearance" on knowledge_documents
  for select to authenticated
  using (
    coalesce(metadata->>'sensitivity', 'standard') = 'standard'
    or (metadata->>'sensitivity' = 'sensitive' and current_officer_clearance() in ('sensitive', 'restricted'))
    or (metadata->>'sensitivity' = 'restricted' and current_officer_clearance() = 'restricted')
  );

drop policy if exists "authenticated_read" on document_chunks;
create policy "authenticated_read_by_clearance" on document_chunks
  for select to authenticated
  using (
    exists (
      select 1 from knowledge_documents kd
      where kd.id = document_chunks.document_id
        and (
          coalesce(kd.metadata->>'sensitivity', 'standard') = 'standard'
          or (kd.metadata->>'sensitivity' = 'sensitive' and current_officer_clearance() in ('sensitive', 'restricted'))
          or (kd.metadata->>'sensitivity' = 'restricted' and current_officer_clearance() = 'restricted')
        )
    )
  );

-- ---------------------------------------------------------------------
-- 4. The real single authoritative enforcement point: both RPC
-- functions every real search consumer (retrieve_knowledge.py, and any
-- future caller) actually goes through. Fixed here, at the SQL level,
-- so the exclusion applies regardless of which role/client calls them
-- -- this is what actually stops service_role-connected callers, which
-- the RLS policies above cannot.
-- ---------------------------------------------------------------------

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
    -- MSN-0333: general search excludes sensitive/restricted regardless
    -- of caller role -- the actual authoritative point for this path.
    and coalesce(kd.metadata->>'sensitivity', 'standard') = 'standard'
  order by dc.embedding <=> query_embedding
  limit match_count;
$$;

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
    -- MSN-0333: same exclusion as match_document_chunks above.
    and coalesce(kd.metadata->>'sensitivity', 'standard') = 'standard'
  order by rank desc, kd.source_path, dc.chunk_index
  limit match_limit;
$$;
