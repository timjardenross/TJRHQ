-- ============================================================
-- Migration 0036 — Content Intelligence (USS-TJR-MSN-0202)
-- Thin interpretation layer over existing intelligence and
-- communications architecture. Content Intelligence is not a
-- parallel system — it is a scoring overlay that asks:
-- "Given what we collected today, what should the Captain write about?"
--
-- New tables:
--   content_signals  — FK overlay on intelligence_events with content
--                      scoring fields (pillar, relevance, angle)
--
-- Additive columns on comms_content:
--   body, draft_generated_at, signal_source_id
--
-- Status constraint fix:
--   Adds 'review' and 'ready_to_publish' states to match pipeline.py
--
-- Source registry additions:
--   source_type_useful_life_days — parameterised recency decay per type
--   terms_reviewed               — source governance gate
--   content_source               — flag for content-oriented sources
-- ============================================================

-- ── Content signals overlay ───────────────────────────────────────────────────
-- Stores only content-specific scoring fields.
-- Title/summary/url accessed via FK to intelligence_events — never duplicated.

CREATE TABLE IF NOT EXISTS content_signals (
  id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id            uuid        NOT NULL,          -- FK to intelligence_events.event_id (text) via cast
  event_id_text       text        NOT NULL,          -- the original text event_id for lookups
  source_name         text,                          -- denormalised for display without join
  pillar_key          text,                          -- one of 8 content pillars
  pillar_name         text,                          -- denormalised for display
  content_relevance   float       DEFAULT 0.0,       -- 0–1 content strategy fit score
  captain_focus       bool        DEFAULT false,     -- aligns with active missions/priorities
  rank_score          float       DEFAULT 0.0,       -- content_ranker composite score
  suggested_angle     text,                          -- one-line framing angle for the Captain
  scored_at           timestamptz DEFAULT now(),
  suppressed          bool        DEFAULT false,
  CONSTRAINT content_signals_event_id_text_uq UNIQUE (event_id_text)  -- idempotent on re-score
);

COMMENT ON TABLE content_signals IS
  'MSN-0202: content scoring overlay on intelligence_events. Asks "should the Captain '
  'write about this?" One row per intelligence event that passes content relevance '
  'threshold. Title/summary/url read from intelligence_events via event_id_text.';

CREATE INDEX IF NOT EXISTS idx_content_signals_pillar       ON content_signals (pillar_key);
CREATE INDEX IF NOT EXISTS idx_content_signals_rank_score   ON content_signals (rank_score DESC);
CREATE INDEX IF NOT EXISTS idx_content_signals_scored_at    ON content_signals (scored_at DESC);
CREATE INDEX IF NOT EXISTS idx_content_signals_captain_focus ON content_signals (captain_focus) WHERE captain_focus = true;

-- ── Source registry additions ─────────────────────────────────────────────────
-- Parameterised useful-life decay and content governance columns.
-- Additive only — existing rows unaffected.

ALTER TABLE intelligence_source_registry
  ADD COLUMN IF NOT EXISTS source_type_label      text,
  ADD COLUMN IF NOT EXISTS useful_life_days       int  DEFAULT 14,
  ADD COLUMN IF NOT EXISTS terms_reviewed         bool DEFAULT false,
  ADD COLUMN IF NOT EXISTS content_source         bool DEFAULT false;

COMMENT ON COLUMN intelligence_source_registry.useful_life_days IS
  'MSN-0202: recency decay window for content scoring. '
  'linkedin_post=3, industry_report=60, research_paper=180, hbr_article=365, default=14.';

COMMENT ON COLUMN intelligence_source_registry.terms_reviewed IS
  'MSN-0202: source governance gate. Only sources with terms_reviewed=true '
  'are included in content signal scoring. Prevents unlicensed aggregation.';

COMMENT ON COLUMN intelligence_source_registry.content_source IS
  'MSN-0202: true for sources registered specifically for content intelligence '
  '(vs ORI sources that are also eligible).';

-- ── comms_content additions ───────────────────────────────────────────────────

ALTER TABLE comms_content
  ADD COLUMN IF NOT EXISTS body                text,
  ADD COLUMN IF NOT EXISTS draft_generated_at  timestamptz,
  ADD COLUMN IF NOT EXISTS signal_source_id    text,      -- ref to content_signals.event_id_text
  ADD COLUMN IF NOT EXISTS sensitive           bool DEFAULT false;

COMMENT ON COLUMN comms_content.body IS
  'MSN-0202: persisted draft text. Previously generated but not stored.';

COMMENT ON COLUMN comms_content.signal_source_id IS
  'MSN-0202: traceability back to the intelligence signal that prompted this opportunity.';

COMMENT ON COLUMN comms_content.sensitive IS
  'MSN-0202: content involving workplace dynamics, client relationships, or health topics '
  'that requires a caution flag and manual review path before advancing past "review".';

-- ── Status constraint fix ─────────────────────────────────────────────────────
-- pipeline.py already references 'review' and 'ready_to_publish' but migration
-- 0027 constraint did not include them. Additive fix.

ALTER TABLE comms_content
  DROP CONSTRAINT IF EXISTS comms_content_status_chk;

ALTER TABLE comms_content
  ADD CONSTRAINT comms_content_status_chk
  CHECK (status IN (
    'opportunity',
    'draft',
    'review',
    'approved',
    'ready_to_publish',
    'published',
    'archived'
  ));

-- ── Content pipeline view (extends existing comms_pipeline) ──────────────────

CREATE OR REPLACE VIEW content_pipeline_summary AS
SELECT
  status,
  count(*)                                              AS total,
  count(*) FILTER (WHERE signal_source_id IS NOT NULL)  AS from_external_signal,
  count(*) FILTER (WHERE sensitive = true)              AS sensitive_flagged,
  count(*) FILTER (WHERE body IS NOT NULL)              AS has_draft
FROM comms_content
GROUP BY status
ORDER BY
  CASE status
    WHEN 'opportunity'      THEN 1
    WHEN 'draft'            THEN 2
    WHEN 'review'           THEN 3
    WHEN 'approved'         THEN 4
    WHEN 'ready_to_publish' THEN 5
    WHEN 'published'        THEN 6
    WHEN 'archived'         THEN 7
  END;

COMMENT ON VIEW content_pipeline_summary IS
  'MSN-0202: content lifecycle counts including external signal and draft tracking.';

-- ── Anon read policies (mirrors 0035 pattern) ─────────────────────────────────

ALTER TABLE content_signals ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'content_signals' AND policyname = 'anon_read_content_signals'
  ) THEN
    EXECUTE 'CREATE POLICY anon_read_content_signals ON content_signals
      FOR SELECT USING (true)';
  END IF;
END $$;
