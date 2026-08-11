-- Migration 0031: Captured Items Maturity
-- MSN-XXXX: Add enrichment/review columns without touching 0031b constraints.
--
-- IMPORTANT: 0031b (applied 2026-06-27 on VM directly) owns the constraints on
-- source_type, item_type, and processing_status. This migration ONLY adds columns
-- that 0031b did not add. Do not re-define those constraints here.
--
-- 0031b live allowed values (do not conflict):
--   source_type:       channel_message|channel_file|telegram_voice|command_centre|portal_quick_capture
--   item_type:         url|text_note|file|image|screenshot|note|idea|health|decision|task
--   processing_status: pending|in_progress|completed|failed|routed|dismissed
--
-- This migration adds:
--   classification, importance, review_status, requires_review,
--   ai_enrichment_status, summary, routed_to_table, routed_to_id,
--   plus source envelope columns if not already present.

-- ── 1. Source envelope columns (safe — IF NOT EXISTS) ─────────────────────────

ALTER TABLE public.captured_items
  ADD COLUMN IF NOT EXISTS source_type            text,
  ADD COLUMN IF NOT EXISTS source_channel_id      text,
  ADD COLUMN IF NOT EXISTS source_message_id      text,
  ADD COLUMN IF NOT EXISTS source_message_ts      text,
  ADD COLUMN IF NOT EXISTS source_message_permalink text,
  ADD COLUMN IF NOT EXISTS source_url             text,
  ADD COLUMN IF NOT EXISTS source_user_id         text,
  ADD COLUMN IF NOT EXISTS captured_by            text,
  ADD COLUMN IF NOT EXISTS title                  text,
  ADD COLUMN IF NOT EXISTS raw_text               text;

-- ── 2. Classification + routing columns ───────────────────────────────────────

ALTER TABLE public.captured_items
  ADD COLUMN IF NOT EXISTS classification       text NOT NULL DEFAULT 'unclassified',
  ADD COLUMN IF NOT EXISTS importance           text NOT NULL DEFAULT 'medium',
  ADD COLUMN IF NOT EXISTS review_status        text NOT NULL DEFAULT 'unreviewed',
  ADD COLUMN IF NOT EXISTS requires_review      boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS ai_enrichment_status text NOT NULL DEFAULT 'not_enriched',
  ADD COLUMN IF NOT EXISTS summary              jsonb,
  ADD COLUMN IF NOT EXISTS routed_to_table      text,
  ADD COLUMN IF NOT EXISTS routed_to_id         uuid;

-- ── 3. Constraints for NEW columns only (not owned by 0031b) ─────────────────

ALTER TABLE public.captured_items
  DROP CONSTRAINT IF EXISTS captured_items_classification_check,
  DROP CONSTRAINT IF EXISTS captured_items_importance_check,
  DROP CONSTRAINT IF EXISTS captured_items_review_status_check,
  DROP CONSTRAINT IF EXISTS captured_items_ai_enrichment_status_check;

ALTER TABLE public.captured_items
  ADD CONSTRAINT captured_items_classification_check
    CHECK (classification IN ('reference', 'mission', 'personal', 'research',
                              'decision', 'unclassified')),
  ADD CONSTRAINT captured_items_importance_check
    CHECK (importance IN ('low', 'medium', 'high')),
  ADD CONSTRAINT captured_items_review_status_check
    CHECK (review_status IN ('unreviewed', 'reviewed', 'actioned')),
  ADD CONSTRAINT captured_items_ai_enrichment_status_check
    CHECK (ai_enrichment_status IN ('not_enriched', 'queued', 'enriched', 'failed'));

-- ── 4. Indexes ────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS captured_items_review_status_idx
  ON public.captured_items (review_status);

CREATE INDEX IF NOT EXISTS captured_items_classification_idx
  ON public.captured_items (classification);

CREATE INDEX IF NOT EXISTS captured_items_source_channel_idx
  ON public.captured_items (source_channel_id);

CREATE INDEX IF NOT EXISTS captured_items_captured_by_idx
  ON public.captured_items (captured_by);

CREATE INDEX IF NOT EXISTS captured_items_ai_enrichment_status_idx
  ON public.captured_items (ai_enrichment_status);

CREATE UNIQUE INDEX IF NOT EXISTS captured_items_source_message_id_uniq
  ON public.captured_items (source_message_id)
  WHERE source_message_id IS NOT NULL;

-- ── 5. Backfill defaults for existing rows ────────────────────────────────────

UPDATE public.captured_items
  SET ai_enrichment_status = 'not_enriched'
  WHERE ai_enrichment_status IS NULL;

UPDATE public.captured_items
  SET classification = 'unclassified'
  WHERE classification IS NULL;

UPDATE public.captured_items
  SET review_status = 'unreviewed'
  WHERE review_status IS NULL;
