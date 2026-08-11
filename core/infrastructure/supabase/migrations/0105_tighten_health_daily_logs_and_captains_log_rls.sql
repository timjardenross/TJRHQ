-- Migration 0105: reconcile health_daily_logs / captains_log_entries RLS with live reality
--
-- Found during the 2026-08-09 Human Systems Workbench Chief Engineer review
-- (workbench-reviews/human-systems/chief-engineer-review.md, Recommendation 1):
-- live RLS on health_daily_logs and captains_log_entries is correctly locked
-- down to `authenticated`, but the migrations that actually did that
-- (live migration history names: tighten_advisory_sessions_and_health_daily_logs_rls,
-- 2026-07-17, plus the security_phase1-4 set, 2026-06-20) were never committed
-- to this repo. Confirmed via list_migrations + pg_policies (project
-- cjvrpjwewsrumnbdydgg) on 2026-08-09.
--
-- captains_log_entries is the sharper case: its committed migration
-- (0005_captains_log_entries.sql) creates the table with NO RLS statement
-- at all. If this schema were ever rebuilt from tracked history alone, this
-- table would come back completely open (no RLS enabled -> unrestricted via
-- PostgREST, given the standard Supabase schema-level GRANTs to anon confirmed
-- live). health_daily_logs' own CREATE TABLE also predates the migrations
-- directory (untracked foundation, out of scope for this fix) and is included
-- here so its RLS state matches live even though its table-creation isn't
-- separately tracked.
--
-- This migration does not change live state — it was already correct — it
-- only brings the tracked history in line with what's already running.
-- Idempotent (drop-then-create) and guarded with to_regclass so it safely
-- no-ops on a fresh rebuild where the table doesn't exist yet (a separate,
-- pre-existing gap: neither table's CREATE TABLE is fully self-contained in
-- tracked migrations for a from-scratch replay — not something this
-- RLS-only fix attempts to solve).

DO $$
BEGIN
  IF to_regclass('public.health_daily_logs') IS NOT NULL THEN
    ALTER TABLE health_daily_logs ENABLE ROW LEVEL SECURITY;

    DROP POLICY IF EXISTS "auth_write" ON health_daily_logs;
    DROP POLICY IF EXISTS "auth_read" ON health_daily_logs;

    CREATE POLICY "auth_write"
      ON health_daily_logs FOR ALL
      TO authenticated
      USING (true)
      WITH CHECK (true);

    CREATE POLICY "auth_read"
      ON health_daily_logs FOR SELECT
      TO authenticated
      USING (true);
  END IF;

  IF to_regclass('public.captains_log_entries') IS NOT NULL THEN
    ALTER TABLE captains_log_entries ENABLE ROW LEVEL SECURITY;

    DROP POLICY IF EXISTS "auth_write" ON captains_log_entries;
    DROP POLICY IF EXISTS "auth_read" ON captains_log_entries;

    CREATE POLICY "auth_write"
      ON captains_log_entries FOR ALL
      TO authenticated
      USING (true)
      WITH CHECK (true);

    CREATE POLICY "auth_read"
      ON captains_log_entries FOR SELECT
      TO authenticated
      USING (true);
  END IF;
END $$;
