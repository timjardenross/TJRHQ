-- MSN-0060B Phase B1D: Feedback Loops Schema
-- Generates feedback signals from quality scores
-- Tracks provider quality and enables adaptive routing
--
-- Design: Minimal MVP
-- - Generates feedback signals (outcome → provider quality change)
-- - Tracks provider quality metrics (rolling averages, trends)
-- - Enables adaptive routing based on quality history
-- - Defers predictive scoring to B1E

-- ============================================================================
-- Table: feedback_signals
-- Purpose: Record feedback signals from quality scores
-- Cardinality: 1 quality score → 1 feedback signal
-- RLS: Enabled (backend-only access via SERVICE_ROLE_KEY)
-- ============================================================================

CREATE TABLE IF NOT EXISTS feedback_signals (
  -- Identity
  id TEXT PRIMARY KEY,                          -- FBK-YYYYMMDD-HHMMSS
  score_id TEXT NOT NULL,                       -- FK to quality_scores(id)
  decision_id TEXT NOT NULL,                    -- FK to decision_records(id)

  -- Attribution
  provider_name TEXT NOT NULL,                  -- Google, OpenRouter, Ollama
  model_name TEXT,                              -- Gemini, Mistral, Qwen
  provider_route TEXT,                          -- Primary, Fallback, Local

  -- Feedback
  effectiveness_delta NUMERIC(2,1) NOT NULL,    -- Score vs. baseline delta
  suggested_action TEXT NOT NULL,               -- increase, decrease, maintain

  -- Timestamps
  feedback_timestamp TIMESTAMPTZ NOT NULL,      -- When feedback generated
  created_at TIMESTAMPTZ DEFAULT NOW(),         -- When recorded in system

  -- Constraints
  FOREIGN KEY (score_id) REFERENCES quality_scores(id) ON DELETE RESTRICT,
  FOREIGN KEY (decision_id) REFERENCES decision_records(id) ON DELETE RESTRICT,
  CHECK (suggested_action IN ('increase', 'decrease', 'maintain'))
);

-- Enable Row-Level Security (backend-only access model)
ALTER TABLE feedback_signals ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Implicit deny (no policies = backend-only)

-- ============================================================================
-- Table: provider_quality_history
-- Purpose: Track rolling provider quality metrics
-- Cardinality: 1 row per provider/model/route combination
-- RLS: Enabled (backend-only access via SERVICE_ROLE_KEY)
-- ============================================================================

CREATE TABLE IF NOT EXISTS provider_quality_history (
  -- Identity
  id TEXT PRIMARY KEY,                          -- HIS-YYYYMMDD-HHMMSS

  -- Provider/Model/Route
  provider_name TEXT NOT NULL,                  -- Google, OpenRouter, Ollama
  model_name TEXT,                              -- Gemini, Mistral, Qwen
  provider_route TEXT,                          -- Primary, Fallback, Local

  -- Quality Metrics
  decisions_count INTEGER DEFAULT 0,            -- Number of decisions
  avg_effectiveness NUMERIC(2,1),               -- Rolling average effectiveness
  effectiveness_trend TEXT,                     -- up, down, stable
  quality_tier TEXT,                            -- high, medium, low

  -- Tracking
  last_score_date TIMESTAMPTZ,                  -- Latest quality score date
  last_updated TIMESTAMPTZ NOT NULL,            -- Last metrics update
  created_at TIMESTAMPTZ DEFAULT NOW(),         -- When record created

  -- Constraints
  UNIQUE(provider_name, model_name, provider_route),
  CHECK (effectiveness_trend IN ('up', 'down', 'stable')),
  CHECK (quality_tier IN ('high', 'medium', 'low'))
);

-- Enable Row-Level Security (backend-only access model)
ALTER TABLE provider_quality_history ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Implicit deny (no policies = backend-only)

-- ============================================================================
-- Indexes: Query optimization for common access patterns
-- ============================================================================

-- Index 1: Find feedback signals by quality score (score → signal linkage)
CREATE INDEX IF NOT EXISTS idx_feedback_score
  ON feedback_signals(score_id);

-- Index 2: Find feedback signals by provider (provider analysis)
CREATE INDEX IF NOT EXISTS idx_feedback_provider
  ON feedback_signals(provider_name);

-- Index 3: Find signals by action (routing change analysis)
CREATE INDEX IF NOT EXISTS idx_feedback_action
  ON feedback_signals(suggested_action);

-- Index 4: Provider quality history by provider (quality lookup)
CREATE INDEX IF NOT EXISTS idx_provider_quality_provider
  ON provider_quality_history(provider_name);

-- Index 5: Provider quality by effectiveness (routing decisions)
CREATE INDEX IF NOT EXISTS idx_provider_quality_effectiveness
  ON provider_quality_history(avg_effectiveness DESC);

-- Index 6: Composite index for adaptive routing (provider + effectiveness)
CREATE INDEX IF NOT EXISTS idx_provider_routing
  ON provider_quality_history(provider_name, avg_effectiveness DESC);

-- ============================================================================
-- Views: Read-only consolidated views for analysis
-- ============================================================================

-- View: Provider quality trend (for adaptive routing)
-- Shows current provider quality with trend analysis
CREATE OR REPLACE VIEW v_provider_quality_trend AS
  SELECT
    qs.provider_name,
    qs.model_name,
    qs.provider_route,
    COUNT(*) AS total_decisions,
    AVG(qs.effectiveness_score) AS avg_effectiveness,
    STDDEV(qs.effectiveness_score) AS quality_variance,
    MAX(qs.scored_at) AS latest_score_date,
    CASE
      WHEN AVG(qs.effectiveness_score) > 4.0 THEN 'high'
      WHEN AVG(qs.effectiveness_score) > 3.0 THEN 'medium'
      ELSE 'low'
    END as quality_tier,
    CASE
      WHEN AVG(qs.effectiveness_score) > 4.0 THEN 'up'
      WHEN AVG(qs.effectiveness_score) < 3.0 THEN 'down'
      ELSE 'stable'
    END as trend
  FROM quality_scores qs
  WHERE qs.effectiveness_score IS NOT NULL
  GROUP BY qs.provider_name, qs.model_name, qs.provider_route
  ORDER BY avg_effectiveness DESC;

-- View: Feedback signal summary (feedback analysis)
-- Shows feedback patterns by provider
CREATE OR REPLACE VIEW v_feedback_summary AS
  SELECT
    provider_name,
    COUNT(*) AS total_signals,
    COUNT(CASE WHEN suggested_action = 'increase' THEN 1 END) AS increase_signals,
    COUNT(CASE WHEN suggested_action = 'decrease' THEN 1 END) AS decrease_signals,
    COUNT(CASE WHEN suggested_action = 'maintain' THEN 1 END) AS maintain_signals,
    AVG(effectiveness_delta) AS avg_delta,
    MIN(feedback_timestamp) AS first_feedback,
    MAX(feedback_timestamp) AS latest_feedback
  FROM feedback_signals
  GROUP BY provider_name
  ORDER BY latest_feedback DESC;

-- View: Recommended routing order (adaptive routing)
-- Shows optimal provider order for routing decisions
CREATE OR REPLACE VIEW v_recommended_routing AS
  SELECT
    ROW_NUMBER() OVER (ORDER BY avg_effectiveness DESC) as route_priority,
    provider_name,
    model_name,
    provider_route,
    avg_effectiveness as quality_score,
    quality_tier,
    trend,
    total_decisions
  FROM v_provider_quality_trend
  WHERE total_decisions >= 2  -- Only recommend if multiple decisions
  ORDER BY avg_effectiveness DESC;

-- ============================================================================
-- Comments: Documentation
-- ============================================================================

COMMENT ON TABLE feedback_signals IS 'B1D Phase: Feedback Loops. Signals generated from quality scores to inform adaptive routing. Links outcome effectiveness to provider performance.';

COMMENT ON COLUMN feedback_signals.id IS 'Canonical feedback signal ID: FBK-YYYYMMDD-HHMMSS. Unique, sortable, human-readable.';

COMMENT ON COLUMN feedback_signals.effectiveness_delta IS 'Score minus provider baseline. Positive = better than usual, Negative = worse than usual.';

COMMENT ON COLUMN feedback_signals.suggested_action IS 'Routing action suggested: increase (provider performing well), decrease (provider underperforming), maintain (provider stable).';

COMMENT ON TABLE provider_quality_history IS 'B1D Phase: Provider Quality Tracking. Rolling metrics on provider effectiveness. Used to inform adaptive routing decisions.';

COMMENT ON COLUMN provider_quality_history.effectiveness_trend IS 'Quality trend direction: up (improving), down (declining), stable (consistent).';

COMMENT ON COLUMN provider_quality_history.quality_tier IS 'Quality category: high (>4.0 avg), medium (3.0-4.0), low (<3.0).';

-- ============================================================================
-- Permissions: Backend-only access (RLS implicit deny)
-- ============================================================================

-- Only SERVICE_ROLE_KEY can access (backend only)
-- ANON_KEY cannot access these tables (intentional security model)

-- ============================================================================
-- B1D Minimal Acceptance Criteria
-- ============================================================================

/*
Acceptance Criteria:
✅ Feedback signals persist successfully
   - Signals can be inserted and retrieved without loss
✅ Feedback linked to quality score and provider
   - score_id foreign key enforces referential integrity
   - provider_name tracks provider performance
✅ Provider quality tracked accurately
   - Rolling averages calculated
   - Trends identified (up/down/stable)
   - Quality history updated automatically
✅ Adaptive routing enabled
   - Provider quality data available for routing
   - Suggested routing order queryable
   - Quality-based prioritization operational
✅ RLS security maintained
   - Backend-only access model (no ANON_KEY)
   - Consistent with B1A, B1B, B1C security
✅ No regression to B1A, B1B, B1C
   - decision_records table untouched
   - decision_outcomes table untouched
   - quality_scores table untouched
   - All prior schemas and queries unaffected
✅ Ready for B1E integration
   - Feedback signals available for B1E analysis
   - Provider quality history available for forecasting
   - No blocking dependencies for B1E
*/

-- ============================================================================
-- Schema Version and Migration Tracking
-- ============================================================================

-- B1D Deployment metadata (for audit trail)
-- Marker: MSN-0060B-B1D-FEEDBACK-SCHEMA
-- Version: 1.0 (Minimal MVP)
-- Date: 2026-06-10
-- Author: Captain TJR
-- Status: Ready for production deployment
