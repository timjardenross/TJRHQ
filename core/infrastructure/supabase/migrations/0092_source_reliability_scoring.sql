-- Migration 0092: Source Reliability Scoring (SRS) Framework
--
-- Adds columns to track and compute source reliability dynamically.
-- Enables auto-scoring of which sources are accurate vs noisy.
--
-- Run this migration to enable the SRS framework.

-- ─── Add SRS columns to intelligence_source_registry ─────────────────────────

ALTER TABLE intelligence_source_registry ADD COLUMN IF NOT EXISTS
  accuracy_ratio NUMERIC(3, 2) DEFAULT 0.50;

COMMENT ON COLUMN intelligence_source_registry.accuracy_ratio IS
  'Proportion of events from this source that were verified accurate (0.0–1.0). '
  'Auto-calculated daily from intelligence_event_validation. Default: 0.50 (unknown).';

ALTER TABLE intelligence_source_registry ADD COLUMN IF NOT EXISTS
  false_positive_rate NUMERIC(3, 2) DEFAULT 0.20;

COMMENT ON COLUMN intelligence_source_registry.false_positive_rate IS
  'Proportion of events from this source that were false positives (0.0–1.0). '
  'Auto-calculated daily from intelligence_event_validation. Default: 0.20 (conservative estimate).';

ALTER TABLE intelligence_source_registry ADD COLUMN IF NOT EXISTS
  reliability_score NUMERIC(3, 2) GENERATED ALWAYS AS (
    ROUND((confidence_weight * accuracy_ratio * (1.0 - false_positive_rate))::NUMERIC, 2)
  ) STORED;

COMMENT ON COLUMN intelligence_source_registry.reliability_score IS
  'Composite SRS score = base_confidence × accuracy_ratio × (1 - fp_rate). '
  'Ranges 0.0–1.0. GENERATED ALWAYS AS (cannot be manually set).';

ALTER TABLE intelligence_source_registry ADD COLUMN IF NOT EXISTS
  reliability_tier TEXT GENERATED ALWAYS AS (
    CASE
      WHEN (confidence_weight * accuracy_ratio * (1.0 - false_positive_rate)) > 0.85 THEN 'TIER_1'
      WHEN (confidence_weight * accuracy_ratio * (1.0 - false_positive_rate)) > 0.70 THEN 'TIER_2'
      WHEN (confidence_weight * accuracy_ratio * (1.0 - false_positive_rate)) > 0.50 THEN 'TIER_3'
      ELSE 'TIER_4'
    END
  ) STORED;

COMMENT ON COLUMN intelligence_source_registry.reliability_tier IS
  'Auto-tier based on SRS: TIER_1=always use, TIER_2=secondary, TIER_3=de-emphasize, TIER_4=archive.';

ALTER TABLE intelligence_source_registry ADD COLUMN IF NOT EXISTS
  accuracy_sample_size INT DEFAULT 0;

COMMENT ON COLUMN intelligence_source_registry.accuracy_sample_size IS
  'Number of events used to calculate accuracy_ratio (need ≥10 for meaningful score).';

ALTER TABLE intelligence_source_registry ADD COLUMN IF NOT EXISTS
  accuracy_last_updated TIMESTAMPTZ DEFAULT NULL;

COMMENT ON COLUMN intelligence_source_registry.accuracy_last_updated IS
  'Timestamp when accuracy_ratio and false_positive_rate were last computed.';

-- ─── Create event validation tracking table ────────────────────────────────

CREATE TABLE IF NOT EXISTS intelligence_event_validation (
  validation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id UUID NOT NULL REFERENCES intelligence_events(event_id) ON DELETE CASCADE,
  source_id UUID NOT NULL REFERENCES intelligence_source_registry(source_id) ON DELETE CASCADE,

  -- Validation result
  is_accurate BOOLEAN,  -- NULL = unknown, true = verified accurate, false = false positive

  -- Why was this accurate/inaccurate?
  validation_method TEXT,  -- 'internal_logs' | 'customer_report' | 'no_evidence' | 'manual_review'
  validation_detail TEXT,  -- e.g., "Found matching error in CloudWatch logs at 2026-08-07 08:45"

  -- Timestamps
  event_published_at TIMESTAMPTZ NOT NULL,
  validated_at TIMESTAMPTZ DEFAULT NOW(),

  -- Audit
  validated_by TEXT DEFAULT 'system'  -- 'system' | 'manual_review' | user_email
);

COMMENT ON TABLE intelligence_event_validation IS
  'Tracks validation of events from intelligence_events. '
  'Used to calculate accuracy_ratio and false_positive_rate for each source.';

CREATE INDEX IF NOT EXISTS idx_intelligence_event_validation_source
  ON intelligence_event_validation(source_id, validated_at DESC);

COMMENT ON INDEX idx_intelligence_event_validation_source IS
  'Fast lookup: accuracy data for a source ordered by recency.';

CREATE INDEX IF NOT EXISTS idx_intelligence_event_validation_accuracy
  ON intelligence_event_validation(source_id, is_accurate);

COMMENT ON INDEX idx_intelligence_event_validation_accuracy IS
  'Fast aggregation: true_positive and false_positive counts per source.';

CREATE INDEX IF NOT EXISTS idx_intelligence_event_validation_event
  ON intelligence_event_validation(event_id);

COMMENT ON INDEX idx_intelligence_event_validation_event IS
  'Lookup: validation status of a specific event.';

-- ─── View: Sources by reliability tier (for reporting) ──────────────────────

CREATE OR REPLACE VIEW source_registry_by_tier AS
  SELECT
    source_id,
    source_name,
    category,
    priority_rank,
    reliability_score,
    reliability_tier,
    accuracy_ratio,
    false_positive_rate,
    accuracy_sample_size,
    accuracy_last_updated,
    active
  FROM intelligence_source_registry
  WHERE active = true
  ORDER BY reliability_tier, reliability_score DESC;

COMMENT ON VIEW source_registry_by_tier IS
  'Quick look at which active sources are TIER_1 (high-reliability) vs TIER_4 (unreliable).';

-- ─── RLS: enable + authenticated-read policy on validation data ─────────────
-- NOTE (fix): the table must be RLS-enabled for any policy below to take
-- effect — Postgres lets you CREATE POLICY on a table with RLS still off,
-- and it silently does nothing while the table stays fully open to anon via
-- Supabase's default anon/authenticated grants. Also: auth.role() returns
-- 'authenticated', not 'authenticated_user' — the original condition below
-- would never have matched, so even with RLS on, no one (including
-- legitimate authenticated users) could have read this table.

ALTER TABLE intelligence_event_validation ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated can read event validations"
  ON intelligence_event_validation
  FOR SELECT
  USING (auth.role() = 'authenticated');

-- ─── Grant permissions ──────────────────────────────────────────────────────

GRANT SELECT, INSERT ON intelligence_event_validation TO service_role;
GRANT UPDATE ON intelligence_source_registry TO service_role;
GRANT SELECT ON source_registry_by_tier TO authenticated;

-- ─── Done ────────────────────────────────────────────────────────────────────

-- Test the schema:
-- SELECT source_name, reliability_score, reliability_tier, accuracy_sample_size
--   FROM intelligence_source_registry
--  WHERE active = true
--  ORDER BY reliability_score DESC
--  LIMIT 10;

-- NOTE: with defaults (accuracy_ratio=0.50, false_positive_rate=0.20), max
-- possible reliability_score is 0.97*0.5*0.8=0.388 — every source starts in
-- TIER_4 until intelligence_event_validation rows accumulate and
-- accuracy_ratio is recomputed from real data. Expected, not a bug.
