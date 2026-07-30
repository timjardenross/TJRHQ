-- ============================================================
-- Migration 0059 — core_events.time_sensitivity (MSN-0308, Workstream 4)
-- Additive, nullable column, same shape as importance/confidence/relevance.
-- Resolves the schema gap MSN-0306/MSN-0307 both found: the Priority
-- Engine's time_sensitivity dimension had no real column to read from.
-- No domain populates it yet -- this is schema readiness, not new data.
-- ============================================================

ALTER TABLE core_events ADD COLUMN IF NOT EXISTS time_sensitivity smallint
  CHECK (time_sensitivity BETWEEN 0 AND 100);

COMMENT ON COLUMN core_events.time_sensitivity IS
  'MSN-0308: how time-critical this event is (0-100), independent of importance. '
  'Nullable -- absent means "no time-sensitivity signal from this domain," not zero.';
