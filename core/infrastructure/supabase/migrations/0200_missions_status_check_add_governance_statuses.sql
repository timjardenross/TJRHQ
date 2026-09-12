-- ============================================================================
-- Migration 0200 -- missions: document the live missions_status_check
-- constraint in the migration trail (issue #187)
-- ============================================================================
-- Purpose:
--   Issue #187 reported that platform-runtime/commands/mission_lifecycle.py's
--   _VALID_TRANSITIONS accepts 4 statuses ('Approved for Engineering',
--   'Awaiting Captain Approval', 'Approved', 'Requires Rework') that no
--   migration file up through 0199 adds to missions_status_check --
--   correct as far as the migration *files* go; migration 0013 is indeed
--   the last one to touch that constraint on paper.
--
--   Checked the LIVE constraint directly (2026-09-12, project
--   cjvrpjwewsrumnbdydgg) before writing this migration to apply it, and
--   found it already contains all 14 statuses, this migration's ALTER
--   included -- someone applied this exact change directly against the
--   database at some point without a corresponding migration file ever
--   landing in the repo. So the live schema was never actually broken;
--   the migration *history* was the thing out of sync with reality. This
--   file closes that gap (and is itself a no-op against the live DB --
--   DROP IF EXISTS + an identical ADD CONSTRAINT) so a future
--   `supabase db diff` / fresh restore doesn't silently regress a schema
--   that's already correct in production.
--
--   For the record, the 4 statuses issue #187 asked to adjudicate on ARE
--   real, active, currently-relied-upon governance states, not
--   aspirational ones from an unfinished redesign -- confirmed via real
--   callers, not guessed, before treating "add to schema" as the right of
--   the two possible fixes:
--     - core/engineering/mission_dispatch.py: APPROVED_STATUS =
--       "Approved for Engineering" is the literal trigger constant that
--       fires engineering dispatch when a mission reaches that status.
--     - lcars-portal/src/lib/missionStatus.ts: both
--       'Approved for Engineering' and 'Requires Rework' are in its
--       canonical status list; AWAITING_CAPTAIN_STATUSES explicitly
--       includes 'Awaiting Captain Approval' as a real UI-facing state.
--     - Real Engineering-Handoff records under Missions/Engineering-
--       Handoffs/ already reference these statuses in production data.
--   So the schema is what the migration *files* had fallen behind on, not
--   the code -- extending the constraint (not narrowing
--   _VALID_TRANSITIONS) is confirmed as the correct fix, even though it
--   turned out to already be live.
--
-- Apply via Supabase SQL Editor or psql (safe to run even though the live
-- constraint already matches -- idempotent).
-- ============================================================================

ALTER TABLE missions DROP CONSTRAINT IF EXISTS missions_status_check;

ALTER TABLE missions
  ADD CONSTRAINT missions_status_check
  CHECK (status IN (
    'Idea',
    'Designed',
    'Approved for Engineering',
    'Implemented',
    'Tested',
    'Awaiting Number One Review',
    'Validated',
    'Awaiting XO Approval',
    'Awaiting Captain Approval',
    'Approved',
    'Closed',
    'Blocked',
    'Archived',
    'Requires Rework'
  ));
