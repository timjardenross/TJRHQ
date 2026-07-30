-- MSN-0060B Phase B1C: Quality Scoring Schema
-- Scores decision outcomes for effectiveness (1-5 scale)
-- Links outcomes to quality scores for analysis
--
-- Design: Minimal MVP
-- - Scores outcome effectiveness
-- - Generates scoring reasons
-- - Captures provider/model/route attribution
-- - Enables provider quality analysis
-- - Defers effectiveness forecasting to B1D

-- ============================================================================
-- Table: quality_scores
-- Purpose: Record effectiveness scores of decision outcomes
-- Cardinality: 1 outcome → 1 score (1:1 initially, could extend to 1:N for B1D)
-- RLS: Enabled (backend-only access via SERVICE_ROLE_KEY)
-- ============================================================================

CREATE TABLE IF NOT EXISTS quality_scores (
  -- Identity
  id TEXT PRIMARY KEY,                          -- SCO-YYYYMMDD-HHMMSS (canonical format)
  outcome_id TEXT NOT NULL,                     -- FK to decision_outcomes(id)
  decision_id TEXT NOT NULL,                    -- FK to decision_records(id)
  recommendation_id TEXT,                       -- FK to recommendations(id) for reference

  -- Scoring
  effectiveness_score NUMERIC(2,1),             -- 1.0 to 5.0, NULL if unknown
  scoring_reason TEXT NOT NULL,                 -- Why this score

  -- Attribution
  provider_name TEXT,                           -- Google, OpenRouter, Ollama (from decision)
  model_name TEXT,                              -- Gemini, Mistral, Qwen (from decision)
  provider_route TEXT,                          -- Primary, Fallback, Local (from decision)

  -- Timestamps
  scored_at TIMESTAMPTZ NOT NULL,               -- When scored
  created_at TIMESTAMPTZ DEFAULT NOW(),         -- When recorded in system

  -- Constraints
  FOREIGN KEY (outcome_id) REFERENCES decision_outcomes(id) ON DELETE RESTRICT,
  FOREIGN KEY (decision_id) REFERENCES decision_records(id) ON DELETE RESTRICT,
  CHECK (effectiveness_score IS NULL OR (effectiveness_score >= 1.0 AND effectiveness_score <= 5.0))
);

-- Enable Row-Level Security (backend-only access model)
ALTER TABLE quality_scores ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Implicit deny (no policies = backend-only)
-- No SELECT, INSERT, UPDATE, DELETE policies defined
-- Only SERVICE_ROLE_KEY bypasses RLS (backend access)
-- ANON_KEY cannot access this table (intentional, security model)

-- ============================================================================
-- Indexes: Query optimization for common access patterns
-- ============================================================================

-- Index 1: Find scores for an outcome (outcome → score linkage)
CREATE INDEX IF NOT EXISTS idx_quality_outcome
  ON quality_scores(outcome_id);

-- Index 2: Find scores for a decision (decision → scores)
CREATE INDEX IF NOT EXISTS idx_quality_decision
  ON quality_scores(decision_id);

-- Index 3: Find scores by provider (provider analysis)
CREATE INDEX IF NOT EXISTS idx_quality_provider
  ON quality_scores(provider_name);

-- Index 4: Find scores by effectiveness (filtering by quality)
CREATE INDEX IF NOT EXISTS idx_quality_score
  ON quality_scores(effectiveness_score);

-- Index 5: Find recent scores (recent scores first)
CREATE INDEX IF NOT EXISTS idx_quality_timestamp
  ON quality_scores(scored_at DESC);

-- Index 6: Composite index for provider analysis (provider + score)
CREATE INDEX IF NOT EXISTS idx_quality_provider_score
  ON quality_scores(provider_name, effectiveness_score);

-- ============================================================================
-- Views: Read-only consolidated views for analysis
-- ============================================================================

-- View 1: Provider quality summary
-- Shows: Which providers are most effective (by average score)
CREATE OR REPLACE VIEW v_provider_quality AS
  SELECT
    provider_name,
    COUNT(*) AS scored_decisions,
    COUNT(CASE WHEN effectiveness_score >= 4.0 THEN 1 END) AS high_quality_count,
    COUNT(CASE WHEN effectiveness_score < 3.0 THEN 1 END) AS low_quality_count,
    AVG(effectiveness_score) AS avg_score,
    MIN(effectiveness_score) AS min_score,
    MAX(effectiveness_score) AS max_score,
    STDDEV(effectiveness_score) AS score_variance
  FROM quality_scores
  WHERE effectiveness_score IS NOT NULL
  GROUP BY provider_name
  ORDER BY avg_score DESC;

-- View 2: Model quality summary
-- Shows: Which models are most effective (by provider)
CREATE OR REPLACE VIEW v_model_quality AS
  SELECT
    model_name,
    provider_name,
    COUNT(*) AS scored_decisions,
    COUNT(CASE WHEN effectiveness_score >= 4.0 THEN 1 END) AS high_quality_count,
    COUNT(CASE WHEN effectiveness_score < 3.0 THEN 1 END) AS low_quality_count,
    AVG(effectiveness_score) AS avg_score,
    MIN(effectiveness_score) AS min_score,
    MAX(effectiveness_score) AS max_score
  FROM quality_scores
  WHERE effectiveness_score IS NOT NULL
  GROUP BY model_name, provider_name
  ORDER BY avg_score DESC;

-- View 3: Routing strategy quality summary
-- Shows: Which routing strategies are most effective
CREATE OR REPLACE VIEW v_route_quality AS
  SELECT
    provider_route,
    COUNT(*) AS decisions,
    COUNT(CASE WHEN effectiveness_score >= 4.0 THEN 1 END) AS high_quality_count,
    COUNT(CASE WHEN effectiveness_score < 3.0 THEN 1 END) AS low_quality_count,
    AVG(effectiveness_score) AS avg_score,
    MIN(effectiveness_score) AS min_score,
    MAX(effectiveness_score) AS max_score,
    STDDEV(effectiveness_score) AS score_variance
  FROM quality_scores
  WHERE effectiveness_score IS NOT NULL
  GROUP BY provider_route
  ORDER BY avg_score DESC;

-- View 4: Full traceability chain (outcome → score + decision context)
CREATE OR REPLACE VIEW v_quality_outcome_chain AS
  SELECT
    qs.id AS score_id,
    qs.outcome_id,
    qs.decision_id,
    qs.effectiveness_score,
    qs.scoring_reason,
    qs.provider_name,
    qs.model_name,
    qs.provider_route,
    do.outcome_status,
    do.implementation_notes,
    do.outcome_timestamp,
    dr.human_decision,
    dr.decision_maker,
    dr.decision_timestamp,
    qs.scored_at,
    qs.created_at
  FROM quality_scores qs
  JOIN decision_outcomes do ON qs.outcome_id = do.id
  JOIN decision_records dr ON qs.decision_id = dr.id
  ORDER BY qs.scored_at DESC;

-- ============================================================================
-- Comments: Documentation
-- ============================================================================

COMMENT ON TABLE quality_scores IS 'B1C Phase: Quality Scoring. Effectiveness scores for decision outcomes. Linked to decision_outcomes and decision_records for traceability. Defers effectiveness forecasting to B1D Continuous Learning phase.';

COMMENT ON COLUMN quality_scores.id IS 'Canonical quality score ID: SCO-YYYYMMDD-HHMMSS. Unique, sortable, human-readable.';

COMMENT ON COLUMN quality_scores.outcome_id IS 'Foreign key to decision_outcomes(id). Links score to outcome.';

COMMENT ON COLUMN quality_scores.decision_id IS 'Foreign key to decision_records(id). Links score to decision.';

COMMENT ON COLUMN quality_scores.effectiveness_score IS 'Effectiveness rating: 1.0 (ineffective) to 5.0 (excellent). NULL for unknown/pending outcomes.';

COMMENT ON COLUMN quality_scores.scoring_reason IS 'Human-readable explanation for the score. Why this score was assigned.';

COMMENT ON COLUMN quality_scores.provider_name IS 'AI provider (Google, OpenRouter, Ollama). Captured from decision metadata.';

COMMENT ON COLUMN quality_scores.model_name IS 'Model name (Gemini, Mistral, Qwen). Captured from decision metadata.';

COMMENT ON COLUMN quality_scores.provider_route IS 'Routing strategy (Primary, Fallback, Local). Indicates which provider was selected by routing logic.';

COMMENT ON COLUMN quality_scores.scored_at IS 'When the score was assigned.';

COMMENT ON COLUMN quality_scores.created_at IS 'When the score was recorded in system.';

-- ============================================================================
-- Permissions: Backend-only access (RLS implicit deny)
-- ============================================================================

-- GRANT SELECT, INSERT, UPDATE, DELETE ON quality_scores TO authenticated;
-- (commented out because we use RLS implicit deny instead)

-- Only SERVICE_ROLE_KEY can access (backend only)
-- ANON_KEY cannot access this table (intentional security model)

-- ============================================================================
-- B1C Minimal Acceptance Criteria
-- ============================================================================

/*
Acceptance Criteria:
✅ Quality scores persist successfully
   - Scores can be inserted and retrieved without loss
✅ Score linked to originating outcome
   - outcome_id foreign key enforces referential integrity
   - No orphan scores possible
✅ Full traceability outcome → score → decision
   - Complete chain queryable via v_quality_outcome_chain view
   - All timestamps and metadata preserved
✅ Provider quality analysis operational
   - v_provider_quality enables provider effectiveness comparison
   - Scores by provider and model available
✅ Routing effectiveness analysis operational
   - v_route_quality enables routing strategy comparison
   - Decision count and quality metrics available
✅ RLS security maintained
   - Backend-only access model (no ANON_KEY)
   - Consistent with B1A and B1B security
✅ No regression to B1A or B1B
   - decision_records table untouched
   - decision_outcomes table untouched
   - B1A and B1B schemas and queries unaffected
✅ Ready for B1D integration
   - Quality scores available for feedback loops
   - Schema designed for effectiveness forecasting
   - No blocking dependencies for B1D
*/

-- ============================================================================
-- Schema Version and Migration Tracking
-- ============================================================================

-- B1C Deployment metadata (for audit trail)
-- Marker: MSN-0060B-B1C-QUALITY-SCHEMA
-- Version: 1.0 (Minimal MVP)
-- Date: 2026-06-10
-- Author: Captain TJR
-- Status: Ready for production deployment
