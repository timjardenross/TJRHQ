-- Migration 0100: reconcile advisory_sessions RLS with live reality
--
-- The committed migration (0034_advisory_sessions.sql) still defines
-- USING(true)/WITH CHECK(true) with no role restriction — a real anon-key
-- data leak per WORKBENCH-REVIEW.md finding C3. Live policies were already
-- fixed to {authenticated} at some point via an undocumented dashboard
-- change (confirmed 2026-08-08: pg_policies shows roles={authenticated}
-- on both SELECT and INSERT), but 0034's committed text never matched —
-- if this project's migrations were ever replayed from scratch, the leak
-- would silently reopen. This migration makes the committed history match
-- what's actually live, idempotently (DROP + recreate, so it's a no-op if
-- already correct).

DROP POLICY IF EXISTS "advisory_sessions_select" ON advisory_sessions;
DROP POLICY IF EXISTS "advisory_sessions_insert" ON advisory_sessions;

CREATE POLICY "advisory_sessions_select"
  ON advisory_sessions FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY "advisory_sessions_insert"
  ON advisory_sessions FOR INSERT
  TO authenticated
  WITH CHECK (true);
