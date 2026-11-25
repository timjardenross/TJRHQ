-- PROPOSAL (WP11), NOT APPLIED. FULL DB-SIDE ROLLBACK of 0263a (and of 0263b if it is still applied: run 0263r first).
-- Removes the expand objects so the database is back to the production shape of 2026-11-25: original primary key, original columns.
-- A code revert alone is NOT a rollback of the database; this script is the database half. It is destructive for HISTORY unless the
-- export below was taken, therefore it refuses to run without an explicit confirmation made in the same session:
--
--   1. Stop the new writer (flag OFF, or code reverted) so no new generation lands while exporting.
--   2. Export, off the database host, with a client-side copy (example; any equivalent export works):
--        psql "$DB" -c "\copy (select row_to_json(t) from public.intelligence_products t) to 'products.jsonl'"
--        psql "$DB" -c "\copy (select row_to_json(t) from public.intelligence_products_revisions t) to 'revisions.jsonl'"
--        psql "$DB" -c "\copy (select row_to_json(t) from public.intelligence_product_refreshes t) to 'refreshes.jsonl'"
--      Verify row counts and the sha256 of every body_md against the database before continuing.
--   3. In ONE session:  set intelligence.export_confirmed = 'yes';  then run this file.
--
-- What is lost by design: the metadata columns (generation_seq, cadence, hashes, watermarks, lineage), the archive table and the
-- refresh table. What is kept in place: every row of intelligence_products that holds the latest version per original key, byte-exact.
-- Older versions exist ONLY in the export after this script runs. Prerequisite: 0263b is not applied (use 0263r first).

begin;
set local lock_timeout = '3s';
set local statement_timeout = '120s';

do $$ begin
    if current_setting('intelligence.export_confirmed', true) is distinct from 'yes' then
        raise exception 'refused: export history first and set intelligence.export_confirmed = ''yes'' in this session'
            using errcode = 'insufficient_privilege';
    end if;
    if exists (select 1 from pg_trigger where tgname = 'intelligence_products_append_only' and tgrelid = 'public.intelligence_products'::regclass) then
        raise exception 'refused: 0263b is applied; run 0263r first' using errcode = 'invalid_object_definition';
    end if;
    if to_regclass('public.intelligence_products_revisions') is null then
        raise exception 'nothing to roll back: 0263a is not applied' using errcode = 'undefined_table';
    end if;
end $$;

lock table public.intelligence_products in access exclusive mode;
drop view if exists public.intelligence_products_current;
drop trigger if exists intelligence_products_archive_trg on public.intelligence_products;
drop trigger if exists intelligence_products_archive_del_trg on public.intelligence_products;
drop trigger if exists intelligence_products_legacy_fill_trg on public.intelligence_products;
drop trigger if exists intelligence_products_a_no_truncate on public.intelligence_products;   -- 0263a's TRUNCATE guard (depends on intelligence_history_append_only)
drop table public.intelligence_product_refreshes;
drop table public.intelligence_products_revisions;
drop function public.intelligence_products_archive();
drop function public.intelligence_products_legacy_fill();
drop function public.intelligence_history_append_only();
alter table public.intelligence_products drop constraint if exists intelligence_products_cadence_chk;
alter table public.intelligence_products drop constraint if exists intelligence_products_seq_chk;
alter table public.intelligence_products
    drop column id, drop column generation_seq, drop column reporting_date, drop column reporting_date_basis, drop column cadence,
    drop column cadence_basis, drop column content_hash, drop column input_watermark, drop column supersedes_id,
    drop column change_summary, drop column writer_version;
-- the 0263a revokes on intelligence_products (truncate/DML for signed-in users) are deliberately KEPT: nothing needs them back.
commit;
