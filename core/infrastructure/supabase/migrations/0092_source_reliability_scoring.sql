-- ============================================================
-- Migration 0092 — Source Reliability Scoring (SRS) Framework
-- Adds accuracy tracking + computed reliability tiering to
-- intelligence_source_registry, and an event validation log.
-- ============================================================

-- ─── 1. SRS columns on intelligence_source_registry ────────────────────────
ALTER TABLE intelligence_source_registry ADD COLUMN IF NOT EXISTS
  accuracy_ratio NUMERIC(3, 2) DEFAULT 0.50;

ALTER TABLE intelligence_source_registry ADD COLUMN IF NOT EXISTS
  false_positive_rate NUMERIC(3, 2) DEFAULT 0.20;

ALTER TABLE intelligence_source_registry ADD COLUMN IF NOT EXISTS
  reliability_score NUMERIC(3, 2) GENERATED ALWAYS AS (
    ROUND((confidence_weight * accuracy_ratio * (1.0 - false_positive_rate))::NUMERIC, 2)
  ) STORED;

ALTER TABLE intelligence_source_registry ADD COLUMN IF NOT EXISTS
  reliability_tier TEXT GENERATED ALWAYS AS (
    CASE
      WHEN (confidence_weight * accuracy_ratio * (1.0 - false_positive_rate)) > 0.85 THEN 'TIER_1'
      WHEN (confidence_weight * accuracy_ratio * (1.0 - false_positive_rate)) > 0.70 THEN 'TIER_2'
      WHEN (confidence_weight * accuracy_ratio * (1.0 - false_positive_rate)) > 0.50 THEN 'TIER_3'
      ELSE 'TIER_4'
    END
  ) STORED;

ALTER TABLE intelligence_source_registry ADD COLUMN IF NOT EXISTS
  accuracy_sample_size INT DEFAULT 0;

ALTER TABLE intelligence_source_registry ADD COLUMN IF NOT EXISTS
  accuracy_last_updated TIMESTAMPTZ DEFAULT NULL;

-- ─── 2. Event validation tracking table ────────────────────────────────────
CREATE TABLE IF NOT EXISTS intelligence_event_validation (
  validation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id UUID NOT NULL REFERENCES intelligence_events(event_id) ON DELETE CASCADE,
  source_id UUID NOT NULL REFERENCES intelligence_source_registry(source_id) ON DELETE CASCADE,
  is_accurate BOOLEAN,
  validation_method TEXT,
  validation_detail TEXT,
  event_published_at TIMESTAMPTZ NOT NULL,
  validated_at TIMESTAMPTZ DEFAULT NOW(),
  validated_by TEXT DEFAULT 'system'
);

CREATE INDEX IF NOT EXISTS idx_intelligence_event_validation_source
  ON intelligence_event_validation(source_id, validated_at DESC);

CREATE INDEX IF NOT EXISTS idx_intelligence_event_validation_accuracy
  ON intelligence_event_validation(source_id, is_accurate);

-- ─── 3. Reporting view ──────────────────────────────────────────────────────
CREATE OR REPLACE VIEW source_registry_by_tier AS
  SELECT source_id, source_name, category, priority_rank,
         reliability_score, reliability_tier, accuracy_ratio,
         false_positive_rate, accuracy_sample_size, accuracy_last_updated, active
  FROM intelligence_source_registry
  WHERE active = true
  ORDER BY reliability_tier, reliability_score DESC;

-- NOTE: with defaults (accuracy_ratio=0.50, false_positive_rate=0.20), max
-- possible reliability_score is 0.97*0.5*0.8=0.388 — every source starts in
-- TIER_4 until intelligence_event_validation rows accumulate and
-- accuracy_ratio is recomputed from real data. Expected, not a bug.
