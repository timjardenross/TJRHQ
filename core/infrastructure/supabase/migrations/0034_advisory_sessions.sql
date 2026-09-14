-- Migration 0034 — Advisory Sessions
-- Persists Consult and Board advisory sessions to Supabase.
-- Consult: one row per assistant reply, keyed by advisor_id.
-- Board: one row per board convening, result stored as JSONB.

CREATE TABLE IF NOT EXISTS advisory_sessions (
  id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at    timestamptz NOT NULL    DEFAULT now(),
  mode          text        NOT NULL    CHECK (mode IN ('consult', 'board')),
  advisor_id    text,                          -- consult: advisor slug; board: null
  question      text        NOT NULL,
  response      text,                          -- consult: assistant reply text
  result        jsonb,                         -- board: full AdvisoryResult JSON
  metadata      jsonb                          -- reserved for future fields
);

CREATE INDEX IF NOT EXISTS advisory_sessions_mode_created  ON advisory_sessions (mode, created_at DESC);
CREATE INDEX IF NOT EXISTS advisory_sessions_advisor       ON advisory_sessions (advisor_id, created_at DESC);

-- Read policy: anon can select own sessions (no user auth yet — open read within project)
--
-- SUPERSEDED 2026-07-18 (WORKBENCH-REVIEW finding C3) by
-- 0100_advisory_sessions_restrict_to_authenticated.sql, which drops these
-- two policies and recreates them restricted to `authenticated`. This
-- file is left as-applied (renaming/editing an already-run migration
-- changes nothing live) but 0100 is the authoritative current policy --
-- do not treat the `USING (true)` below as this table's live state.
-- tools/check_advisory_sessions_rls.py (added 2026-09-15 adversarial
-- review) checks the live pg_policies catalog directly so this drift
-- between "what 0034 says" and "what's actually applied" can't silently
-- reopen without being caught.
ALTER TABLE advisory_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "advisory_sessions_select" ON advisory_sessions
  FOR SELECT USING (true);

CREATE POLICY "advisory_sessions_insert" ON advisory_sessions
  FOR INSERT WITH CHECK (true);
