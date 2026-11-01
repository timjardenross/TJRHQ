-- Command Memory key-value decision records (~100/day 400s on
-- /rest/v1/decisions, "column decisions.statement/rationale/owner does
-- not exist").
--
-- Background: the applied migration 0plain create_decisions_table
-- (20260608) created public.decisions with this exact shape (id text,
-- statement, rationale, owner, status, created_by, created_at,
-- alternatives, updated_at, updated_by). public.decisions was later
-- dropped and recreated outside the migration system with a completely
-- different shape (id uuid, mission_id, decision_type, reasoning,
-- outcome, artifacts, error_message, timestamp, outcome_quality,
-- quality_notes, quality_rated_at) — it holds 65 real rows and is left
-- alone by this migration.
--
-- ~45 platform-runtime modules (EXEC-002A..EXEC-007) never adapted to
-- that shape change: they still use the original shape as an
-- owner-prefix key-value store (initiative:, dep_link:, capability:,
-- officer_schedule:, lesson_candidate:, investigation:,
-- improvement_backlog:, ...) and have never written a row against the
-- live table, hence the 400s. No existing table fits (decision_records
-- and commander_decisions have different meanings) — this migration
-- gives those 45 callers back the original shape under its own name.
--
-- id is text, not uuid: callers mint their own "DEC-…"-style ids, not
-- gen_random_uuid() (the default only covers a caller that doesn't).
-- decision_type is included even though it's not part of the original
-- decisions shape because some of the KV writers set it as part of
-- their owner-prefixed record. status is free text (not an enum)
-- because callers define their own per-domain status vocabularies
-- (e.g. "investigation:" rows vs "capability:" rows use different
-- status sets) and a shared enum would need to be a superset of all of
-- them with no enforcement value.

CREATE TABLE IF NOT EXISTS public.command_memory_records (
  id            text        PRIMARY KEY DEFAULT gen_random_uuid()::text,
  owner         text,
  statement     text,
  rationale     text,
  status        text,
  decision_type text,
  alternatives  jsonb,
  created_by    text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz DEFAULT now(),
  updated_by    text
);

CREATE INDEX IF NOT EXISTS idx_command_memory_records_owner
  ON public.command_memory_records (owner text_pattern_ops);
CREATE INDEX IF NOT EXISTS idx_command_memory_records_created_at
  ON public.command_memory_records (created_at DESC);

ALTER TABLE public.command_memory_records ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.command_memory_records FROM anon;

CREATE POLICY "command_memory_records_service_role" ON public.command_memory_records
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "auth_read" ON public.command_memory_records
  FOR SELECT TO authenticated USING (true);
