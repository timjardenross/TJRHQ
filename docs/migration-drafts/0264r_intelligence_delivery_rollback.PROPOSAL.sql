-- PROPOSAL (WP11), NOT APPLIED. DB-SIDE ROLLBACK of 0264 (delivery attempts + brief rollup columns). Same export-first discipline as
-- 0263z: the attempts table is an AUDIT record; dropping it destroys the only attempt-level delivery history.
--   1. Turn BRIEF_DELIVERY_RECORD_V1 off / revert the code (writers then stop touching the table and the columns).
--   2. Export off the host:  psql "$DB" -c "\copy (select row_to_json(t) from public.intelligence_delivery_attempts t) to 'attempts.jsonl'"
--      and the five rollup columns of both brief tables (select id/brief_id, production_status, production_status_reasons,
--      telegram_status, telegram_at, delivery_disclosure ...). Verify counts.
--   3. In ONE session:  set intelligence.export_confirmed = 'yes';  then run this file.
begin;
set local lock_timeout = '3s';
do $$ begin
    if current_setting('intelligence.export_confirmed', true) is distinct from 'yes' then
        raise exception 'refused: export delivery attempts first and set intelligence.export_confirmed = ''yes'' in this session'
            using errcode = 'insufficient_privilege';
    end if;
end $$;
drop table if exists public.intelligence_delivery_attempts;           -- also removes its triggers, indexes and policies
drop function if exists public.intelligence_delivery_attempts_guard(), public.intelligence_delivery_attempts_no_truncate();
alter table public.captains_daily_briefs drop column if exists production_status, drop column if exists production_status_reasons,
    drop column if exists telegram_status, drop column if exists telegram_at, drop column if exists delivery_disclosure;
alter table public.intelligence_briefs drop column if exists production_status, drop column if exists production_status_reasons,
    drop column if exists telegram_status, drop column if exists telegram_at, drop column if exists delivery_disclosure;
commit;
