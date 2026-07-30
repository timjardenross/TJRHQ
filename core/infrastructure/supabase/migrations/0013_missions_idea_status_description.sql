-- ============================================================================
-- Migration 0013 — missions: add 'Idea' status + description column
-- ============================================================================
-- Purpose:
--   /mission-capture now assigns status='Idea' (dormant, pre-triage capture)
--   instead of 'Designed' (active work state). Ideas are excluded from the
--   Number One work queue until promoted by the Captain.
--
--   Adds a description TEXT column to persist the LLM-generated capture body.
--
-- Apply via Supabase SQL Editor or psql.
-- ============================================================================

-- 1. Extend the status CHECK constraint to include 'Idea'.
--    Drop the existing constraint by name, re-add with the expanded set.
ALTER TABLE missions DROP CONSTRAINT IF EXISTS missions_status_check;

ALTER TABLE missions
  ADD CONSTRAINT missions_status_check
  CHECK (status IN (
    'Idea',
    'Designed',
    'Implemented',
    'Tested',
    'Awaiting Number One Review',
    'Validated',
    'Awaiting XO Approval',
    'Closed',
    'Blocked',
    'Archived'
  ));

-- 2. Add description column for LLM-generated capture body.
ALTER TABLE missions ADD COLUMN IF NOT EXISTS description TEXT;
