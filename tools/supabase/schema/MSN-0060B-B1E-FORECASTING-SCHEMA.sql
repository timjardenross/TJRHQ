-- MSN-0060B Phase B1E: Quality Forecasting Schema
-- Forecasts provider effectiveness and detects anomalies
-- Enables proactive routing decisions

-- Design: Minimal MVP
-- - Time-series effectiveness forecasting
-- - Statistical trend analysis
-- - Anomaly detection
-- - Forecast confidence levels
-- - Defers advanced ML to B1F

-- ============================================================================
-- Table: quality_forecasts
-- Purpose: Store effectiveness forecasts for providers
-- Cardinality: 1 row per forecast per provider per time period
-- RLS: Enabled (backend-only access via SERVICE_ROLE_KEY)
-- ============================================================================

CREATE TABLE IF NOT EXISTS quality_forecasts (
  -- Identity
  id TEXT PRIMARY KEY,                          -- FOR-YYYYMMDD-HHMMSS
  provider_name TEXT NOT NULL,                  -- Google, OpenRouter, Ollama
  model_name TEXT,                              -- Gemini, Mistral, Qwen
  provider_route TEXT,                          -- Primary, Fallback, Local

  -- Forecast
  forecast_horizon INTEGER NOT NULL,            -- Decisions ahead (e.g., 5)
  predicted_effectiveness NUMERIC(2,1) NOT NULL,-- Forecasted score (1.0-5.0)
  confidence_level TEXT NOT NULL,               -- high, medium, low
  confidence_band_lower NUMERIC(2,1),           -- Lower bound (1.0-5.0)
  confidence_band_upper NUMERIC(2,1),           -- Upper bound (1.0-5.0)

  -- Trend
  trend_direction TEXT,                         -- up, down, stable
  trend_persistence NUMERIC(3,2),               -- 0-1, likelihood continues

  -- Quality metrics
  forecast_accuracy NUMERIC(3,2),               -- R² from regression
  decisions_used INTEGER,                       -- Data points in forecast

  -- Timestamps
  forecast_timestamp TIMESTAMPTZ NOT NULL,      -- When forecast generated
  created_at TIMESTAMPTZ DEFAULT NOW(),         -- When recorded

  -- Constraints
  CHECK (confidence_level IN ('high', 'medium', 'low')),
  CHECK (trend_direction IN ('up', 'down', 'stable')),
  CHECK (predicted_effectiveness >= 1.0 AND predicted_effectiveness <= 5.0)
);

-- Enable Row-Level Security (backend-only access model)
ALTER TABLE quality_forecasts ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Implicit deny (no policies = backend-only)

-- ============================================================================
-- Table: quality_anomalies
-- Purpose: Record detected quality anomalies
-- Cardinality: Multiple anomalies per provider
-- RLS: Enabled (backend-only access via SERVICE_ROLE_KEY)
-- ============================================================================

CREATE TABLE IF NOT EXISTS quality_anomalies (
  -- Identity
  id TEXT PRIMARY KEY,                          -- ANO-YYYYMMDD-HHMMSS
  provider_name TEXT NOT NULL,                  -- Google, OpenRouter, Ollama
  model_name TEXT,                              -- Gemini, Mistral, Qwen
  provider_route TEXT,                          -- Primary, Fallback, Local
  score_id TEXT,                                -- FK to quality_scores (optional)

  -- Anomaly details
  score_value NUMERIC(2,1) NOT NULL,            -- The anomalous score
  anomaly_type TEXT NOT NULL,                   -- outlier, trend_change, degradation
  z_score NUMERIC(5,2) NOT NULL,                -- Standard deviations from mean
  severity TEXT NOT NULL,                       -- low, medium, high

  -- Timestamps
  detected_at TIMESTAMPTZ NOT NULL,             -- When anomaly detected
  created_at TIMESTAMPTZ DEFAULT NOW(),         -- When recorded

  -- Constraints
  CHECK (anomaly_type IN ('outlier', 'trend_change', 'degradation')),
  CHECK (severity IN ('low', 'medium', 'high')),
  FOREIGN KEY (score_id) REFERENCES quality_scores(id) ON DELETE SET NULL
);

-- Enable Row-Level Security (backend-only access model)
ALTER TABLE quality_anomalies ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Implicit deny (no policies = backend-only)

-- ============================================================================
-- Indexes: Query optimization for common access patterns
-- ============================================================================

-- Index 1: Find forecasts by provider (forecast lookup)
CREATE INDEX IF NOT EXISTS idx_forecast_provider
  ON quality_forecasts(provider_name);

-- Index 2: Find forecasts by confidence (routing decisions)
CREATE INDEX IF NOT EXISTS idx_forecast_confidence
  ON quality_forecasts(confidence_level);

-- Index 3: Find forecasts by trend (trend analysis)
CREATE INDEX IF NOT EXISTS idx_forecast_trend
  ON quality_forecasts(trend_direction);

-- Index 4: Find recent forecasts (monitoring)
CREATE INDEX IF NOT EXISTS idx_forecast_timestamp
  ON quality_forecasts(forecast_timestamp DESC);

-- Index 5: Find anomalies by provider (anomaly analysis)
CREATE INDEX IF NOT EXISTS idx_anomaly_provider
  ON quality_anomalies(provider_name);

-- Index 6: Find anomalies by severity (alert filtering)
CREATE INDEX IF NOT EXISTS idx_anomaly_severity
  ON quality_anomalies(severity);

-- Index 7: Find anomalies by type (pattern analysis)
CREATE INDEX IF NOT EXISTS idx_anomaly_type
  ON quality_anomalies(anomaly_type);

-- Index 8: Link anomalies to quality scores
CREATE INDEX IF NOT EXISTS idx_anomaly_score
  ON quality_anomalies(score_id);

-- ============================================================================
-- Views: Read-only consolidated views for analysis
-- ============================================================================

-- View: Provider forecast with current quality
-- Shows predicted effectiveness alongside current metrics
CREATE OR REPLACE VIEW v_provider_forecast AS
  SELECT
    qf.provider_name,
    qf.model_name,
    qf.provider_route,
    qf.predicted_effectiveness as forecast_score,
    qf.confidence_level,
    qf.confidence_band_lower,
    qf.confidence_band_upper,
    qf.trend_direction,
    qf.trend_persistence,
    pqh.avg_effectiveness as current_score,
    CASE
      WHEN qf.predicted_effectiveness > pqh.avg_effectiveness + 0.5 THEN 'improving'
      WHEN qf.predicted_effectiveness < pqh.avg_effectiveness - 0.5 THEN 'declining'
      ELSE 'stable'
    END as forecast_direction,
    qf.forecast_accuracy,
    qf.decisions_used,
    qf.forecast_timestamp
  FROM quality_forecasts qf
  LEFT JOIN provider_quality_history pqh
    ON qf.provider_name = pqh.provider_name
    AND qf.model_name = pqh.model_name
    AND qf.provider_route = pqh.provider_route
  ORDER BY qf.predicted_effectiveness DESC;

-- View: Anomaly summary by provider
-- Shows recent anomalies and severity distribution
CREATE OR REPLACE VIEW v_anomaly_summary AS
  SELECT
    provider_name,
    COUNT(*) AS total_anomalies,
    COUNT(CASE WHEN severity = 'high' THEN 1 END) AS high_severity,
    COUNT(CASE WHEN severity = 'medium' THEN 1 END) AS medium_severity,
    COUNT(CASE WHEN severity = 'low' THEN 1 END) AS low_severity,
    COUNT(CASE WHEN anomaly_type = 'degradation' THEN 1 END) AS degradations,
    COUNT(CASE WHEN anomaly_type = 'outlier' THEN 1 END) AS outliers,
    MAX(detected_at) AS latest_anomaly
  FROM quality_anomalies
  GROUP BY provider_name
  ORDER BY latest_anomaly DESC;

-- View: Recommended proactive routing
-- Shows provider ranking by forecast with confidence
CREATE OR REPLACE VIEW v_proactive_routing AS
  SELECT
    ROW_NUMBER() OVER (ORDER BY predicted_effectiveness DESC) as route_priority,
    provider_name,
    model_name,
    provider_route,
    predicted_effectiveness as forecast_quality,
    confidence_level,
    trend_direction,
    forecast_accuracy,
    CASE
      WHEN confidence_level = 'high' THEN 'high_confidence'
      WHEN confidence_level = 'medium' THEN 'medium_confidence'
      ELSE 'low_confidence'
    END as routing_note,
    forecast_timestamp
  FROM quality_forecasts
  WHERE decisions_used >= 5  -- Only recommend with sufficient data
  ORDER BY predicted_effectiveness DESC;

-- ============================================================================
-- Comments: Documentation
-- ============================================================================

COMMENT ON TABLE quality_forecasts IS 'B1E Phase: Quality Forecasting. Forecasts provider effectiveness for future decisions. Used for proactive routing decisions.';

COMMENT ON COLUMN quality_forecasts.id IS 'Canonical forecast ID: FOR-YYYYMMDD-HHMMSS. Unique, sortable, human-readable.';

COMMENT ON COLUMN quality_forecasts.predicted_effectiveness IS 'Forecasted effectiveness score (1.0-5.0). Predicted using linear regression on historical scores.';

COMMENT ON COLUMN quality_forecasts.confidence_level IS 'Forecast confidence: high (20+ decisions), medium (10-20), low (<10). Reflects data volume and forecast reliability.';

COMMENT ON COLUMN quality_forecasts.trend_direction IS 'Quality trend: up (improving), down (declining), stable (consistent). Indicates direction of change.';

COMMENT ON COLUMN quality_forecasts.trend_persistence IS 'Probability (0-1) that trend continues. Higher = stronger confidence trend persists.';

COMMENT ON COLUMN quality_forecasts.forecast_accuracy IS 'R² value from linear regression. Measures how well trend explains historical data (0-1, higher = better).';

COMMENT ON TABLE quality_anomalies IS 'B1E Phase: Anomaly Detection. Records detected quality outliers and deviations. Used for alerting and investigation.';

COMMENT ON COLUMN quality_anomalies.score_value IS 'The anomalous score value (1.0-5.0).';

COMMENT ON COLUMN quality_anomalies.anomaly_type IS 'Type of anomaly: outlier (single unusual score), trend_change (direction reversal), degradation (sustained drop).';

COMMENT ON COLUMN quality_anomalies.z_score IS 'Standard deviations from mean. |z| > 2.0 = 95% confidence anomaly. |z| > 3.0 = 99.7% confidence.';

COMMENT ON COLUMN quality_anomalies.severity IS 'Anomaly severity: low (|z| 2.0-2.5), medium (2.5-3.0), high (>3.0).';

-- ============================================================================
-- Permissions: Backend-only access (RLS implicit deny)
-- ============================================================================

-- Only SERVICE_ROLE_KEY can access (backend only)
-- ANON_KEY cannot access these tables (intentional security model)

-- ============================================================================
-- B1E Minimal Acceptance Criteria
-- ============================================================================

/*
Acceptance Criteria:
✅ Effectiveness Forecasting
   - Predicts next 5 decisions' quality
   - Calculates confidence bands
   - Validates forecast accuracy vs. actuals
✅ Trend Analysis
   - Detects quality trends (improving/declining/stable)
   - Calculates trend persistence (likelihood to continue)
   - Statistical significance testing
✅ Anomaly Detection
   - Identifies outlier scores
   - Flags unexpected quality changes
   - Alerts on significant deviations
✅ Forecast Confidence
   - Quality varies by sample size (low confidence with <5 decisions)
   - Wider bands with less data
   - Confidence levels communicated in routing
✅ Integrated Quality Tier Updates
   - Forecast confidence affects quality tier assignment
   - Predicted trends visible in routing decisions
   - Future quality visible for planning
✅ 25+ Tests Passing
   - Unit tests for forecasting algorithms
   - Integration tests for forecast accuracy
   - Regression tests (B1A/B1B/B1C/B1D all operational)
✅ Ready for B1F
   - Forecast data available for cost analysis
   - Trend information ready for optimization
   - No blocking dependencies for B1F
*/

-- ============================================================================
-- Schema Version and Migration Tracking
-- ============================================================================

-- B1E Deployment metadata (for audit trail)
-- Marker: MSN-0060B-B1E-FORECASTING-SCHEMA
-- Version: 1.0 (Minimal MVP)
-- Date: 2026-06-10
-- Author: Captain TJR
-- Status: Ready for implementation and testing
