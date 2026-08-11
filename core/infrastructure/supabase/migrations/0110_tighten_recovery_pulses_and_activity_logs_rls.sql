-- Migration 0107: reconcile recovery_pulses / activity_logs RLS with live reality
--
-- Found during the 2026-08-09 Human Systems Workbench Chief Engineer review
-- (workbench-reviews/human-systems/chief-engineer-review.md, Recommendation 1).
-- Live migration history (project cjvrpjwewsrumnbdydgg, confirmed via
-- list_migrations on 2026-08-09) shows recovery_pulses and activity_logs were
-- brought under `authenticated`-only RLS by the 2026-06-20 security_phase1-4
-- set (security_phase1_enable_rls_unprotected,
-- security_phase2_replace_permissive_policies, plus the intervening
-- allow_anon_writes_activity_weight_logs migration that briefly opened
-- anon writes on activity_logs/weight_logs and was itself reversed by
-- phase 2 the same session) and the later human_systems_realtime /
-- recovery_pulses_multi_telemetry work. None of these are committed to this
-- repo's migrations directory (grep across all 115 tracked files found no
-- match for any of these names).
--
-- recovery_pulses additionally carries a service_role-only INSERT policy
-- (it's also written by the Telegram-bot backend, not just the UI) alongside
-- the authenticated one — reproduced here exactly as verified live via
-- pg_policies. Neither table has an UPDATE/DELETE policy live; none is added
-- here.
--
-- weight_logs shares activity_logs' exact pattern and history
-- (allow_anon_writes_activity_weight_logs touched both) but is not part of
-- the Human Systems Workbench and not one of the nine tables the review
-- scoped this gap to — deliberately left out of this fix, noted here so it
-- isn't mistaken for an oversight.
--
-- This migration does not change live state — it was already correct — it
-- only brings the tracked history in line with what's already running.
-- Idempotent (drop-then-create).

ALTER TABLE recovery_pulses ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "auth_read" ON recovery_pulses;
DROP POLICY IF EXISTS "auth_write" ON recovery_pulses;
DROP POLICY IF EXISTS "service_insert" ON recovery_pulses;

CREATE POLICY "auth_read"
  ON recovery_pulses FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY "auth_write"
  ON recovery_pulses FOR INSERT
  TO authenticated
  WITH CHECK (true);

CREATE POLICY "service_insert"
  ON recovery_pulses FOR INSERT
  TO service_role
  WITH CHECK (true);

DO $$
BEGIN
  IF to_regclass('public.activity_logs') IS NOT NULL THEN
    ALTER TABLE activity_logs ENABLE ROW LEVEL SECURITY;

    DROP POLICY IF EXISTS "Authenticated users can manage activity_logs" ON activity_logs;

    CREATE POLICY "Authenticated users can manage activity_logs"
      ON activity_logs FOR ALL
      TO authenticated
      USING (true)
      WITH CHECK (true);
  END IF;
END $$;
