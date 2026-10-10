-- 0231_shorten_log_retention_keep_latest.sql
-- Supabase DB-size review (2026-10-10): database 255 MiB of the Free plan's 500 MB.
-- Three append-only operational logs are pruned at 30 days (0221, plus a job created
-- outside migrations for domain_heartbeats). Counts measured 2026-10-10: rows older
-- than 14 days are 78.8% of domain_heartbeats (68,961 of 87,528), 60.8% of
-- core_events and 63.2% of verification_state, about 43 MiB after a VACUUM FULL.
--
-- Readers need at most 7 days of history (portal history tab 72 h, weekly review 7 d,
-- morning cycle "today", event-bus consumers "newest N" or 24 h) EXCEPT the newest
-- rows, which are read however old they are:
--   * view domain_heartbeat_latest takes the newest row AND the newest status in
--     ('ok','skipped') per domain (last_success_at, never_succeeded, is_stale).
--     5 of 61 domains had a last success older than 14 days when measured, so a plain
--     14-day delete would flip them to "never succeeded" in HQ Status.
--     => the newest row and the newest ok/skipped row per domain_key are always kept.
--   * verification_state is read as "latest 1" (infra_narrative, deadmans_switch,
--     command-centre) => the newest row is always kept.
--
-- NOT changed: intelligence_source_health stays at 30 days (intelligence/audit/
-- source_fidelity.py reads a 30-day window), audit_events stays at 90 days.
-- The pg_cron jobs (ids 3-6, 03:30-03:45 UTC) call these functions by name, so no
-- cron change is needed. prune_domain_heartbeats() previously existed only in the
-- live database (no migration defined it); this file puts it under version control.
--
-- ROLLBACK (restores the previous 30-day behaviour; deleted rows are not recoverable,
-- they are regenerable logs and their data is already excluded from the nightly backup):
--   create or replace function public.prune_domain_heartbeats() returns void
--     language sql security definer set search_path = 'public' as $$
--       delete from public.domain_heartbeats where checked_at < now() - interval '30 days'; $$;
--   create or replace function public.prune_core_events() returns void
--     language sql security definer set search_path = 'public' as $$
--       delete from public.core_events where occurred_at < now() - interval '30 days'; $$;
--   create or replace function public.prune_verification_state() returns void
--     language sql security definer set search_path = 'public' as $$
--       delete from public.verification_state where computed_at < now() - interval '30 days'; $$;
--
-- Disk is only returned to the quota after a VACUUM FULL of each table (run manually,
-- one table at a time; see the size-plan runbook), not by this migration.

create or replace function public.prune_domain_heartbeats()
returns void
language sql
security definer
set search_path = 'public'
as $$
  with keep as (
    (select distinct on (domain_key) heartbeat_id
       from public.domain_heartbeats
      order by domain_key, checked_at desc)
    union
    (select distinct on (domain_key) heartbeat_id
       from public.domain_heartbeats
      where status in ('ok', 'skipped')
      order by domain_key, checked_at desc)
  )
  delete from public.domain_heartbeats h
  where h.checked_at < now() - interval '14 days'
    and h.heartbeat_id not in (select heartbeat_id from keep);
$$;

create or replace function public.prune_core_events()
returns void
language sql
security definer
set search_path = 'public'
as $$
  delete from public.core_events
  where occurred_at < now() - interval '14 days';
$$;

create or replace function public.prune_verification_state()
returns void
language sql
security definer
set search_path = 'public'
as $$
  delete from public.verification_state
  where computed_at < now() - interval '14 days'
    and state_id <> (
      select state_id from public.verification_state
      order by computed_at desc, state_id
      limit 1
    );
$$;
