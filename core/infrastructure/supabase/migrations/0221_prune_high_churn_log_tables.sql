-- 0221_prune_high_churn_log_tables.sql
--
-- Supabase egress/database-size investigation (2026-09-20): DB size was at
-- 83% of the Free Plan's 500MB quota. Live inspection found
-- domain_heartbeats already has a daily prune job (prune_domain_heartbeats,
-- 30-day window, cron.job id=3, "prune_domain_heartbeats_daily") but no
-- other high-churn append-only log table does. At the time of this
-- migration: core_events 30,050 rows/14MB, verification_state 19,755
-- rows/14MB, intelligence_source_health 48,332 rows/11MB, audit_events
-- 2,313 rows/2.4MB (smaller today, but the same unbounded-growth shape).
--
-- None of these four tables has a foreign key referencing it (checked live
-- against information_schema.table_constraints), so a plain DELETE cannot
-- orphan another table's row. Each is a raw per-event/per-check log with
-- its own downstream daily/summary aggregate table already computed from
-- it (e.g. source_reliability_snapshot for intelligence_source_health,
-- daily_health_snapshot for the platform overall) — pruning the raw log
-- does not remove the long-term trend data those summaries hold.
--
-- Same pattern as prune_domain_heartbeats: a SECURITY DEFINER SQL function
-- plus a cron.schedule() call, staggered a few minutes apart in the same
-- quiet 03:xx UTC window the existing prune job already runs in.
--
-- Retention windows: 30 days for the three high-volume operational logs
-- (core_events, verification_state, intelligence_source_health), matching
-- domain_heartbeats' own precedent. audit_events gets 90 days — an audit
-- trail's evidentiary value skews toward "keep it longer", and its row
-- count is far smaller today, so the extra retention costs little.

create or replace function public.prune_core_events()
returns void
language sql
security definer
set search_path = 'public'
as $$
  delete from public.core_events
  where occurred_at < now() - interval '30 days';
$$;

create or replace function public.prune_verification_state()
returns void
language sql
security definer
set search_path = 'public'
as $$
  delete from public.verification_state
  where computed_at < now() - interval '30 days';
$$;

create or replace function public.prune_intelligence_source_health()
returns void
language sql
security definer
set search_path = 'public'
as $$
  delete from public.intelligence_source_health
  where checked_at < now() - interval '30 days';
$$;

create or replace function public.prune_audit_events()
returns void
language sql
security definer
set search_path = 'public'
as $$
  delete from public.audit_events
  where created_at < now() - interval '90 days';
$$;

select cron.schedule('prune_core_events_daily', '35 3 * * *', $$select public.prune_core_events();$$);
select cron.schedule('prune_verification_state_daily', '40 3 * * *', $$select public.prune_verification_state();$$);
select cron.schedule('prune_intelligence_source_health_daily', '45 3 * * *', $$select public.prune_intelligence_source_health();$$);
select cron.schedule('prune_audit_events_daily', '50 3 * * *', $$select public.prune_audit_events();$$);
