-- ============================================================
-- Migration 0029 — Notebook Traceability Fields (EXEC-010C WP2)
-- Adds execution audit trail to intelligence_notes:
--   routed_entity_type  — WP1 route type (MISSION, IMPROVEMENT, etc.)
--   routed_at           — when the artefact was created
--   routed_by           — who/what triggered execution (captain, system, etc.)
-- Additive + idempotent.
-- ============================================================

ALTER TABLE intelligence_notes
  ADD COLUMN IF NOT EXISTS routed_entity_type  text,
  ADD COLUMN IF NOT EXISTS routed_at           timestamptz,
  ADD COLUMN IF NOT EXISTS routed_by           text;

COMMENT ON COLUMN intelligence_notes.routed_entity_type IS
  'WP1 route type executed: MISSION, BUILD_REQUEST, STRATEGIC_INITIATIVE, IMPROVEMENT, KNOWLEDGE_ARTICLE, RESEARCH_REQUEST, COMMUNICATION_OPPORTUNITY';
COMMENT ON COLUMN intelligence_notes.routed_at IS
  'Timestamp when the artefact was created by the Route Execution Engine (WP1).';
COMMENT ON COLUMN intelligence_notes.routed_by IS
  'Identity that triggered route execution — captain, system, or operator.';
