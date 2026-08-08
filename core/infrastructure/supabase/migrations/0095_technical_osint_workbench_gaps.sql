-- Migration 0095: Technical OSINT Workbench — close gaps vs TECHNICAL_OSINT_WORKBENCH.md
--
-- Additive only. Adds:
--   - intelligence_events.criticality_score (spec-defined, was missing)
--   - intelligence_events.affected_cves (spec-defined, schema-only — no extraction
--     pipeline exists yet to populate it)
--   - signal_corroboration (spec-defined — replaces source-network's in-memory
--     per-request title-overlap recompute with a real persisted table)
--   - signal_escalation_history (spec-defined — real audit trail; threat-assessment
--     currently computes escalation decisions live and discards them)
--   - source_reliability_snapshot (NOT in spec — required to make source-network's
--     "trending" real instead of the 2 hardcoded fake entries currently returned)
--   - validation_job_runs (NOT in spec — audit trail for the daily validation job,
--     per spec section 7 step 3 "log validation results for audit trail", which
--     had no persisted target before this)

-- ─── intelligence_events additions ───────────────────────────────────────

ALTER TABLE intelligence_events ADD COLUMN IF NOT EXISTS
  criticality_score NUMERIC(3, 2);

COMMENT ON COLUMN intelligence_events.criticality_score IS
  'Impact severity 0-1. No formula given in TECHNICAL_OSINT_WORKBENCH.md — '
  'computed as weighted blend of risk_rating + operational_relevance + '
  'banking_relevance + cps230_relevance boost (see backfill/validation job).';

ALTER TABLE intelligence_events ADD COLUMN IF NOT EXISTS
  affected_cves TEXT[];

COMMENT ON COLUMN intelligence_events.affected_cves IS
  'Related CVE IDs. Schema-only — no extraction pipeline populates this yet.';

-- ─── signal_corroboration ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS signal_corroboration (
  corroboration_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  signal_id UUID NOT NULL REFERENCES intelligence_events(event_id) ON DELETE CASCADE,
  corroborating_signal_id UUID NOT NULL REFERENCES intelligence_events(event_id) ON DELETE CASCADE,
  overlap_type VARCHAR(50) NOT NULL DEFAULT 'title_match',
  title_word_overlap INTEGER,
  confirmation_count INTEGER,
  created_at TIMESTAMPTZ DEFAULT now(),
  CONSTRAINT signal_corroboration_no_self CHECK (signal_id <> corroborating_signal_id)
);

COMMENT ON TABLE signal_corroboration IS
  'Persisted cross-signal corroboration (title-word overlap >= 2, same sector, '
  'within a ~3-day window). Replaces the technical workbench source-network '
  'route''s prior in-memory O(n^2) recompute-per-request.';

CREATE INDEX IF NOT EXISTS idx_signal_corroboration_signal
  ON signal_corroboration(signal_id, confirmation_count DESC);
CREATE INDEX IF NOT EXISTS idx_signal_corroboration_corroborating
  ON signal_corroboration(corroborating_signal_id);

-- ─── signal_escalation_history ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS signal_escalation_history (
  escalation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  signal_id UUID NOT NULL REFERENCES intelligence_events(event_id) ON DELETE CASCADE,
  probability VARCHAR(10),
  impact VARCHAR(10),
  confidence VARCHAR(10),
  escalation_decision VARCHAR(20),
  reason TEXT,
  escalated_by VARCHAR(50) DEFAULT 'system',
  escalated_at TIMESTAMPTZ DEFAULT now()
);

COMMENT ON TABLE signal_escalation_history IS
  'Audit trail of escalation decisions. Written by the daily validation job '
  'only when a signal''s escalation_decision changes from its last logged '
  'value — not on every threat-assessment page read.';

CREATE INDEX IF NOT EXISTS idx_signal_escalation_history_signal
  ON signal_escalation_history(signal_id, escalated_at DESC);

-- ─── source_reliability_snapshot (new — enables real trending) ───────────

CREATE TABLE IF NOT EXISTS source_reliability_snapshot (
  snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID NOT NULL REFERENCES intelligence_source_registry(source_id) ON DELETE CASCADE,
  reliability_score NUMERIC(4, 3) NOT NULL,
  reliability_tier TEXT NOT NULL,
  accuracy_ratio NUMERIC(3, 2),
  false_positive_rate NUMERIC(3, 2),
  accuracy_sample_size INTEGER,
  snapshotted_at TIMESTAMPTZ DEFAULT now()
);

COMMENT ON TABLE source_reliability_snapshot IS
  'One row per source per daily validation-job run. Lets source-network report '
  'real 30-day trending instead of hardcoded placeholder data — until 30 days '
  'of history accumulate, trending reports insufficient_data honestly.';

CREATE INDEX IF NOT EXISTS idx_source_reliability_snapshot_source_time
  ON source_reliability_snapshot(source_id, snapshotted_at DESC);

-- ─── validation_job_runs (new — audit log for the daily job) ─────────────

CREATE TABLE IF NOT EXISTS validation_job_runs (
  run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  started_at TIMESTAMPTZ NOT NULL,
  completed_at TIMESTAMPTZ,
  sources_updated INTEGER DEFAULT 0,
  events_validated INTEGER DEFAULT 0,
  signals_confidence_recomputed INTEGER DEFAULT 0,
  signals_rank_recomputed INTEGER DEFAULT 0,
  snapshots_inserted INTEGER DEFAULT 0,
  escalations_logged INTEGER DEFAULT 0,
  errors INTEGER DEFAULT 0,
  status TEXT DEFAULT 'running',
  error_detail TEXT
);

COMMENT ON TABLE validation_job_runs IS
  'Audit trail for the daily source-accuracy validation job (spec section 7 '
  'step 3). Previously only logged to journald with no persisted record.';

CREATE INDEX IF NOT EXISTS idx_validation_job_runs_started
  ON validation_job_runs(started_at DESC);

-- ─── RLS: enable + authenticated-read on all 4 new tables ────────────────

ALTER TABLE signal_corroboration ENABLE ROW LEVEL SECURITY;
ALTER TABLE signal_escalation_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE source_reliability_snapshot ENABLE ROW LEVEL SECURITY;
ALTER TABLE validation_job_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated can read signal_corroboration"
  ON signal_corroboration FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated can read signal_escalation_history"
  ON signal_escalation_history FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated can read source_reliability_snapshot"
  ON source_reliability_snapshot FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated can read validation_job_runs"
  ON validation_job_runs FOR SELECT USING (auth.role() = 'authenticated');

GRANT SELECT ON signal_corroboration, signal_escalation_history, source_reliability_snapshot, validation_job_runs TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON signal_corroboration, signal_escalation_history, source_reliability_snapshot, validation_job_runs TO service_role;

-- ─── Done ─────────────────────────────────────────────────────────────────
