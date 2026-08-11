-- Health OSINT Phase 5 (curation UI): without a review-status column,
-- publish/reject were indistinguishable from "not yet reviewed" — both
-- leave the signal with suppressed=true or false, but the pending queue
-- (GET /api/health-osint-curation/pending) can only filter on auto_ingested
-- + suppressed, so a rejected signal would resurface on every page load
-- forever instead of dropping off the queue once decided.

ALTER TABLE health_signals ADD COLUMN IF NOT EXISTS
  auto_ingest_reviewed BOOLEAN DEFAULT false;

COMMENT ON COLUMN health_signals.auto_ingest_reviewed IS
  'true once a Captain has published or rejected this auto-ingested signal in the curation UI — false means still pending review. Irrelevant for non-auto-ingested signals.';

CREATE INDEX IF NOT EXISTS idx_health_signals_auto_ingest_pending
  ON health_signals(auto_ingested, auto_ingest_reviewed, collected_at DESC)
  WHERE auto_ingested = true;
