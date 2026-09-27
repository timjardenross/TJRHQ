-- Two unrelated designs share the name `decisions`:
--   * Sprint D learning loop (the table that actually exists): mission_id,
--     decision_type, reasoning, outcome, artifacts, "timestamp", +0011's
--     outcome_quality columns. uuid id.
--   * MSN-0040A Command Memory (tools/supabase/schema/MSN-0040A-Command-
--     Memory-Schema.sql): statement, rationale, owner, status, created_at…
--     with text `DEC-…` ids. Its CREATE TABLE IF NOT EXISTS no-op'd because
--     the learning-loop table already existed, so it was never created.
--
-- ~40 call sites in platform-runtime (officer schedules/handoffs/
-- escalations/follow-ups, investigation registry, improvement backlog and
-- scorecard, enterprise-architecture links, command_memory_integration)
-- use it as an owner-keyed store (`owner = 'officer_schedule:<id>'`,
-- `like 'initiative:%'`, …) and have failed on every call since — ~100
-- PostgREST 400s/day, and none of those features has ever persisted state
-- (Supabase usage review 2026-09-27). Captain's decision: merge the Command
-- Memory columns into the existing table rather than create a second one.
--
-- Rows are told apart by `owner`: Command Memory rows always set it,
-- learning-loop rows never do. Learning-loop readers (lib/comms/
-- opportunities.py, portal ai-context.ts and learning/route.ts) filter
-- `owner is null` in the same change.

-- Command Memory callers insert text ids (`DEC-YYYYMMDD-…`). Nothing
-- references decisions.id (no inbound FKs, no dependent views), so widen
-- it to text; existing uuids keep their value as text.
alter table decisions alter column id drop default;
alter table decisions alter column id type text using id::text;
alter table decisions alter column id set default gen_random_uuid()::text;

alter table decisions
  add column if not exists statement    text,
  add column if not exists rationale    text,
  add column if not exists owner        text,
  add column if not exists status       text,
  add column if not exists created_by   text,
  add column if not exists created_at   timestamptz default now(),
  add column if not exists updated_at   timestamptz,
  add column if not exists updated_by   text,
  add column if not exists alternatives jsonb;

-- Existing learning-loop rows: created_at = their own "timestamp" (UTC),
-- not the moment this migration ran.
update decisions
   set created_at = "timestamp" at time zone 'UTC'
 where owner is null and "timestamp" is not null;

-- Owner lookups are exact (`eq`) and prefix (`like 'x:%'`) — text_pattern_ops
-- serves both. created_at is the common sort key.
create index if not exists idx_decisions_owner      on decisions (owner text_pattern_ops);
create index if not exists idx_decisions_created_at on decisions (created_at desc);
