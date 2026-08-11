-- ============================================================
-- Migration 0091 — Intelligence Workbench Phase B Schema
-- Adds source governance filtering and health synthesis support
-- for the Intelligence Workbench (Operational + Health modes)
-- ============================================================

-- ─── 1. Add source_governed to core_events for Phase A filtering ──────────────
-- Denormalize intelligence_source_registry.terms_reviewed for efficient filtering
-- in Intelligence Workbench queries (operational signals only from reviewed sources).

ALTER TABLE core_events
  ADD COLUMN IF NOT EXISTS source_governed boolean DEFAULT false;

COMMENT ON COLUMN core_events.source_governed IS
  'Phase B Intelligence Workbench: source governance gate. '
  'Denormalized from intelligence_source_registry.terms_reviewed for efficient filtering. '
  'Only events from sources with terms_reviewed=true are shown in operational signals mode.';

CREATE INDEX IF NOT EXISTS idx_core_events_source_governed
  ON core_events(source_governed)
  WHERE source_governed = true;

-- ─── 2. Ensure health_insights has all required columns for workbench ─────────
-- Phase B Health Intelligence mode requires source articles and commitment tracking
ALTER TABLE health_insights
  ADD COLUMN IF NOT EXISTS source_articles jsonb DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS committed_to_memory boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS committed_at timestamptz,
  ADD COLUMN IF NOT EXISTS reviewed_at timestamptz,
  ADD COLUMN IF NOT EXISTS overall_status text DEFAULT 'OK'
    CHECK (overall_status IN ('OK', 'CAUTION', 'ALERT'));

COMMENT ON COLUMN health_insights.source_articles IS
  'Phase B: array of {title, url, summary, published_date, source_type} objects '
  'extracted from health_source_articles for workbench rendering.';
COMMENT ON COLUMN health_insights.committed_to_memory IS
  'Phase B: user committed this insight to their memory/knowledge base via workbench.';
COMMENT ON COLUMN health_insights.committed_at IS
  'Phase B: timestamp when insight was committed to memory.';
COMMENT ON COLUMN health_insights.reviewed_at IS
  'Phase B: timestamp when user reviewed (committed or discarded) this insight.';

-- ─── 3. Ensure intelligence_events has confidence_level for filtering ──────────
-- Map confidence (0–100) to categorical confidence_level if not already present
ALTER TABLE intelligence_events
  ADD COLUMN IF NOT EXISTS confidence_level text DEFAULT 'Emerging'
    CHECK (confidence_level IN ('Confirmed', 'Probable', 'Emerging', 'Unverified'));

-- ─── 4. Create health_source_articles junction table if not exists ───────────
-- Used to populate source_articles array on health_insights
CREATE TABLE IF NOT EXISTS health_source_articles (
  article_id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  insight_id         uuid        NOT NULL REFERENCES health_insights(id) ON DELETE CASCADE,
  title              text        NOT NULL,
  url                text        NOT NULL,
  summary            text,
  published_date     timestamptz,
  source_type        text,  -- 'news', 'journal', 'self-report', etc.
  created_at         timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE health_source_articles IS
  'Phase B Health Intelligence: source articles linked to health insights. '
  'Used to populate health_insights.source_articles array for workbench rendering.';

CREATE INDEX IF NOT EXISTS idx_health_source_articles_insight
  ON health_source_articles(insight_id);
CREATE INDEX IF NOT EXISTS idx_health_source_articles_url
  ON health_source_articles(url);

-- ─── 5. Enable RLS on new tables ────────────────────────────────────────────
ALTER TABLE health_source_articles ENABLE ROW LEVEL SECURITY;

-- ─── 6. Create or update analytics_health_daily view ────────────────────────
-- NEVER APPLIED — DO NOT REPLAY. Left in place as historical record only.
--
-- This step was skipped on the original apply (confirmed via list_migrations:
-- the migration that actually ran live is recorded as
-- "0091_intelligence_workbench_phase_b_steps_1_5" — steps 1-5 only). Reason:
-- this CREATE OR REPLACE VIEW redefines analytics_health_daily with only 5
-- columns (log_date, physical_capacity, sleep_hours, pain_score,
-- overall_note), which is far narrower than the 34-column view actually live
-- today (defined by 0082_recovery_pulses_daily_view.sql). The Human Systems
-- Workbench's GET /api/human-systems route selects columns from this view —
-- sleep_quality, cpap_status, nervous_system_state, energy, movement_notes,
-- pleasure_creativity_marker, what_happened, sitting_tolerance_minutes,
-- workload_constraint, captain_capacity_rating — that only exist in the
-- 0082 definition. If this step were ever replayed (a future `supabase db
-- push`, a migration-history replay, or a well-meaning "let's re-run 0091
-- fully" cleanup), it would silently drop the view back to 5 columns: no
-- error, just every Recovery/Medical tab field this route reads for those
-- missing columns going to NULL / "Not recorded", including the whole Life
-- Participation score.
--
-- Found and flagged during the 2026-08-09 Human Systems Workbench Chief
-- Engineer review (workbench-reviews/human-systems/chief-engineer-review.md,
-- "Real gap: a stale migration file that, if replayed, would silently break
-- the Medical tab"). Commented out rather than deleted, per that review's own
-- recommendation — this is a historical record of what Phase B originally
-- intended and later corrected, not a live bug (confirmed live: 0082's
-- 34-column definition is what's actually running).
--
-- CREATE OR REPLACE VIEW analytics_health_daily AS
-- SELECT
--   log_date::date as log_date,
--   COALESCE((SELECT AVG((physical_capacity)::numeric)
--     FROM captain_readiness_history
--     WHERE assessment_date = log_date), 0) as physical_capacity,
--   COALESCE((SELECT AVG((sleep_hours)::numeric)
--     FROM health_daily_logs
--     WHERE log_date = analytics_health_daily.log_date), 0) as sleep_hours,
--   COALESCE((SELECT AVG((pain_score)::numeric)
--     FROM health_daily_logs
--     WHERE log_date = analytics_health_daily.log_date), 0) as pain_score,
--   (SELECT overall_note FROM captain_readiness_history
--    WHERE assessment_date = log_date LIMIT 1) as overall_note
-- FROM (
--   SELECT DISTINCT log_date FROM health_daily_logs
--   UNION
--   SELECT DISTINCT assessment_date as log_date FROM captain_readiness_history
-- ) t;
