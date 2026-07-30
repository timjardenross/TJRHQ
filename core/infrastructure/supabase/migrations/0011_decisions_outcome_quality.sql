-- Migration 0011: outcome_quality on decisions table
-- Sprint D — Learning Loop
-- Adds retrospective quality rating to automated decisions.
-- G-008 activation threshold: 10+ decisions rated.
-- Rating scale: 1 (poor) to 5 (excellent).

ALTER TABLE decisions
    ADD COLUMN IF NOT EXISTS outcome_quality    INTEGER
        CHECK (outcome_quality BETWEEN 1 AND 5),
    ADD COLUMN IF NOT EXISTS quality_notes      TEXT,
    ADD COLUMN IF NOT EXISTS quality_rated_at   TIMESTAMPTZ;
