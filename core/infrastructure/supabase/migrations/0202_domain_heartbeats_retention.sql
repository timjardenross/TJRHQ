-- ============================================================================
-- Migration 0202 -- domain_heartbeats: bounded retention (USS-TJR-MSN-0378,
-- Supabase Free Plan usage-reduction mission)
-- ============================================================================
-- Purpose:
--   domain_heartbeats is a rolling event log (migration 0071) with no
--   retention -- every domain writes a row on every run attempt forever.
--   Confirmed real via live query against this project (2026-09-13):
--     - 106,515 rows, growing at ~1,590 rows/day since 2026-07-08.
--     - 24 MB total (13.8 MB table + 10.3 MB index), the 3rd-largest table
--       on a project at 79% of its 0.5 GB Free Plan database-size quota.
--   Confirmed there is no read path for heartbeat rows beyond a 72-hour
--   window: domain_heartbeats_latest (migration 0168) only needs the most
--   recent row per domain_key, and the only other reader --
--   lcars-portal/src/app/api/agent-status-workbench/history/route.ts --
--   explicitly windows its own query to WINDOW_HOURS = 72. Rows older than
--   that have zero callers in this codebase.
--
--   30 days keeps ~10x the read window's margin (in case of an outage
--   investigation reaching back further than the live API window) while
--   bounding the table's growth. Runs once daily via pg_cron (already
--   installed on this project, extension version 1.6.4).
--
-- Apply via Supabase SQL Editor or psql.
-- ============================================================================

create or replace function public.prune_domain_heartbeats() returns void
language sql
security definer
set search_path = public
as $$
  delete from public.domain_heartbeats
  where checked_at < now() - interval '30 days';
$$;

comment on function public.prune_domain_heartbeats() is
  'USS-TJR-MSN-0378: bounds domain_heartbeats growth. Deletes rows older than 30 days -- well beyond the 72h window every real reader (domain_heartbeats_latest view, agent-status-workbench/history) actually uses. Scheduled daily via pg_cron.';

select cron.schedule(
  'prune_domain_heartbeats_daily',
  '30 3 * * *',
  $$select public.prune_domain_heartbeats();$$
)
where not exists (
  select 1 from cron.job where jobname = 'prune_domain_heartbeats_daily'
);

-- Rollback:
-- select cron.unschedule('prune_domain_heartbeats_daily');
-- drop function if exists public.prune_domain_heartbeats();
