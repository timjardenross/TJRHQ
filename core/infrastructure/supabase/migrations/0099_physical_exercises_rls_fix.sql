-- Migration 0099: physical_exercises RLS leak
--
-- Found during the 2026-08-08 workbench deep-dive audit: physical_exercises
-- (a static exercise reference/seed table — no code anywhere in the app
-- inserts or updates it) had public-role SELECT/INSERT/UPDATE policies.
-- Confirmed exploitable live: an anon-key POST reached the NOT-NULL
-- constraint layer (past RLS), proving write access was genuinely open,
-- not just readable. Its sibling tables (physical_workout_sessions,
-- physical_readiness_checkins, physical_workout_exercise_logs) were
-- already correctly scoped to authenticated — this one was missed.

DROP POLICY IF EXISTS "physical_exercises_select" ON physical_exercises;
DROP POLICY IF EXISTS "physical_exercises_insert" ON physical_exercises;
DROP POLICY IF EXISTS "physical_exercises_update" ON physical_exercises;

CREATE POLICY "physical_exercises_select"
  ON physical_exercises FOR SELECT
  TO authenticated
  USING (true);

-- No authenticated insert/update policy: nothing in the app writes to this
-- table (verified — grep found zero .insert()/.update() call sites), so
-- there is no legitimate user-facing write path to preserve. Maintenance
-- writes go through service_role, which bypasses RLS entirely.

GRANT SELECT ON physical_exercises TO authenticated;
REVOKE INSERT, UPDATE, DELETE ON physical_exercises FROM authenticated, anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON physical_exercises TO service_role;
