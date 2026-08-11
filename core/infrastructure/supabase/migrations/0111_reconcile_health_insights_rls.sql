-- Migration 0108: reconcile health_insights RLS with live reality
--
-- Found during the 2026-08-09 Human Systems Workbench Chief Engineer review
-- (workbench-reviews/human-systems/chief-engineer-review.md): health_insights
-- is one of the nine tables the review verified live RLS against
-- (`authenticated`-only, no anon/public policy), but no committed migration
-- enables RLS or defines a policy on this table at all — it isn't touched by
-- 0091_intelligence_workbench_phase_b.sql (which only enables RLS on the
-- newer health_source_articles table) or any other tracked file. The live
-- `auth_read` policy predates this repo's migration history (likely part of
-- the same 2026-06-20 security_phase1-4 pass that tightened its siblings —
-- list_migrations shows no single migration named specifically for this
-- table). health_insights has no write policy live at all — it's written by
-- the scheduler/backend via service_role, which bypasses RLS, matching the
-- convention used for other job-written tables (llm_call_metrics etc., see
-- 0087_shadow_mode_rls_lockdown.sql). No write policy is added here.
--
-- This migration does not change live state — it was already correct — it
-- only brings the tracked history in line with what's already running.
-- Idempotent (drop-then-create), guarded with to_regclass since
-- health_insights' own CREATE TABLE predates the migrations directory and
-- isn't fully tracked for a from-scratch replay (a separate, pre-existing
-- gap this RLS-only fix does not attempt to solve).

DO $$
BEGIN
  IF to_regclass('public.health_insights') IS NOT NULL THEN
    ALTER TABLE health_insights ENABLE ROW LEVEL SECURITY;

    DROP POLICY IF EXISTS "auth_read" ON health_insights;

    CREATE POLICY "auth_read"
      ON health_insights FOR SELECT
      TO authenticated
      USING (true);
  END IF;
END $$;
