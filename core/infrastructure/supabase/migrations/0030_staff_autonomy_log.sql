-- ============================================================
-- Migration 0030 — Staff Autonomy Log
-- Tracks self-directed actions taken by exec staff within
-- their granted authority bounds (not at Captain's direct instruction).
-- Pairs with the [SD] git commit convention (see CLAUDE.md).
-- ============================================================

CREATE TABLE IF NOT EXISTS staff_autonomy_log (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    actor        text        NOT NULL,           -- 'EDO', 'CE', 'XO', 'COMMS', 'HSF', etc.
    action       text        NOT NULL,           -- short description of what was done
    rationale    text,                           -- why this was self-directed
    commit_sha   text,                           -- git SHA (first 12 chars is fine)
    branch       text,                           -- branch the action was taken on
    mission_ref  text,                           -- mission that granted the standing authority
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- RLS: service_role bypasses; no public read/write
ALTER TABLE staff_autonomy_log ENABLE ROW LEVEL SECURITY;

-- Index for dashboard queries (chronological feed)
CREATE INDEX IF NOT EXISTS staff_autonomy_log_created_at_idx
    ON staff_autonomy_log (created_at DESC);

-- Index for filtering by actor
CREATE INDEX IF NOT EXISTS staff_autonomy_log_actor_idx
    ON staff_autonomy_log (actor);
