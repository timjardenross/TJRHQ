-- Migration 0106: reconcile physical readiness / workout RLS with live reality
--
-- Found during the 2026-08-09 Human Systems Workbench Chief Engineer review
-- (workbench-reviews/human-systems/chief-engineer-review.md, Recommendation 1).
-- The committed 0068_physical_readiness.sql creates physical_readiness_checkins,
-- physical_workout_sessions, and physical_workout_exercise_logs with
-- role-unrestricted `USING (true)` / `WITH CHECK (true)` policies (its own
-- header comment even documents this as deliberate at the time: "Single-user
-- system; RLS policies are permissive `true` checks"). Live policies on all
-- three tables were since tightened to `authenticated`-only (live migration
-- history name: tighten_physical_readiness_workout_rls, 2026-07-17) but that
-- migration was never committed to this repo. Confirmed via list_migrations +
-- pg_policies (project cjvrpjwewsrumnbdydgg) on 2026-08-09: policy names are
-- identical to 0068's, only the role scope differs (now `authenticated`
-- instead of unrestricted/public).
--
-- physical_readiness_checkins live has no UPDATE/DELETE policy (matches 0068
-- — never had one). physical_readiness_profiles is deliberately NOT included
-- here: verified live it is still `public`-role with `USING (true)` on all
-- three of its policies (unchanged from 0068) — out of scope for this fix,
-- since this workbench's review scoped the untracked-migration gap to the
-- nine tables it reads/writes, and physical_readiness_profiles isn't one of
-- them. Flagged separately, not silently fixed here.
--
-- This migration does not change live state — it was already correct — it
-- only brings the tracked history in line with what's already running.
-- Idempotent (drop-then-create).

ALTER TABLE physical_readiness_checkins ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "physical_readiness_checkins_select" ON physical_readiness_checkins;
DROP POLICY IF EXISTS "physical_readiness_checkins_insert" ON physical_readiness_checkins;

CREATE POLICY "physical_readiness_checkins_select"
  ON physical_readiness_checkins FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY "physical_readiness_checkins_insert"
  ON physical_readiness_checkins FOR INSERT
  TO authenticated
  WITH CHECK (true);

ALTER TABLE physical_workout_sessions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "physical_workout_sessions_select" ON physical_workout_sessions;
DROP POLICY IF EXISTS "physical_workout_sessions_insert" ON physical_workout_sessions;
DROP POLICY IF EXISTS "physical_workout_sessions_update" ON physical_workout_sessions;

CREATE POLICY "physical_workout_sessions_select"
  ON physical_workout_sessions FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY "physical_workout_sessions_insert"
  ON physical_workout_sessions FOR INSERT
  TO authenticated
  WITH CHECK (true);

CREATE POLICY "physical_workout_sessions_update"
  ON physical_workout_sessions FOR UPDATE
  TO authenticated
  USING (true)
  WITH CHECK (true);

ALTER TABLE physical_workout_exercise_logs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "physical_workout_exercise_logs_select" ON physical_workout_exercise_logs;
DROP POLICY IF EXISTS "physical_workout_exercise_logs_insert" ON physical_workout_exercise_logs;
DROP POLICY IF EXISTS "physical_workout_exercise_logs_update" ON physical_workout_exercise_logs;

CREATE POLICY "physical_workout_exercise_logs_select"
  ON physical_workout_exercise_logs FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY "physical_workout_exercise_logs_insert"
  ON physical_workout_exercise_logs FOR INSERT
  TO authenticated
  WITH CHECK (true);

CREATE POLICY "physical_workout_exercise_logs_update"
  ON physical_workout_exercise_logs FOR UPDATE
  TO authenticated
  USING (true)
  WITH CHECK (true);
