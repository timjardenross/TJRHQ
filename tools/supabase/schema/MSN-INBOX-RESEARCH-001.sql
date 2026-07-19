-- =============================================================================
-- MSN-INBOX-RESEARCH-001: Research Stage Columns for captured_items
-- Adds Mistral research pipeline output columns.
-- Applied: 2026-06-21
-- =============================================================================

ALTER TABLE captured_items
  ADD COLUMN IF NOT EXISTS research_status text
    CHECK (research_status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
  ADD COLUMN IF NOT EXISTS research_findings text,
  ADD COLUMN IF NOT EXISTS research_brief text,
  ADD COLUMN IF NOT EXISTS research_mission_id text,
  ADD COLUMN IF NOT EXISTS research_confidence float DEFAULT 0.0;

-- Index: research queue (items awaiting or running research)
CREATE INDEX IF NOT EXISTS idx_captured_items_research_status
  ON captured_items(research_status)
  WHERE research_status IN ('pending', 'running');
