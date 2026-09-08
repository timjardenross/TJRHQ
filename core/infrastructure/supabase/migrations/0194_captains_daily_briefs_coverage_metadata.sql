-- 0194_captains_daily_briefs_coverage_metadata.sql
-- HQ V1 Integration QA §21 (Deferred Gap I7): the Captain's Daily Brief —
-- the artifact TJR actually reads each morning — computed no coverage/
-- evidence-cutoff metadata anywhere in its pipeline, unlike the separate
-- OSINT intelligence_briefs pipeline (period_start/period_end + the
-- sources_checked/sources_available/sources_failed/sources_stale columns
-- already surfaced this mission, migration 0004). A Captain could not tell
-- "this brief covers everything up to X" from "this brief is missing
-- recent signals because collection lagged."
--
-- evidence_window_hours: the lookback window actually used to gather
--   signals for this brief (e.g. 24 for morning/eod, 168 for weekly) —
--   answers "how far back does this brief's evidence go."
-- collection_caveat: non-null only when a positive signal exists that the
--   feeding collection job did not complete successfully before this brief
--   generated (e.g. intelligence_collection's heartbeat wasn't 'ok' as of
--   generation time) — answers "is this brief's evidence actually
--   complete, or might collection have lagged."
--
-- Both nullable/additive — existing rows read back as NULL (unknown),
-- never as a false "fully covered" claim.

ALTER TABLE captains_daily_briefs
    ADD COLUMN IF NOT EXISTS evidence_window_hours integer,
    ADD COLUMN IF NOT EXISTS collection_caveat text;

COMMENT ON COLUMN captains_daily_briefs.evidence_window_hours IS
  'Lookback window (hours) actually used to gather signals for this brief. NULL for pre-migration rows and brief types that do not use a signals window (e.g. knowledge_ops).';

COMMENT ON COLUMN captains_daily_briefs.collection_caveat IS
  'Non-null only when the feeding collection job (e.g. intelligence_collection for the morning brief) showed a positive failure/staleness signal as of generation time — never fabricated as healthy when unknown.';
