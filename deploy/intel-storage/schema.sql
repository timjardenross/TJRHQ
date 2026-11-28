create extension if not exists vector;
do $$ begin
  if not exists (select from pg_roles where rolname='intel_owner') then create role intel_owner nologin; end if;
  if not exists (select from pg_roles where rolname='intel_ingest') then create role intel_ingest login; end if;
  if not exists (select from pg_roles where rolname='intel_read') then create role intel_read login; end if;
  if not exists (select from pg_roles where rolname='intel_maint') then create role intel_maint login; end if;
end $$;
revoke all on database intel from public;
grant connect on database intel to intel_ingest, intel_read, intel_maint;
revoke create on schema public from public;
create schema if not exists intel authorization intel_owner;
-- the index default (40) missed a true nearest neighbour in the first rehearsal
alter database intel set hnsw.ef_search = 200;
create table if not exists intel.object (
  sha256 text primary key check (sha256 ~ '^[0-9a-f]{64}$'),
  domain text not null check (domain ~ '^[a-z][a-z0-9_-]{0,39}$'),
  raw_bytes bigint not null, stored_bytes bigint not null,
  created_at timestamptz not null default now());
create table if not exists intel.document (
  id bigint primary key,
  source_key text not null, uri text not null, title text not null, body text not null,
  origin text not null check (origin in ('synthetic', 'cleared_public')),
  object_sha256 text not null references intel.object(sha256),
  previous_id bigint references intel.document(id),
  retrieved_at timestamptz not null,
  search tsvector generated always as (setweight(to_tsvector('english', title), 'A') || to_tsvector('english', body)) stored);
create index if not exists document_search on intel.document using gin (search);
create index if not exists document_object on intel.document (object_sha256);
create index if not exists document_previous on intel.document (previous_id);
create table if not exists intel.passage (
  document_id bigint not null references intel.document(id) on delete cascade,
  ordinal int not null, body text not null, substantive boolean not null,
  primary key (document_id, ordinal));
-- separate table so that rebuildable vectors can be left out of the off-host dump
create table if not exists intel.passage_embedding (
  document_id bigint not null, ordinal int not null, model text not null, embedding vector(768) not null,
  primary key (document_id, ordinal),
  foreign key (document_id, ordinal) references intel.passage on delete cascade);
-- documents an active investigation depends on: their vectors are rebuilt first after a recovery
create table if not exists intel.rebuild_priority (
  document_id bigint primary key references intel.document(id) on delete cascade,
  reason text not null);
create index if not exists document_retrieved on intel.document (retrieved_at desc);
create index if not exists passage_embedding_hnsw on intel.passage_embedding using hnsw (embedding vector_cosine_ops);
alter table intel.object owner to intel_owner;
alter table intel.document owner to intel_owner;
alter table intel.passage owner to intel_owner;
alter table intel.passage_embedding owner to intel_owner;
alter table intel.rebuild_priority owner to intel_owner;
grant usage on schema intel to intel_ingest, intel_read, intel_maint;
grant select on all tables in schema intel to intel_read, intel_ingest, intel_maint;
grant insert on intel.rebuild_priority, intel.object, intel.document, intel.passage, intel.passage_embedding to intel_ingest;
grant delete on intel.object, intel.document to intel_maint;

-- Package C pilot: one historical cohort, copied with its recorded links. Identifiers from the source are kept as text.
create table if not exists intel.c_batch (
  batch_id text primary key, source_as_of text not null, synthetic boolean not null, authority text,
  export_digests jsonb not null, held jsonb not null, imported_at timestamptz not null default now(),
  check (synthetic or authority is not null));
create table if not exists intel.c_source (
  batch_id text not null references intel.c_batch on delete cascade,
  source_id text not null, source_name text not null, licence_url text not null, attribution text not null,
  primary key (batch_id, source_id));
create table if not exists intel.c_event (
  event_id text primary key, batch_id text not null references intel.c_batch on delete cascade, source_id text not null,
  raw_title text, raw_summary text, canonical_url text, geography text, collected_at timestamptz, published_at timestamptz,
  published_at_basis text, published_at_precision text, published_at_confidence text, signal_status text,
  -- the publication date only, not factual accuracy
  date_evidence text not null check (date_evidence in ('verified', 'unverified')),
  suppressed boolean, suppression_reason text, publisher_domain text, publisher_family text,
  canonical_signal_id text,
  canonical_state text not null check (canonical_state in ('loaded', 'held', 'external', 'not_recorded', 'deleted')),
  search tsvector generated always as (setweight(to_tsvector('english', coalesce(raw_title, '')), 'A') || to_tsvector('english', coalesce(raw_summary, ''))) stored,
  foreign key (batch_id, source_id) references intel.c_source (batch_id, source_id) on delete cascade);
create index if not exists c_event_search on intel.c_event using gin (search);
create table if not exists intel.c_edge (
  batch_id text not null references intel.c_batch on delete cascade,
  cohort_event_id text not null,                      -- no foreign key: a held record's links are kept without its content
  relation text not null, linked_id text not null,
  endpoint text not null check (endpoint in ('loaded', 'held', 'external', 'not_event', 'deleted')),
  origin_held boolean not null,
  not_independent_because text,
  primary key (cohort_event_id, relation, linked_id));
create index if not exists c_edge_linked on intel.c_edge (linked_id);
do $$ declare t text; begin
  foreach t in array array['c_batch', 'c_source', 'c_event', 'c_edge'] loop
    execute format('alter table intel.%I owner to intel_owner', t);
    execute format('grant select on intel.%I to intel_read, intel_ingest, intel_maint', t);
    execute format('grant insert on intel.%I to intel_ingest', t);
  end loop;
end $$;
grant delete on intel.c_batch to intel_maint;
