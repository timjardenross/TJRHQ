-- Rollback for Migration 0013: Intelligence Maturity Phase 2
-- Run this ONLY if rolling back 0013.

DROP TRIGGER IF EXISTS trg_mission_closed_at ON missions;
DROP FUNCTION IF EXISTS set_mission_closed_at();

ALTER TABLE missions
    DROP COLUMN IF EXISTS mission_type,
    DROP COLUMN IF EXISTS closed_at,
    DROP COLUMN IF EXISTS outcome_rating,
    DROP COLUMN IF EXISTS priority,
    DROP COLUMN IF EXISTS rework_of;

ALTER TABLE lessons_learned
    DROP COLUMN IF EXISTS reuse_count,
    DROP COLUMN IF EXISTS last_referenced_at;

DROP TABLE IF EXISTS captain_readiness_history;
