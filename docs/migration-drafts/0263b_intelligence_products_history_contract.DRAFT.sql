-- DRAFT, NOT APPLIED. OPTIONAL. Lives outside the migrations directory on purpose.
--
-- 0263b  CONTRACT: swap the primary key of public.intelligence_products to a surrogate id, make the generation list a first-class
-- append-only table, and replace the view body with a live-rows-only definition.
--
-- *** CANNOT BE FILED UNTIL ALL OF THE FOLLOWING ARE TRUE (each is a separate release, none of them is in this repository's
-- database layer) ***
--   1. 0263a is applied and the new writer is deployed (flag OFF or ON, both work on 0263a alone).
--   2. EVERY reader of the base table intelligence_products has been switched to public.intelligence_products_current, or
--      demonstrably tolerates SEVERAL rows per (product_key, reporting_date). After this step the base table holds every
--      generation; a reader that takes "the first row per product ordered by generated_for" gets an arbitrary one of the day.
--      Readers (grep -rn intelligence_products over the whole tree):
--        - lcars-portal/src/lib/intelligenceProducts.ts  (HQ/portal: order by generated_for desc limit 30, first row per key)
--              APPLICATION CHANGE ESSENTIAL BEFORE PART B. CAPTAIN APPROVAL REQUIRED (HQ Development is not an active workstream).
--        - intelligence/brief_products_block.py          (flag ON reads the view; the flag-OFF fallback is fixed in this branch)
--        - tools/intelligence/verify_operational.py, tools/ops/live_cycle_queries.py, tools/intelligence/effectiveness_measures.py
--              (changed in this branch to tolerate several generations per day)
--   3. The Captain / G4 approves filing. File it as its own migration. Take a point-in-time export of the three tables first.
-- Part A alone already preserves history (trigger archive of every content overwrite + the current view), so this step buys
-- uniqueness-by-construction and append-only enforcement on the live table, not more history.
--
-- After this step the ORIGINAL writer fails with SQLSTATE 42P10 (its on_conflict target is gone); the new writer's flag-OFF path
-- detects that and appends with the original attribution instead.
--
-- Safety: lock_timeout makes it fail fast instead of queuing behind a long transaction and blocking readers (retry later; the
-- transaction is atomic). Re-running after success is refused by the guard below. Rollback is 0263r.

begin;
set local lock_timeout = '3s';
set local statement_timeout = '120s';

do $$ begin
    if exists (select 1 from pg_trigger where tgname = 'intelligence_products_append_only'
               and tgrelid = 'public.intelligence_products'::regclass) then
        raise exception '0263b already applied (append-only trigger present); nothing to do' using errcode = 'invalid_object_definition';
    end if;
    if not exists (select 1 from pg_class where relname = 'intelligence_products_revisions' and relnamespace = 'public'::regnamespace) then
        raise exception '0263b requires 0263a' using errcode = 'undefined_table';
    end if;
end $$;

lock table public.intelligence_products in access exclusive mode;

-- 0. Drop the transitional triggers first so the housekeeping updates below are not archived a second time.
drop trigger intelligence_products_archive_trg on public.intelligence_products;
drop trigger intelligence_products_archive_del_trg on public.intelligence_products;
drop trigger intelligence_products_legacy_fill_trg on public.intelligence_products;

-- 0b. Swap the primary key first: folding below inserts a second row for a (product_key, generated_for) that already exists.
--     From this statement on the original writer's on_conflict target no longer exists (42P10).
alter table public.intelligence_products drop constraint intelligence_products_pkey;
alter table public.intelligence_products add constraint intelligence_products_pkey primary key (id);

-- 1. Fold archived (overwritten) versions into the generation list so lineage is uniform. Idempotent per revision.
--    A revision is NOT folded when its content equals the next version of the same product in time (an adjacent duplicate would
--    show as a second "generation" with identical content); non-adjacent repeats (A, B, A) are real generations and are kept.
with versions as (
    select 'rev'::text as src, r.revision_id as rid, null::bigint as pid, r.product_key, r.as_of,
           md5(concat_ws('|', r.title, r.summary, r.sections::text, r.exceptions::text, r.body_md)) as h, 0 as ord
    from public.intelligence_products_revisions r where r.archive_reason in ('update', 'rollback_export')
    union all
    select 'live', null, p.id, p.product_key, p.as_of,
           md5(concat_ws('|', p.title, p.summary, p.sections::text, p.exceptions::text, p.body_md)), 1
    from public.intelligence_products p
), ordered as (
    select v.*, lead(v.h) over (partition by v.product_key order by v.as_of, v.ord, coalesce(v.rid, v.pid)) as next_h from versions v
)
insert into public.intelligence_products (
    product_key, generated_for, as_of, title, summary, sections, exceptions, body_md, created_at,
    reporting_date, reporting_date_basis, cadence, cadence_basis, content_hash, input_watermark, writer_version, change_summary)
select r.product_key, r.generated_for, r.as_of, r.title, r.summary, r.sections, r.exceptions, r.body_md, r.created_at,
       coalesce(r.reporting_date, (r.as_of at time zone 'Australia/Melbourne')::date),
       coalesce(r.reporting_date_basis, 'as_of_melbourne_date'), coalesce(r.cadence, 'unknown'), coalesce(r.cadence_basis, 'legacy_unknown'),
       r.content_hash, r.input_watermark, coalesce(r.writer_version, 1),
       jsonb_build_object('folded_from_revision_id', r.revision_id, 'archived_at', r.archived_at)
from public.intelligence_products_revisions r
join ordered o on o.src = 'rev' and o.rid = r.revision_id
where r.archive_reason in ('update', 'rollback_export')
  and o.h is distinct from o.next_h
  and not exists (select 1 from public.intelligence_products p
                  where (p.change_summary ->> 'folded_from_revision_id') = r.revision_id::text);

-- 2. Sequence per (product, cadence, reporting_date) by time; predecessor link per (product, cadence).
with ranked as (
    select id,
           row_number() over (partition by product_key, cadence, reporting_date order by as_of, id) as rn,
           lag(id) over (partition by product_key, cadence order by as_of, id)                      as prev
    from public.intelligence_products)
update public.intelligence_products p set generation_seq = ranked.rn, supersedes_id = ranked.prev
from ranked where p.id = ranked.id;

-- 3. Constraints that need the resequenced data.
alter table public.intelligence_products alter column reporting_date set not null, alter column cadence set not null;
create unique index intelligence_products_generation_key
    on public.intelligence_products (product_key, cadence, reporting_date, generation_seq);
alter table public.intelligence_products
    add constraint intelligence_products_supersedes_fk foreign key (supersedes_id) references public.intelligence_products (id);
alter table public.intelligence_product_refreshes
    add constraint intelligence_product_refreshes_generation_fk foreign key (generation_id) references public.intelligence_products (id) not valid;
-- NOT VALID on purpose and never validated here: the refreshes table is append-only, so refresh rows that point at a generation id
-- removed by an earlier 0263r (rollback) cannot be repaired. They stay as historical records (the generation content is kept in
-- intelligence_products_revisions); the constraint is enforced for every NEW refresh row.

-- 4. Append-only from now on (0263r disables it deliberately, as table owner).
create trigger intelligence_products_append_only before update or delete on public.intelligence_products
    for each row execute function public.intelligence_history_append_only();
create trigger intelligence_products_no_truncate before truncate on public.intelligence_products
    for each statement execute function public.intelligence_history_append_only();

-- 5. Current view, live rows only (same columns as 0263a): latest generation per (product_key, cadence) BY GENERATION TIME,
--    plus the latest successful refresh (an identical-content refresh moves last_refresh_as_of but not as_of).
create or replace view public.intelligence_products_current with (security_invoker = true) as
with latest as (
    select distinct on (g.product_key, g.cadence)
           g.id, null::bigint as revision_id, 'live'::text as source, g.product_key, g.cadence, g.cadence_basis, g.reporting_date,
           g.reporting_date_basis, g.generated_for, g.generation_seq, g.as_of, g.title, g.summary, g.sections, g.exceptions,
           g.body_md, g.content_hash, g.input_watermark, g.supersedes_id, g.change_summary, g.created_at
    from public.intelligence_products g
    order by g.product_key, g.cadence, g.as_of desc, g.id desc
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

commit;
