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
create index if not exists passage_embedding_hnsw on intel.passage_embedding using hnsw (embedding vector_cosine_ops);
alter table intel.object owner to intel_owner;
alter table intel.document owner to intel_owner;
alter table intel.passage owner to intel_owner;
alter table intel.passage_embedding owner to intel_owner;
grant usage on schema intel to intel_ingest, intel_read, intel_maint;
grant select on all tables in schema intel to intel_read, intel_ingest, intel_maint;
grant insert on intel.object, intel.document, intel.passage, intel.passage_embedding to intel_ingest;
grant delete on intel.object, intel.document to intel_maint;
