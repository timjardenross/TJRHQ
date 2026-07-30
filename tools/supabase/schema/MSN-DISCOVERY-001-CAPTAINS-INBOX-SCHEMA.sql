-- =============================================================================
-- MSN-DISCOVERY-001: Captain's Inbox & Governance Context Service
-- WP1: Capture Registry Schema
-- Applied: 2026-06-12
-- =============================================================================

-- -----------------------------------------------------------------------------
-- TABLE: captured_items (Core Record)
-- Primary intelligence capture record. Written synchronously on intake.
-- Governance cache columns are non-authoritative and expire after 24h.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS captured_items (
  -- Identity
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  captured_by text,

  -- Capture Event (stored immediately on intake)
  captured_at timestamp NOT NULL DEFAULT now(),
  source_type text NOT NULL CHECK (source_type IN ('channel_message', 'channel_file')),
  source_channel_id text NOT NULL,
  source_message_id text NOT NULL,
  source_message_ts text NOT NULL,
  source_message_permalink text,
  source_user_id text,

  -- Item Content (stored immediately on intake)
  item_type text NOT NULL CHECK (item_type IN ('url', 'text_note', 'file', 'image', 'screenshot')),
  source_url text,
  title text NOT NULL,
  raw_text text CHECK (length(raw_text) <= 10240),  -- 10KB cap

  -- Processing Status
  processing_status text DEFAULT 'pending' CHECK (processing_status IN ('pending', 'in_progress', 'completed', 'failed')),
  last_processed_at timestamp,
  processing_errors text[],
  processing_confidence float DEFAULT 0.0,

  -- Classification Results (populated async)
  classification text CHECK (classification IN ('research', 'decision', 'mission', 'reference', 'personal', 'unclassified')),
  importance text CHECK (importance IN ('low', 'medium', 'high', 'critical', 'unrated')),
  summary text,
  summary_source text CHECK (summary_source IN ('claude_generated', 'auto_truncated', 'fallback')),

  -- Quality Control
  requires_review boolean DEFAULT false,
  duplicate_detected boolean DEFAULT false,
  duplicate_of uuid REFERENCES captured_items(id),

  -- Review Lifecycle
  review_status text DEFAULT 'unreviewed' CHECK (review_status IN ('unreviewed', 'reviewed', 'archived')),
  last_reviewed_at timestamp,
  reviewed_by text,

  -- Governance Context Cache (non-authoritative, expires 24h)
  governance_assessment_json jsonb,
  governance_assessment_at timestamp,
  governance_cache_expires_at timestamp,
  governance_status text CHECK (governance_status IN ('aligned', 'conflicts', 'neutral', 'unknown', 'failed')),
  governance_conflict_count integer DEFAULT 0,
  governance_max_severity text CHECK (governance_max_severity IN ('low', 'medium', 'high')),
  requires_governance_review boolean DEFAULT false,

  -- Metadata
  created_at timestamp NOT NULL DEFAULT now(),
  updated_at timestamp NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- TABLE: captured_item_links (Relationships to governance artefacts)
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS captured_item_links (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  captured_item_id uuid NOT NULL REFERENCES captured_items(id) ON DELETE CASCADE,

  link_type text NOT NULL CHECK (link_type IN ('related_mission', 'related_decision', 'evidence_for')),
  mission_id text,
  decision_id text,
  link_confidence float DEFAULT 0.5,
  created_by text,
  is_automatic boolean DEFAULT false,

  created_at timestamp NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- TABLE: captured_item_text (Full-text search index)
-- Separate table to keep captured_items lean and allow independent GIN index.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS captured_item_text (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  captured_item_id uuid NOT NULL REFERENCES captured_items(id) ON DELETE CASCADE,
  indexed_text tsvector,

  created_at timestamp NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- INDEXES
-- -----------------------------------------------------------------------------

-- Deduplication: same source_message_id = same capture (idempotent intake)
CREATE UNIQUE INDEX IF NOT EXISTS idx_captured_items_source_message_unique
  ON captured_items(source_message_id);

-- Fast source lookups
CREATE INDEX IF NOT EXISTS idx_captured_items_source_channel
  ON captured_items(source_channel_id);

-- URL deduplication (only non-duplicate captures)
CREATE UNIQUE INDEX IF NOT EXISTS idx_captured_items_url_unique
  ON captured_items(source_url)
  WHERE source_url IS NOT NULL AND duplicate_detected = false;

-- Review queue queries (importance-ordered)
CREATE INDEX IF NOT EXISTS idx_captured_items_review_status
  ON captured_items(review_status, importance);

-- Governance review queue
CREATE INDEX IF NOT EXISTS idx_captured_items_governance_review
  ON captured_items(requires_governance_review)
  WHERE requires_governance_review = true;

-- Cache expiration sweep
CREATE INDEX IF NOT EXISTS idx_captured_items_cache_expiry
  ON captured_items(governance_cache_expires_at)
  WHERE governance_cache_expires_at IS NOT NULL;

-- Recency queries (dashboard widgets)
CREATE INDEX IF NOT EXISTS idx_captured_items_captured_at
  ON captured_items(captured_at DESC);

-- Processing queue
CREATE INDEX IF NOT EXISTS idx_captured_items_processing_status
  ON captured_items(processing_status)
  WHERE processing_status IN ('pending', 'in_progress');

-- Full-text search
CREATE INDEX IF NOT EXISTS idx_captured_item_text_search
  ON captured_item_text USING GIN(indexed_text);

-- Links by item
CREATE INDEX IF NOT EXISTS idx_captured_item_links_item
  ON captured_item_links(captured_item_id);

-- -----------------------------------------------------------------------------
-- updated_at TRIGGER
-- -----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION update_captured_items_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_captured_items_updated_at
  BEFORE UPDATE ON captured_items
  FOR EACH ROW EXECUTE FUNCTION update_captured_items_updated_at();

-- -----------------------------------------------------------------------------
-- ROW LEVEL SECURITY
-- RLS enabled on all three tables. MVP policy: service_role bypasses RLS;
-- authenticated users can read/write their own captures.
-- anon role has no access.
-- -----------------------------------------------------------------------------

ALTER TABLE captured_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE captured_item_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE captured_item_text ENABLE ROW LEVEL SECURITY;

-- captured_items: authenticated users can insert and read all rows (Captain-only workspace)
CREATE POLICY captured_items_insert ON captured_items
  FOR INSERT TO authenticated
  WITH CHECK (true);

CREATE POLICY captured_items_select ON captured_items
  FOR SELECT TO authenticated
  USING (true);

CREATE POLICY captured_items_update ON captured_items
  FOR UPDATE TO authenticated
  USING (true)
  WITH CHECK (true);

-- captured_item_links: mirrors parent access
CREATE POLICY captured_item_links_insert ON captured_item_links
  FOR INSERT TO authenticated
  WITH CHECK (true);

CREATE POLICY captured_item_links_select ON captured_item_links
  FOR SELECT TO authenticated
  USING (true);

-- captured_item_text: mirrors parent access
CREATE POLICY captured_item_text_insert ON captured_item_text
  FOR INSERT TO authenticated
  WITH CHECK (true);

CREATE POLICY captured_item_text_select ON captured_item_text
  FOR SELECT TO authenticated
  USING (true);

-- -----------------------------------------------------------------------------
-- END OF SCHEMA
-- =============================================================================
