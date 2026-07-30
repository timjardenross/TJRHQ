-- Migration 0013: Intelligence Maturity Phase 2
-- Mission: M-20260613-INTELLIGENCE-MATURITY-PHASE2
-- Applied: manually via Supabase SQL editor or supabase CLI
-- Rollback: 0013-rollback.sql
--
-- Changes:
--   1. captain_readiness_history  — persist readiness snapshots for trend analysis
--   2. missions: closed_at, mission_type, outcome_rating, priority, rework_of
--   3. lessons_learned: reuse_count, last_referenced_at
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- 1. Captain Readiness History
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS captain_readiness_history (
    id                  UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    assessment_date     DATE        NOT NULL UNIQUE,
    readiness_score     SMALLINT    NOT NULL CHECK (readiness_score BETWEEN 0 AND 100),
    readiness_status    TEXT        NOT NULL CHECK (readiness_status IN ('Green','Amber','Red','Unknown')),
    health_score        SMALLINT,
    ops_score           SMALLINT,
    pain_score          NUMERIC(3,1),
    sleep_hours         NUMERIC(3,1),
    energy              TEXT,
    mood                TEXT,
    active_missions     SMALLINT,
    blocked_missions    SMALLINT,
    capacity_score      SMALLINT,
    contributors        JSONB,
    recommended_focus   JSONB,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE captain_readiness_history IS
    'Daily readiness snapshots for trend analysis. One row per calendar date (UNIQUE on assessment_date).';

-- Index for time-series queries
CREATE INDEX IF NOT EXISTS idx_readiness_history_date
    ON captain_readiness_history (assessment_date DESC);

-- ---------------------------------------------------------------------------
-- 2. Mission Analytics Fields
-- ---------------------------------------------------------------------------

ALTER TABLE missions
    ADD COLUMN IF NOT EXISTS mission_type    TEXT
        CHECK (mission_type IN ('capability','infrastructure','intelligence',
                                'governance','health','operations','research','other')),
    ADD COLUMN IF NOT EXISTS closed_at       TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS outcome_rating  SMALLINT
        CHECK (outcome_rating BETWEEN 1 AND 5),
    ADD COLUMN IF NOT EXISTS priority        TEXT
        CHECK (priority IN ('P0','P1','P2','P3')),
    ADD COLUMN IF NOT EXISTS rework_of       UUID REFERENCES missions(id);

COMMENT ON COLUMN missions.mission_type    IS 'Classification of mission category for analytics segmentation.';
COMMENT ON COLUMN missions.closed_at       IS 'Timestamp when mission transitioned to Closed or Archived. Auto-managed by trigger.';
COMMENT ON COLUMN missions.outcome_rating  IS '1–5 Captain rating of mission outcome quality.';
COMMENT ON COLUMN missions.priority        IS 'Mission priority (P0–P3). Synced from mission-index.txt.';
COMMENT ON COLUMN missions.rework_of       IS 'FK to original mission if this mission is a rework/retry.';

-- Auto-set closed_at when status transitions to terminal
CREATE OR REPLACE FUNCTION set_mission_closed_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status IN ('Closed', 'Archived') AND OLD.status NOT IN ('Closed', 'Archived') THEN
        NEW.closed_at = NOW();
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_mission_closed_at ON missions;
CREATE TRIGGER trg_mission_closed_at
    BEFORE UPDATE ON missions
    FOR EACH ROW EXECUTE FUNCTION set_mission_closed_at();

-- ---------------------------------------------------------------------------
-- 3. Lesson Reuse Tracking
-- ---------------------------------------------------------------------------

ALTER TABLE lessons_learned
    ADD COLUMN IF NOT EXISTS reuse_count          INTEGER     DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_referenced_at   TIMESTAMPTZ;

COMMENT ON COLUMN lessons_learned.reuse_count         IS 'Number of times this lesson has been surfaced or applied.';
COMMENT ON COLUMN lessons_learned.last_referenced_at  IS 'Timestamp of most recent reference to this lesson.';

-- ---------------------------------------------------------------------------
-- Verify
-- ---------------------------------------------------------------------------

SELECT 'captain_readiness_history' AS table_name, COUNT(*) AS rows FROM captain_readiness_history
UNION ALL
SELECT 'missions (priority col)', COUNT(*) FROM missions WHERE priority IS NOT NULL
UNION ALL
SELECT 'lessons_learned (reuse_count col)', COUNT(*) FROM lessons_learned WHERE reuse_count >= 0;
