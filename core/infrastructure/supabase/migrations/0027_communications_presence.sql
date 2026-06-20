-- ============================================================
-- Migration 0027 — Communications & Presence (USS-TJR-MSN-COMMS-001 WP1/WP7/WP8)
-- ONE consolidated, additive content-lifecycle store (opportunity -> draft ->
-- approved -> published). The published slice is the reputation portfolio (WP7).
-- The opportunity ENGINE derives candidates live from Command Memory (no copy of
-- that data here); only accepted/drafted/published items are persisted. No
-- separate content system, no duplicate repository. Additive + idempotent.
-- Captain-as-publisher: a 'published' row records what the Captain chose to
-- publish — nothing here publishes anything.
-- ============================================================

CREATE TABLE IF NOT EXISTS comms_content (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  content_id        text,                         -- grouping key, e.g. mission-USS-...-0061
  title             text NOT NULL,
  pillar            text,                          -- thought-leadership pillar key
  source_kind       text,                          -- mission|decision|lesson|capability|research|ADR|resilience|objective
  source_ref        text,                          -- the source record id
  classification    text NOT NULL DEFAULT 'publishable',
  status            text NOT NULL DEFAULT 'opportunity',
  format            text,                          -- linkedin_post|case_study|...
  strategic_domain  text,                          -- SPC-001 domain the content advances
  notes             text,
  created_at        timestamptz DEFAULT now(),
  updated_at        timestamptz DEFAULT now(),
  CONSTRAINT comms_content_classification_chk CHECK (classification IN
    ('publishable','internal_only','future_opportunity')),
  CONSTRAINT comms_content_status_chk CHECK (status IN
    ('opportunity','draft','approved','published','archived'))
);

COMMENT ON TABLE comms_content IS
  'COMMS-001 WP1/WP7/WP8: consolidated content lifecycle store (opportunity -> draft '
  '-> approved -> published). Published rows = the professional reputation portfolio. '
  'Captain-as-publisher; the system never publishes.';

CREATE INDEX IF NOT EXISTS idx_comms_content_status ON comms_content (status);
CREATE INDEX IF NOT EXISTS idx_comms_content_pillar ON comms_content (pillar);

-- WP5: content pipeline roll-up (reporting only).
CREATE OR REPLACE VIEW comms_pipeline AS
SELECT
  status,
  count(*)                                            AS items,
  count(*) FILTER (WHERE classification = 'publishable') AS publishable
FROM comms_content
GROUP BY status;

COMMENT ON VIEW comms_pipeline IS
  'COMMS-001 WP5: content counts by lifecycle status for the presence dashboard.';

-- WP7: the published reputation portfolio (reporting only).
CREATE OR REPLACE VIEW comms_portfolio AS
SELECT
  title,
  pillar,
  strategic_domain,
  format,
  updated_at
FROM comms_content
WHERE status = 'published'
ORDER BY updated_at DESC;

COMMENT ON VIEW comms_portfolio IS
  'COMMS-001 WP7: published items — the evolving professional credibility portfolio.';
