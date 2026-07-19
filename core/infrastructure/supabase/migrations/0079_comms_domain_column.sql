-- ============================================================
-- Migration 0079 — Comms domain column (Phase 1C Communications)
-- Adds a domain classifier to content_signals so health-sourced
-- and operational (ORI-sourced) signals can be filtered separately
-- in the Communications Workbench UI. Additive only.
-- ============================================================

ALTER TABLE content_signals
  ADD COLUMN IF NOT EXISTS domain text NOT NULL DEFAULT 'operational'
    CHECK (domain IN ('health', 'operational'));

-- Existing rows are all ORI-sourced (health scoring did not exist before this
-- migration), so the default backfills them correctly.
UPDATE content_signals SET domain = 'operational' WHERE domain IS NULL;

CREATE INDEX IF NOT EXISTS idx_content_signals_domain
  ON content_signals (domain, rank_score DESC);

COMMENT ON COLUMN content_signals.domain IS
  'Phase 1C: signal origin — health (from health_insights) or operational (from ORI '
  'intelligence_events). Drives the domain toggle in the Communications Workbench.';
