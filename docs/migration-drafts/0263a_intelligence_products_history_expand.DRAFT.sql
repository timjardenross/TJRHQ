-- DRAFT, NOT APPLIED. Lives outside core/infrastructure/supabase/migrations on purpose so no deploy path picks it up.
-- NUMBERING: provisional. Production migration versions are timestamps; the repo directory stops at 0260 and 0262 belongs to
-- another change. File as a timestamp-versioned migration (see the Batch 1 durable-state engineering report "numbering hazards").
--
-- 0263a  EXPAND: append-only assessment history for public.intelligence_products (see intelligence/product_history.py).
--
-- PREREQUISITES: 0261 (intelligence_products) applied. Nothing else. No application change is needed first.
-- SAFE WITH: the ORIGINAL writer (upsert on product_key,generated_for), the new writer with INTEL_PRODUCTS_APPEND_V1 OFF, and the
--   new writer with the flag ON. The original primary key stays; the database archives every content overwrite into
--   intelligence_products_revisions (trigger), and the view intelligence_products_current exposes the latest assessment per
--   product and cadence from the live rows PLUS those archived versions, so history is preserved WITHOUT part B.
-- PART B (0263b, contract) is an OPTIONAL later step; part R (0263r) undoes part B. Each is its own file, filed separately.
--
-- Re-runnable: columns, tables, constraints, triggers, policies and the view are created idempotently; a failed run (for example
-- lock_timeout, SQLSTATE 55P03) rolls back completely and can simply be retried.
--
-- Principles: nothing is deleted or overwritten silently; historical rows get explicit *_basis labels instead of inferred
-- values; cadence of historical rows is 'unknown' because it cannot be established from the stored data.
--
-- Vocabularies
--   reporting_date_basis: writer_melbourne (new writer, flag ON) | legacy_utc_key (new writer, flag OFF fallback)
--                         | as_of_melbourne_date (legacy rows: the Melbourne calendar date of the stored as_of instant; whether
--                           that was the INTENDED reporting day is not asserted. generated_for keeps the original key.)
--   cadence_basis:        job | caller_unspecified | legacy_unknown

begin;
set local lock_timeout = '3s';
set local statement_timeout = '60s';

-- Guard: 0263a is the EXPAND step. Re-running it after 0263b would re-add the archive/legacy-fill triggers and restore the union view
-- body over a contracted table (a mixed state). If 0263b is applied, stop; use 0263r first if the contract has to be undone.
do $$ begin
    if exists (select 1 from pg_trigger where tgname = 'intelligence_products_append_only'
               and tgrelid = 'public.intelligence_products'::regclass) then
        raise exception '0263a: 0263b is already applied (intelligence_products_append_only exists); refusing to re-run the expand step'
            using errcode = 'invalid_object_definition';
    end if;
end $$;

alter table public.intelligence_products
    add column if not exists id                   bigint generated always as identity,
    add column if not exists generation_seq       integer     not null default 1,
    add column if not exists reporting_date       date,          -- Melbourne calendar date the assessment is attributed to
    add column if not exists reporting_date_basis text,
    add column if not exists cadence              text,          -- daily | weekly | unknown
    add column if not exists cadence_basis        text,
    add column if not exists content_hash         text,          -- sha256 of canonical content (product_history.content_hash); NULL = not recorded
    add column if not exists input_watermark      jsonb,         -- {event_count, max_collected_at, id_hash, window_days}
    add column if not exists supersedes_id        bigint,        -- previous generation of the same product and cadence
    add column if not exists change_summary       jsonb,         -- facts about what changed vs the superseded generation (+ write_id nonce)
    add column if not exists writer_version       integer     not null default 1;

-- Backfill: explicit labels, no inferred cadence. as_of is a stored instant; its Melbourne date is a fact about WHEN it was generated.
update public.intelligence_products set
    reporting_date       = (as_of at time zone 'Australia/Melbourne')::date,
    reporting_date_basis = 'as_of_melbourne_date',
    cadence              = 'unknown',
    cadence_basis        = 'legacy_unknown'
where reporting_date is null;

do $$ begin
    if not exists (select 1 from pg_constraint where conname = 'intelligence_products_cadence_chk') then
        alter table public.intelligence_products
            add constraint intelligence_products_cadence_chk check (cadence is null or cadence in ('daily','weekly','unknown'));
    end if;
    if not exists (select 1 from pg_constraint where conname = 'intelligence_products_seq_chk') then
        alter table public.intelligence_products add constraint intelligence_products_seq_chk check (generation_seq >= 1);
    end if;
end $$;

-- Archive of every overwritten or deleted row (full copy). Written by trigger, so it also protects against the OLD writer, a
-- flag turned off, and manual SQL. Insert-only.
create table if not exists public.intelligence_products_revisions (
    revision_id          bigint generated always as identity primary key,
    archived_at          timestamptz not null default now(),
    archive_reason       text        not null check (archive_reason in ('update','delete','rollback_export')),
    source_id            bigint,
    product_key          text        not null,
    generated_for        date        not null,
    as_of                timestamptz not null,
    title                text        not null,
    summary              text        not null,
    sections             jsonb       not null,
    exceptions           jsonb       not null,
    body_md              text        not null,
    created_at           timestamptz not null,
    generation_seq       integer,
    reporting_date       date,
    reporting_date_basis text,
    cadence              text,
    cadence_basis        text,
    content_hash         text,
    input_watermark      jsonb,
    supersedes_id        bigint,
    change_summary       jsonb,
    writer_version       integer
);

-- One row per reassessment run (successful or failed), separate from content generations.
create table if not exists public.intelligence_product_refreshes (
    id             bigint generated always as identity primary key,
    refreshed_at   timestamptz not null default now(),     -- database clock at record time
    product_key    text        not null check (product_key in ('recurring_provider','systemic_risk','forward_watch')),
    cadence        text        not null check (cadence in ('daily','weekly','unknown')),
    reporting_date date        not null,
    as_of          timestamptz not null,                   -- the assessment instant
    outcome        text        not null check (outcome in ('new_generation','unchanged','failed')),
    generation_id  bigint,                                 -- FK added in part B
    generation_seq integer,
    input_watermark jsonb,
    content_hash   text,
    error_class    text,                                   -- exception class name only, never message text
    writer_version integer
);
create index if not exists intelligence_product_refreshes_lookup
    on public.intelligence_product_refreshes (product_key, cadence, as_of desc);

-- Privileges: hosted default ACLs hand new tables to anon/authenticated. History tables are read-only for signed-in users
-- (RLS also gates rows; this removes TRUNCATE/DML grants RLS cannot cover). The service role keeps its default access.
revoke all on table public.intelligence_products_revisions, public.intelligence_product_refreshes from anon, authenticated;
grant select on table public.intelligence_products_revisions, public.intelligence_product_refreshes to authenticated;
-- The existing table: signed-in users only ever read it; TRUNCATE is not covered by RLS.
revoke truncate, insert, update, delete, references, trigger on table public.intelligence_products from anon, authenticated;
-- TRUNCATE is neither archived by the row triggers nor covered by RLS: it would destroy all history (N1). Nothing in the platform
-- truncates these tables, so remove the privilege from every API role (a statement trigger below refuses it for any role incl. owner).
revoke truncate on table public.intelligence_products, public.intelligence_products_revisions, public.intelligence_product_refreshes
    from public, anon, authenticated, service_role;

-- Archive an overwrite only when CONTENT changes (M7): an identical-content overwrite adds no revision. A deletion is always archived.
create or replace function public.intelligence_products_archive() returns trigger language plpgsql as $$
begin
    insert into public.intelligence_products_revisions (
        archive_reason, source_id, product_key, generated_for, as_of, title, summary, sections, exceptions, body_md, created_at,
        generation_seq, reporting_date, reporting_date_basis, cadence, cadence_basis, content_hash, input_watermark,
        supersedes_id, change_summary, writer_version)
    values (lower(tg_op), old.id, old.product_key, old.generated_for, old.as_of, old.title, old.summary, old.sections,
        old.exceptions, old.body_md, old.created_at, old.generation_seq, old.reporting_date, old.reporting_date_basis,
        old.cadence, old.cadence_basis, old.content_hash, old.input_watermark, old.supersedes_id, old.change_summary,
        old.writer_version);
    if tg_op = 'DELETE' then return old; end if;
    return new;
end $$;

-- Rows written by the ORIGINAL writer get the same labelled attribution as the backfill. The original writer's merge only touches
-- the columns it sends, so on UPDATE it is recognised by "history columns unchanged while content or as_of changed" (the new
-- writer always changes change_summary: it carries a per-write nonce).
create or replace function public.intelligence_products_legacy_fill() returns trigger language plpgsql as $$
declare
    legacy boolean;
begin
    if tg_op = 'INSERT' then
        legacy := coalesce(new.writer_version, 1) = 1;
    else
        legacy := new.change_summary is not distinct from old.change_summary
              and (new.as_of, new.title, new.summary, new.sections, new.exceptions, new.body_md)
                  is distinct from (old.as_of, old.title, old.summary, old.sections, old.exceptions, old.body_md);
    end if;
    if legacy then
        new.reporting_date       := (new.as_of at time zone 'Australia/Melbourne')::date;
        new.reporting_date_basis := 'as_of_melbourne_date';
        new.cadence              := 'unknown';
        new.cadence_basis        := 'legacy_unknown';
        new.content_hash         := null;
        new.input_watermark      := null;
        new.supersedes_id        := null;
        new.change_summary       := null;
        new.writer_version       := 1;
        if tg_op = 'UPDATE' and (new.title, new.summary, new.sections, new.exceptions, new.body_md)
                                is distinct from (old.title, old.summary, old.sections, old.exceptions, old.body_md) then
            new.generation_seq := old.generation_seq + 1;
        end if;
    end if;
    return new;
end $$;

create or replace function public.intelligence_history_append_only() returns trigger language plpgsql as $$
begin
    raise exception '% is append-only (% refused)', tg_table_name, tg_op using errcode = 'integrity_constraint_violation';
end $$;

drop trigger if exists intelligence_products_archive_trg on public.intelligence_products;
drop trigger if exists intelligence_products_archive_del_trg on public.intelligence_products;
create trigger intelligence_products_archive_trg before update on public.intelligence_products
    for each row when ((old.title, old.summary, old.sections, old.exceptions, old.body_md)
                       is distinct from (new.title, new.summary, new.sections, new.exceptions, new.body_md))
    execute function public.intelligence_products_archive();
create trigger intelligence_products_archive_del_trg before delete on public.intelligence_products
    for each row execute function public.intelligence_products_archive();
drop trigger if exists intelligence_products_legacy_fill_trg on public.intelligence_products;
create trigger intelligence_products_legacy_fill_trg before insert or update on public.intelligence_products
    for each row execute function public.intelligence_products_legacy_fill();
-- TRUNCATE guard on the LIVE table (N1): refuse, never archive-then-allow. (0263b adds its own, named intelligence_products_no_truncate.)
drop trigger if exists intelligence_products_a_no_truncate on public.intelligence_products;
create trigger intelligence_products_a_no_truncate before truncate on public.intelligence_products
    for each statement execute function public.intelligence_history_append_only();
drop trigger if exists intelligence_products_revisions_append_only on public.intelligence_products_revisions;
create trigger intelligence_products_revisions_append_only before update or delete on public.intelligence_products_revisions
    for each row execute function public.intelligence_history_append_only();
drop trigger if exists intelligence_product_refreshes_append_only on public.intelligence_product_refreshes;
create trigger intelligence_product_refreshes_append_only before update or delete on public.intelligence_product_refreshes
    for each row execute function public.intelligence_history_append_only();
drop trigger if exists intelligence_products_revisions_no_truncate on public.intelligence_products_revisions;
create trigger intelligence_products_revisions_no_truncate before truncate on public.intelligence_products_revisions
    for each statement execute function public.intelligence_history_append_only();
drop trigger if exists intelligence_product_refreshes_no_truncate on public.intelligence_product_refreshes;
create trigger intelligence_product_refreshes_no_truncate before truncate on public.intelligence_product_refreshes
    for each statement execute function public.intelligence_history_append_only();

alter table public.intelligence_products_revisions enable row level security;
alter table public.intelligence_product_refreshes enable row level security;
drop policy if exists intelligence_products_revisions_read on public.intelligence_products_revisions;
drop policy if exists intelligence_product_refreshes_read on public.intelligence_product_refreshes;
create policy intelligence_products_revisions_read on public.intelligence_products_revisions for select to authenticated using (true);
create policy intelligence_product_refreshes_read on public.intelligence_product_refreshes for select to authenticated using (true);
-- Writes: service role only (it bypasses RLS); no insert/update/delete policy for any other role.

-- Current view (expand form): the latest assessment per (product_key, cadence), ordered by GENERATION TIME (as_of), never by the
-- mixed UTC/Melbourne reporting_date. Sources: live rows plus archived content overwrites (so a Monday weekly run that overwrote
-- the daily row on the same key still leaves the daily assessment visible). Exactly one row per (product_key, cadence), hence at
-- most one per (product_key, cadence, reporting_date). Readers choose between cadences explicitly:
--   * is_latest_for_product marks the most recently refreshed row of each product (unknown-cadence rows rank last on a tie);
--   * a stale weekly row stays visible next to a current daily one, because every cadence has its own row.
-- Part B replaces the body (same columns) with a live-rows-only definition.
create or replace view public.intelligence_products_current with (security_invoker = true) as
with gens as (
    select p.id, null::bigint as revision_id, 'live'::text as source, p.product_key, p.cadence, p.cadence_basis, p.reporting_date,
           p.reporting_date_basis, p.generated_for, p.generation_seq, p.as_of, p.title, p.summary, p.sections, p.exceptions,
           p.body_md, p.content_hash, p.input_watermark, p.supersedes_id, p.change_summary, p.created_at
    from public.intelligence_products p
    union all
    select null::bigint, r.revision_id, 'archived'::text, r.product_key, coalesce(r.cadence, 'unknown'), r.cadence_basis,
           coalesce(r.reporting_date, (r.as_of at time zone 'Australia/Melbourne')::date), r.reporting_date_basis, r.generated_for,
           coalesce(r.generation_seq, 1), r.as_of, r.title, r.summary, r.sections, r.exceptions, r.body_md, r.content_hash,
           r.input_watermark, r.supersedes_id, r.change_summary, r.created_at
    from public.intelligence_products_revisions r
    where r.archive_reason in ('update', 'rollback_export')
), latest as (
    select distinct on (g.product_key, g.cadence) g.*
    from gens g
    order by g.product_key, g.cadence, g.as_of desc, g.id desc nulls last, g.revision_id desc nulls last
), withref as (
    select l.*,
           greatest(l.as_of, r.as_of) as last_refresh_as_of,
           r.outcome                  as last_refresh_outcome,
           f.as_of                    as last_failed_as_of
    from latest l
    left join lateral (select x.as_of, x.outcome from public.intelligence_product_refreshes x
                       where x.product_key = l.product_key and x.cadence = l.cadence and x.outcome in ('new_generation','unchanged')
                       order by x.as_of desc, x.id desc limit 1) r on true
    left join lateral (select max(x.as_of) as as_of from public.intelligence_product_refreshes x
                       where x.product_key = l.product_key and x.cadence = l.cadence and x.outcome = 'failed') f on true
)
select w.id, w.product_key, w.cadence, w.cadence_basis, w.reporting_date, w.reporting_date_basis, w.generated_for,
       w.generation_seq, w.as_of, w.title, w.summary, w.sections, w.exceptions, w.body_md, w.content_hash,
       w.input_watermark, w.supersedes_id, w.change_summary, w.created_at,
       w.last_refresh_as_of, w.last_refresh_outcome, w.last_failed_as_of,
       w.revision_id, w.source,
       (row_number() over (partition by w.product_key order by w.last_refresh_as_of desc, (w.cadence = 'unknown'), w.cadence) = 1)
           as is_latest_for_product
from withref w;
revoke all on table public.intelligence_products_current from anon;
grant select on table public.intelligence_products_current to authenticated;

commit;
