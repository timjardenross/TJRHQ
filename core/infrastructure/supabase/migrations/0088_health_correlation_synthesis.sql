-- ============================================================
-- Migration 0088 — Issue 18: LLM synthesis column on health correlations
-- USS Starship Endeavour NCC-170230
--
-- intelligence_health_correlations (0086) stores raw Pearson-correlation
-- output only. Issue 18 (correlation_synthesis.py) turns that into grounded
-- narrative insights; this adds somewhere to persist that result alongside
-- the numbers it was derived from.
--
-- Additive & idempotent. Safe to run repeatedly.
-- ============================================================

alter table intelligence_health_correlations
  add column if not exists synthesis jsonb;

comment on column intelligence_health_correlations.synthesis is
  'Issue 18: LLM narrative synthesis of the correlations row (insights, '
  'operational_implications, data_quality) from correlation_synthesis.'
  'synthesize_correlation_insights(). Null if synthesis was skipped '
  '(insufficient_data) or failed.';
