-- DRAFT, NOT APPLIED. ROLLBACK OF 0263b (run as the table owner; it deliberately disables the append-only trigger).
--
-- 0263r  restores the 0263a state: the original primary key (product_key, generated_for), the archive and legacy-fill triggers
-- (so the ORIGINAL writer stays protected after the rollback) and the 0263a view. Every generation stays stored: generations that
-- cannot keep their own row under the original key are first copied into intelligence_products_revisions (reason
-- 'rollback_export'), which the 0263a view reads.
--
-- PREREQUISITES: 0263b applied. Stop the new writer's flag-ON path first only if you want the rollback window quiet; the
-- lock below makes concurrent writers wait (3 s lock_timeout, then fail; retry).
-- NOT part of the forward path; file only when 0263b has to be undone. Re-running is refused by the guard.

begin;
set local lock_timeout = '3s';
set local statement_timeout = '120s';

do $$ begin
    if not exists (select 1 from pg_trigger where tgname = 'intelligence_products_append_only'
                   and tgrelid = 'public.intelligence_products'::regclass) then
        raise exception '0263r: 0263b is not applied (append-only trigger absent); nothing to roll back' using errcode = 'invalid_object_definition';
    end if;
end $$;

lock table public.intelligence_products in access exclusive mode;
alter table public.intelligence_products disable trigger intelligence_products_append_only;

-- Rows to keep: the latest version per original key (by generation time). Computed once with a window function: a correlated
-- subquery per row was quadratic (22 s at 6,000 rows in the WP11 scale rehearsal, with the table locked and portal reads timing out).
create temp table intelligence_products_rollback_keep on commit drop as
select id from (select id, row_number() over (partition by product_key, generated_for order by as_of desc, id desc) as rn
                from public.intelligence_products) k where rn = 1;
create unique index on intelligence_products_rollback_keep (id);

insert into public.intelligence_products_revisions (archive_reason, source_id, product_key, generated_for, as_of, title, summary,
    sections, exceptions, body_md, created_at, generation_seq, reporting_date, reporting_date_basis, cadence, cadence_basis,
    content_hash, input_watermark, supersedes_id, change_summary, writer_version)
select 'rollback_export', p.id, p.product_key, p.generated_for, p.as_of, p.title, p.summary, p.sections, p.exceptions, p.body_md,
       p.created_at, p.generation_seq, p.reporting_date, p.reporting_date_basis, p.cadence, p.cadence_basis, p.content_hash,
       p.input_watermark, p.supersedes_id, p.change_summary, p.writer_version
from public.intelligence_products p
where not exists (select 1 from intelligence_products_rollback_keep k where k.id = p.id);

-- Refresh rows that reference a removed generation id keep that (now dangling) id: the refreshes table is append-only and the
-- foreign key is dropped here; the removed generation's content stays in intelligence_products_revisions ('rollback_export').
alter table public.intelligence_products drop constraint intelligence_products_supersedes_fk;
alter table public.intelligence_product_refreshes drop constraint intelligence_product_refreshes_generation_fk;
delete from public.intelligence_products p
where not exists (select 1 from intelligence_products_rollback_keep k where k.id = p.id);
drop trigger intelligence_products_append_only on public.intelligence_products;
drop trigger intelligence_products_no_truncate on public.intelligence_products;
drop index public.intelligence_products_generation_key;
alter table public.intelligence_products drop constraint intelligence_products_pkey;
alter table public.intelligence_products add constraint intelligence_products_pkey primary key (product_key, generated_for);
alter table public.intelligence_products alter column reporting_date drop not null, alter column cadence drop not null;
update public.intelligence_products set supersedes_id = null where supersedes_id is not null;  -- ids of removed rows are gone

-- Re-create the 0263a protections for the original writer (M3): archive on content overwrite / delete, legacy attribution fill.
create trigger intelligence_products_archive_trg before update on public.intelligence_products
    for each row when ((old.title, old.summary, old.sections, old.exceptions, old.body_md)
                       is distinct from (new.title, new.summary, new.sections, new.exceptions, new.body_md))
    execute function public.intelligence_products_archive();
create trigger intelligence_products_archive_del_trg before delete on public.intelligence_products
    for each row execute function public.intelligence_products_archive();
create trigger intelligence_products_legacy_fill_trg before insert or update on public.intelligence_products
    for each row execute function public.intelligence_products_legacy_fill();

-- Restore the 0263a TRUNCATE protection (N1): the 0263b trigger was dropped above, so re-create the 0263a one and the privilege revoke.
drop trigger if exists intelligence_products_a_no_truncate on public.intelligence_products;
create trigger intelligence_products_a_no_truncate before truncate on public.intelligence_products
    for each statement execute function public.intelligence_history_append_only();
revoke truncate on table public.intelligence_products, public.intelligence_products_revisions, public.intelligence_product_refreshes
    from public, anon, authenticated, service_role;

-- Restore the 0263a view body (live rows plus archived versions); same columns.
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

commit;
-- Full removal of 0263a (separate decision): export intelligence_products_revisions and intelligence_product_refreshes first, then
-- drop the view, triggers, tables, functions and the added columns. Dropping the added columns loses only metadata.
