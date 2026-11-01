-- 0235: restrict EXECUTE on four scheduled maintenance functions.
--
-- STATUS: APPLIED to the live project on 2026-10-16 (live version 20261016040712).
-- Do NOT re-apply. This file is the record.
--
-- Before (read from the live catalog, metadata only): PUBLIC, anon,
-- authenticated, service_role and postgres all hold EXECUTE on
--   public.prune_audit_events()
--   public.prune_core_events()
--   public.prune_intelligence_source_health()
--   public.prune_verification_state()
-- These are scheduled maintenance jobs and need no client role.
--
-- After: only the owner (postgres) and service_role keep EXECUTE, which is
-- the grant set prune_domain_heartbeats() already has.
--
-- What legitimately calls these today:
--   * pg_cron jobs prune_{core_events,verification_state,
--     intelligence_source_health,audit_events}_daily (03:35-03:50 UTC), which
--     run as the owner (cron.job.username = postgres). Owner execution is
--     expected not to depend on any grant; the first run after the revoke
--     (17 Oct 03:35-03:50 UTC) has not been observed yet.
--   * No application code calls them over RPC (repo searched; only the
--     migrations that define and schedule them reference them).
--   * service_role keeps EXECUTE for manual or scripted maintenance.
--
-- Verified after applying (2026-10-16): the ACL shows only postgres and
-- service_role. Still to verify: the 17 Oct 03:35-03:50 UTC cron run records
-- succeeded in cron.job_run_details.
--
-- ROLLBACK (restores the exact previous grant set):
--   grant execute on function public.prune_audit_events() to public, anon, authenticated;
--   grant execute on function public.prune_core_events() to public, anon, authenticated;
--   grant execute on function public.prune_intelligence_source_health() to public, anon, authenticated;
--   grant execute on function public.prune_verification_state() to public, anon, authenticated;
--
-- Backup note: this changes privileges only; no row or function body is
-- touched, so no data backup is needed. The rollback above is the recovery.

revoke execute on function public.prune_audit_events() from public, anon, authenticated;
revoke execute on function public.prune_core_events() from public, anon, authenticated;
revoke execute on function public.prune_intelligence_source_health() from public, anon, authenticated;
revoke execute on function public.prune_verification_state() from public, anon, authenticated;
