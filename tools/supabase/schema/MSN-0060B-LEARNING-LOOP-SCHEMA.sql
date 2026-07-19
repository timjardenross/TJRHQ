-- =============================================================================
-- MSN-0060B: LEARNING LOOP SCHEMA - Phases B1A through B1F
-- =============================================================================
-- Authority: DEC-20260610-120000 (Backend-Only Access Model)
-- Authority: DEC-20260609-002 (MVLL Phase B1 Approval)
-- Status: APPROVED FOR IMPLEMENTATION
-- Date: 2026-06-10
--
-- This schema implements the Minimum Viable Learning Loop using backend-first
-- architecture with Supabase Queues and Cron for event-driven processing.
--
-- PHASE B1A: DECISION CAPTURE FOUNDATION
-- PHASE B1B: OUTCOME CAPTURE
-- PHASE B1C: QUALITY SCORING (auto)
-- PHASE B1D: MEMORY FEEDBACK (integration)
-- PHASE B1E: QUEUE & CRON (event-driven)
-- PHASE B1F: OBSERVABILITY (metrics)
-- =============================================================================

-- =============================================================================
-- PHASE B1A: DECISION CAPTURE FOUNDATION
-- =============================================================================

CREATE TABLE IF NOT EXISTS decision_records (
  id TEXT PRIMARY KEY,
  -- Canonical ID format: DEC-REC-YYYYMMDD-HHMMSS
  -- Example: DEC-REC-20260610-153045

  mission_id TEXT NOT NULL,
  -- Links to parent mission (from missions table)
  -- Allows grouping decisions by mission context

  recommendation_id TEXT NOT NULL,
  -- References original recommendation that was decided upon
  -- Allows traceability back to research that prompted decision

  recommendation_text TEXT,
  -- Copy of full recommendation text for audit trail
  -- Allows historical review even if recommendations table changes

  human_decision TEXT NOT NULL,
  -- Describes what human actually decided: "Accepted", "Rejected", "Modified to X"
  -- Classification for outcome analysis

  decision_maker VARCHAR(100),
  -- Slack user ID or system identifier ("Captain TJR", "U12345678", etc.)
  -- For decision attribution and audit

  decision_reason TEXT,
  -- Why was this decision made? What factors influenced it?
  -- For future analysis of decision quality

  decision_timestamp TIMESTAMPTZ NOT NULL,
  -- When was the decision actually made (may differ from capture time)
  -- Allows outcome timing calculation (e.g., "outcome due 7 days later")

  captured_timestamp TIMESTAMPTZ DEFAULT NOW(),
  -- When was this decision logged to database
  -- For audit trail and system performance analysis

  metadata JSONB DEFAULT NULL,
  -- Future: additional context (user sentiment, confidence, etc.)
  -- Extensible field for learning improvement

  -- RLS Policy: None (backend-only, SERVICE_ROLE_KEY)
  -- All access through Python backend via CommanderSupabaseClient
);

CREATE INDEX IF NOT EXISTS idx_decision_records_mission
  ON decision_records(mission_id);
-- Fast lookup: "What decisions were made for mission X?"

CREATE INDEX IF NOT EXISTS idx_decision_records_timestamp
  ON decision_records(decision_timestamp DESC);
-- Fast lookup: "Recent decisions" for observability queries

CREATE INDEX IF NOT EXISTS idx_decision_records_recommendation
  ON decision_records(recommendation_id);
-- Fast lookup: "What decisions referenced this recommendation?"

ALTER TABLE decision_records ENABLE ROW LEVEL SECURITY;
-- RLS enabled; no policies defined (backend-only access)
-- Implicit deny for any unauthenticated access (safe default)

-- =============================================================================
-- PHASE B1B: OUTCOME CAPTURE
-- =============================================================================

CREATE TABLE IF NOT EXISTS decision_outcomes (
  id TEXT PRIMARY KEY,
  -- Canonical ID format: OUT-YYYYMMDD-HHMMSS
  -- Example: OUT-20260617-153045 (one week after decision)

  decision_id TEXT NOT NULL REFERENCES decision_records(id) ON DELETE CASCADE,
  -- Foreign key to parent decision
  -- ON DELETE CASCADE: if decision removed, outcomes removed too

  outcome_status VARCHAR(50) NOT NULL,
  -- Status of outcome: "Pending" | "In Progress" | "Completed" | "Failed"
  -- Controls quality scoring and learning triggers

  result_summary TEXT,
  -- What actually happened? Narrative description of outcome
  -- Maximum detail for human review and audit

  effectiveness_score INTEGER DEFAULT NULL,
  -- 1-5 scale: 5=excellent, 4=good, 3=neutral, 2=poor, 1=terrible
  -- NULL = outcome not yet rated (status still Pending or In Progress)
  -- Used as input to quality_scoring.py

  lessons_learned TEXT DEFAULT NULL,
  -- What did we learn from this outcome?
  -- Free-form analysis for future learning improvement

  captured_timestamp TIMESTAMPTZ DEFAULT NOW(),
  -- When outcome was logged

  outcome_timestamp TIMESTAMPTZ DEFAULT NULL,
  -- When did outcome become known (may be in past)
  -- Allows: outcome captured later, backdated to actual discovery date

  -- PHASE B1C: QUALITY SCORING (auto-calculated)
  quality_score NUMERIC(3,2) DEFAULT NULL,
  -- 0.00-1.00 confidence score derived from effectiveness_score
  -- NULL = pending outcome status
  -- Auto-filled by quality_scoring.py
  -- Mapping:
  --   effectiveness=5 OR status=Completed+5 → quality=0.85
  --   effectiveness=4 OR status=Completed+4 → quality=0.75
  --   effectiveness=3 OR status=Completed+3 → quality=0.65
  --   effectiveness=2 OR status=Completed+2 → quality=0.40
  --   effectiveness=1 OR status=Completed+1 → quality=0.20
  --   status=Failed → quality=0.00
  --   status=Pending/InProgress → quality=0.50 (neutral, awaiting outcome)

  scoring_reason TEXT DEFAULT NULL,
  -- Why this quality score? Machine-generated explanation
  -- Example: "Completed with effectiveness=5 (excellent) → confidence=0.85"

  scored_timestamp TIMESTAMPTZ DEFAULT NULL,
  -- When was quality score calculated

  -- PHASE B1D: MEMORY FEEDBACK (integration point)
  memory_feedback_applied BOOLEAN DEFAULT FALSE,
  -- Flag: Has this outcome triggered memory confidence update?
  -- Prevents duplicate memory adjustments

  memory_adjustment NUMERIC(4,2) DEFAULT NULL,
  -- What confidence adjustment was applied? (+0.15, -0.15, 0.00, etc.)
  -- NULL = feedback not yet applied

  feedback_timestamp TIMESTAMPTZ DEFAULT NULL,
  -- When was memory feedback applied

  -- PHASE B1E: QUEUE & CRON INTEGRATION
  queued_for_followup BOOLEAN DEFAULT FALSE,
  -- Flag: Is this outcome enqueued for cron follow-up?
  -- Cron job processes pending outcomes daily

  followup_scheduled_for TIMESTAMPTZ DEFAULT NULL,
  -- When should this outcome be checked again?
  -- Default: NOW() + 7 days (configurable)

  metadata JSONB DEFAULT NULL,
  -- Future: additional outcome context

  -- RLS Policy: None (backend-only, SERVICE_ROLE_KEY)
);

CREATE INDEX IF NOT EXISTS idx_outcomes_decision
  ON decision_outcomes(decision_id);
-- Fast lookup: "What outcomes for this decision?"

CREATE INDEX IF NOT EXISTS idx_outcomes_status
  ON decision_outcomes(outcome_status);
-- Fast lookup: "What outcomes are pending?" (for cron jobs)

CREATE INDEX IF NOT EXISTS idx_outcomes_quality
  ON decision_outcomes(quality_score DESC);
-- Fast lookup: "What are highest-quality outcomes?" (for learning analysis)

CREATE INDEX IF NOT EXISTS idx_outcomes_timestamp
  ON decision_outcomes(outcome_timestamp DESC);
-- Fast lookup: "Recent outcomes" for observability

CREATE INDEX IF NOT EXISTS idx_outcomes_followup
  ON decision_outcomes(followup_scheduled_for)
  WHERE outcome_status IN ('Pending', 'In Progress');
-- Fast lookup: "What needs cron follow-up today?" (for daily job)

ALTER TABLE decision_outcomes ENABLE ROW LEVEL SECURITY;

-- =============================================================================
-- PHASE B1E: QUEUE SUPPORT TABLES
-- =============================================================================

CREATE TABLE IF NOT EXISTS decision_followup_queue (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  -- Unique queue item ID

  decision_id TEXT NOT NULL REFERENCES decision_records(id) ON DELETE CASCADE,
  -- Which decision needs follow-up?

  check_at TIMESTAMPTZ NOT NULL,
  -- When should this be checked? (e.g., 7 days after decision)

  reminder_level VARCHAR(20),
  -- "reminder_week1" | "reminder_week2" | "escalation" (extensible)

  status VARCHAR(20) DEFAULT 'enqueued',
  -- "enqueued" | "processing" | "completed" | "failed"

  processed_at TIMESTAMPTZ DEFAULT NULL,
  -- When was this item processed?

  error_message TEXT DEFAULT NULL,
  -- If status=failed, why?

  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_followup_queue_check_at
  ON decision_followup_queue(check_at)
  WHERE status = 'enqueued';
-- Fast lookup: "What queue items are due now?" (for cron job)

CREATE INDEX IF NOT EXISTS idx_followup_queue_decision
  ON decision_followup_queue(decision_id);

ALTER TABLE decision_followup_queue ENABLE ROW LEVEL SECURITY;

-- =============================================================================
-- PHASE B1F: OBSERVABILITY SUPPORT
-- =============================================================================

-- Note: Learning loop metrics are aggregated views, not base tables
-- Metrics are added to existing daily_health_snapshots table via Python

-- Example view for observability queries:
CREATE OR REPLACE VIEW learning_loop_daily_metrics AS
SELECT
  CURRENT_DATE as metric_date,
  COUNT(DISTINCT dr.id) as total_decisions,
  COUNT(DISTINCT CASE WHEN do.outcome_status = 'Pending' THEN dr.id END) as pending_outcomes,
  COUNT(DISTINCT CASE WHEN do.outcome_status = 'In Progress' THEN dr.id END) as in_progress_outcomes,
  COUNT(DISTINCT CASE WHEN do.outcome_status = 'Completed' THEN dr.id END) as completed_outcomes,
  COUNT(DISTINCT CASE WHEN do.outcome_status = 'Failed' THEN dr.id END) as failed_outcomes,
  ROUND(AVG(CASE WHEN do.quality_score IS NOT NULL THEN do.quality_score END)::numeric, 2) as avg_quality_score,
  COUNT(DISTINCT CASE WHEN do.memory_feedback_applied = TRUE THEN dr.id END) as learning_adjustments_applied,
  COUNT(DISTINCT CASE WHEN dfq.status = 'enqueued' THEN dfq.id END) as pending_queue_items
FROM decision_records dr
LEFT JOIN decision_outcomes do ON dr.id = do.decision_id
LEFT JOIN decision_followup_queue dfq ON dr.id = dfq.decision_id
WHERE dr.captured_timestamp >= CURRENT_DATE
GROUP BY CURRENT_DATE;

-- =============================================================================
-- CRON SUPPORT FUNCTIONS
-- =============================================================================
-- These functions are called by Supabase Cron jobs (Phase B1E)

CREATE OR REPLACE FUNCTION process_pending_decisions()
RETURNS TABLE (
  pending_count INTEGER,
  pending_ids TEXT[]
) AS $$
DECLARE
  v_pending_ids TEXT[];
BEGIN
  -- Find all decisions awaiting outcome
  SELECT ARRAY_AGG(dr.id)
  INTO v_pending_ids
  FROM decision_records dr
  LEFT JOIN decision_outcomes do ON dr.id = do.decision_id
  WHERE do.id IS NULL
    OR do.outcome_status IN ('Pending', 'In Progress')
  LIMIT 100;  -- Reasonable batch size for cron

  RETURN QUERY
  SELECT
    COALESCE(ARRAY_LENGTH(v_pending_ids, 1), 0)::INTEGER,
    v_pending_ids;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION check_followup_queue_items()
RETURNS TABLE (
  items_processed INTEGER,
  items_failed INTEGER
) AS $$
DECLARE
  v_items_processed INTEGER := 0;
  v_items_failed INTEGER := 0;
BEGIN
  -- Mark items for processing if check_at <= NOW()
  UPDATE decision_followup_queue
  SET status = 'processing'
  WHERE status = 'enqueued'
    AND check_at <= NOW()
  RETURNING id INTO v_items_processed;

  -- In production, each "processing" item would trigger actual reminder
  -- For MVP, just mark as completed
  UPDATE decision_followup_queue
  SET status = 'completed'
  WHERE status = 'processing'
    AND processed_at IS NULL
  RETURNING id INTO v_items_processed;

  RETURN QUERY
  SELECT v_items_processed::INTEGER, v_items_failed::INTEGER;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- CRON JOB DEFINITIONS
-- =============================================================================
-- Execute these after schema is created to enable daily processing

-- Job 1: Daily check for pending outcomes
-- Schedule: 00:00 UTC daily
-- SELECT cron.schedule(
--   'decision-followup-check',
--   '0 0 * * *',
--   'SELECT process_pending_decisions();'
-- );

-- Job 2: Daily queue item processing
-- Schedule: 01:00 UTC daily (one hour after first job)
-- SELECT cron.schedule(
--   'decision-queue-processor',
--   '0 1 * * *',
--   'SELECT check_followup_queue_items();'
-- );

-- =============================================================================
-- RLS POLICY DEFINITION
-- =============================================================================
-- RLS is enabled on all learning loop tables with implicit deny.
-- Backend-only access via SERVICE_ROLE_KEY (CommanderSupabaseClient).
-- No policies needed until proven frontend use case requires them.
-- See: docs/SUPABASE_ACCESS_MODEL.md (Section 9: Approved Exception Process)

-- =============================================================================
-- VERIFICATION QUERIES
-- =============================================================================
-- Use these to verify schema was created correctly:

-- Check table existence:
-- SELECT table_name FROM information_schema.tables
-- WHERE table_schema = 'public'
-- AND table_name LIKE 'decision_%';

-- Check indexes:
-- SELECT indexname FROM pg_indexes
-- WHERE tablename LIKE 'decision_%' OR tablename = 'decision_followup_queue';

-- Check RLS status:
-- SELECT tablename, rowsecurity FROM pg_tables
-- WHERE tablename LIKE 'decision_%';
-- Expected output: t (TRUE) for all learning loop tables

-- =============================================================================
-- END SCHEMA
-- =============================================================================
-- Status: READY FOR IMPLEMENTATION
-- Authority: DEC-20260610-120000 (Backend-Only Access Model)
-- Date: 2026-06-10
-- Next Step: Execute schema in Supabase, then implement learning_loop_service.py
