-- Migration 0215: reconcile debrief_sessions/debrief_logs/debrief_turns and
-- insight_outcomes RLS with a safe default — adversarial review 2026-09-15.
--
-- Live pg_policies showed debrief_sessions/debrief_logs/debrief_turns
-- granted to role {public} (Postgres PUBLIC pseudo-role = every role,
-- anon included) with USING(true)/WITH CHECK(true) — no committed
-- migration created these exact policy names, so this is undocumented
-- drift, same class as the advisory_sessions leak reconciled in 0100 but
-- in the unsafe direction: 0206_debrief_sessions_and_logs.sql's own
-- committed policies (debrief_sessions_service_write/_authenticated_read,
-- debrief_logs_service_write/_authenticated_read) were never what ended
-- up live. These tables hold voice-transcribed personal debrief content
-- (stressors, open_loops, transcript_text) — anon-readable/writable via
-- the client-exposed SUPABASE_ANON_KEY (lcars-portal). debrief_turns had
-- no RLS migration at all.
--
-- insight_outcomes (0062_insight_outcomes.sql) similarly grants
-- {public} ALL (SELECT/INSERT/UPDATE/DELETE) with USING(true)/WITH
-- CHECK(true) — anon can tamper with the quality-scoring outcome record
-- MSN-0210E's decision-quality loop reads.
--
-- xo bot reaches these tables via its scoped `xo_bot` Postgres role (or
-- the service_role bypass fallback — see telegram_bots/xo/app.py
-- _get_supabase()), so `xo_bot` is added explicitly rather than relying
-- on PUBLIC membership. Idempotent (DROP + recreate).

DROP POLICY IF EXISTS "debrief_sessions_select" ON debrief_sessions;
DROP POLICY IF EXISTS "debrief_sessions_insert" ON debrief_sessions;
DROP POLICY IF EXISTS "debrief_sessions_update" ON debrief_sessions;

CREATE POLICY "debrief_sessions_select"
  ON debrief_sessions FOR SELECT
  TO authenticated, xo_bot
  USING (true);

CREATE POLICY "debrief_sessions_insert"
  ON debrief_sessions FOR INSERT
  TO authenticated, xo_bot
  WITH CHECK (true);

CREATE POLICY "debrief_sessions_update"
  ON debrief_sessions FOR UPDATE
  TO authenticated, xo_bot
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS "debrief_logs_select" ON debrief_logs;
DROP POLICY IF EXISTS "debrief_logs_insert" ON debrief_logs;

CREATE POLICY "debrief_logs_select"
  ON debrief_logs FOR SELECT
  TO authenticated, xo_bot
  USING (true);

CREATE POLICY "debrief_logs_insert"
  ON debrief_logs FOR INSERT
  TO authenticated, xo_bot
  WITH CHECK (true);

DROP POLICY IF EXISTS "debrief_turns_select" ON debrief_turns;
DROP POLICY IF EXISTS "debrief_turns_insert" ON debrief_turns;

CREATE POLICY "debrief_turns_select"
  ON debrief_turns FOR SELECT
  TO authenticated, xo_bot
  USING (true);

CREATE POLICY "debrief_turns_insert"
  ON debrief_turns FOR INSERT
  TO authenticated, xo_bot
  WITH CHECK (true);

DROP POLICY IF EXISTS "insight_outcomes_all" ON insight_outcomes;

CREATE POLICY "insight_outcomes_service_write"
  ON insight_outcomes FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

CREATE POLICY "insight_outcomes_authenticated_read"
  ON insight_outcomes FOR SELECT
  TO authenticated
  USING (true);
