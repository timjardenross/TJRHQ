-- Migration 0133: tighten physical_readiness_profiles RLS to authenticated-only
--
-- Follow-up to the 2026-08-09 Human Systems Workbench fix
-- (.claude/skills/bot-reviews/fixes-2026-08-09/human-systems-fixes.md), which
-- explicitly flagged physical_readiness_profiles as out of scope: "still
-- `public`-role with `USING (true)` on all 3 policies, live. Not one of the 9
-- tables the review scoped this finding to... a real drift, but a different
-- finding than the one assigned."
--
-- Re-verified live (project cjvrpjwewsrumnbdydgg) on 2026-08-10 via
-- pg_policies + information_schema.role_table_grants: confirmed still true —
-- all three policies (physical_readiness_profiles_select/_insert/_update) are
-- `{public}`-role with `USING (true)`/`WITH CHECK (true)`, byte-identical to
-- how 0068_physical_readiness.sql created them (0068's own header documents
-- this as a deliberate MVP shortcut: "Single-user system; RLS policies are
-- permissive `true` checks"). Unlike its sibling tables
-- (physical_readiness_checkins, physical_workout_sessions,
-- physical_workout_exercise_logs — tightened live 2026-07-17, tracked
-- retroactively in 0106_tighten_physical_readiness_workout_rls.sql),
-- physical_readiness_profiles was never tightened. `anon` currently holds
-- table-level SELECT/INSERT/UPDATE grants (standard Supabase schema default)
-- with no RLS policy restricting the role, so this table is genuinely
-- read/write-able by unauthenticated API callers today.
--
-- Fix: same pattern as 0106 — same policy names, same operations
-- (SELECT/INSERT/UPDATE, still no DELETE policy — matches original 0068,
-- never had one), same `USING (true)`/`WITH CHECK (true)` semantics, only the
-- role scope narrows from unrestricted/public to `authenticated`. This IS a
-- live state change (unlike 0106/0105/0110/0111, which only caught up
-- tracked history to an already-correct live state).
--
-- Idempotent (drop-then-create).

ALTER TABLE physical_readiness_profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "physical_readiness_profiles_select" ON physical_readiness_profiles;
DROP POLICY IF EXISTS "physical_readiness_profiles_insert" ON physical_readiness_profiles;
DROP POLICY IF EXISTS "physical_readiness_profiles_update" ON physical_readiness_profiles;

CREATE POLICY "physical_readiness_profiles_select"
  ON physical_readiness_profiles FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY "physical_readiness_profiles_insert"
  ON physical_readiness_profiles FOR INSERT
  TO authenticated
  WITH CHECK (true);

CREATE POLICY "physical_readiness_profiles_update"
  ON physical_readiness_profiles FOR UPDATE
  TO authenticated
  USING (true)
  WITH CHECK (true);
