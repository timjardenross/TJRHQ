-- ============================================================
-- Migration 0021 — Human Systems feedback category (Pilot)
-- HSF-001 — supports the Validation Pilot feedback taxonomy:
--   Helpful | Neutral | Not Helpful
--
-- Adds a `category` column and relaxes `useful` to nullable so that a Neutral
-- response is a distinct, first-class signal (not conflated with Not Helpful).
-- Additive + idempotent.
-- ============================================================

ALTER TABLE human_systems_feedback
  ADD COLUMN IF NOT EXISTS category text
    CHECK (category IN ('helpful','neutral','not_helpful'));

-- Neutral feedback has no boolean usefulness — allow NULL.
ALTER TABLE human_systems_feedback
  ALTER COLUMN useful DROP NOT NULL;

COMMENT ON COLUMN human_systems_feedback.category IS
  'HSF-001 Pilot feedback taxonomy: helpful | neutral | not_helpful. '
  'helpful → useful=true, not_helpful → useful=false, neutral → useful=null. '
  'Primary measure for "does this increase Captain capacity, not just activity".';
