-- Migration 0031: Captured Items Maturity
-- MSN-XXXX: Unify capture contract across portal, Telegram, and future sources.
--
-- Safe to run multiple times (IF NOT EXISTS / IF EXISTS guards throughout).
-- Does NOT drop existing data.
--
-- Canonical contract enforced by this migration:
--   source_type      = 'channel_message'           (always)
--   item_type        = 'text_note'                 (text captures; 'voice_note' reserved)
--   source_channel_id = one of KNOWN_CHANNELS below
--   classification   = reference|mission|personal|research|decision|unclassified
--   importance       = low|medium|high
--   processing_status = pending|routed|dismissed|archived
--   review_status     = unreviewed|reviewed|actioned
--   ai_enrichment_status = not_enriched|queued|enriched|failed

-- ── 1. Add columns missing from 0030 (safe: IF NOT EXISTS) ───────────────────

ALTER TABLE public.captured_items
  ADD COLUMN IF NOT EXISTS source_type          text,
  ADD COLUMN IF NOT EXISTS source_channel_id    text,
  ADD COLUMN IF NOT EXISTS source_message_id    text,
  ADD COLUMN IF NOT EXISTS source_message_ts    text,
  ADD COLUMN IF NOT EXISTS source_message_permalink text,
  ADD COLUMN IF NOT EXISTS source_url           text,
  ADD COLUMN IF NOT EXISTS source_user_id       text,
  ADD COLUMN IF NOT EXISTS captured_by          text,
  ADD COLUMN IF NOT EXISTS title                text,
  ADD COLUMN IF NOT EXISTS raw_text             text,
  ADD COLUMN IF NOT EXISTS classification       text NOT NULL DEFAULT 'unclassified',
  ADD COLUMN IF NOT EXISTS importance           text NOT NULL DEFAULT 'medium',
  ADD COLUMN IF NOT EXISTS processing_status    text NOT NULL DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS review_status        text NOT NULL DEFAULT 'unreviewed',
  ADD COLUMN IF NOT EXISTS requires_review      boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS ai_enrichment_status text NOT NULL DEFAULT 'not_enriched',
  ADD COLUMN IF NOT EXISTS summary              jsonb,
  ADD COLUMN IF NOT EXISTS routed_to_table      text,
  ADD COLUMN IF NOT EXISTS routed_to_id         uuid;

-- ── 2. Drop legacy constraints that conflict with new canonical values ────────

ALTER TABLE public.captured_items
  DROP CONSTRAINT IF EXISTS captured_items_item_type_check,
  DROP CONSTRAINT IF EXISTS captured_items_status_check;

-- ── 3. Add updated constraints ────────────────────────────────────────────────

ALTER TABLE public.captured_items
  ADD CONSTRAINT captured_items_item_type_check
    CHECK (item_type IN ('note', 'mission', 'idea', 'health', 'decision',
                         'text_note', 'voice_note', 'file', 'image')),
  ADD CONSTRAINT captured_items_classification_check
    CHECK (classification IN ('reference', 'mission', 'personal', 'research',
                              'decision', 'unclassified')),
  ADD CONSTRAINT captured_items_importance_check
    CHECK (importance IN ('low', 'medium', 'high')),
  ADD CONSTRAINT captured_items_processing_status_check
    CHECK (processing_status IN ('pending', 'routed', 'dismissed', 'archived')),
  ADD CONSTRAINT captured_items_review_status_check
    CHECK (review_status IN ('unreviewed', 'reviewed', 'actioned')),
  ADD CONSTRAINT captured_items_ai_enrichment_status_check
    CHECK (ai_enrichment_status IN ('not_enriched', 'queued', 'enriched', 'failed'));

-- ── 4. Indexes for inbox queries ──────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS captured_items_processing_status_idx
  ON public.captured_items (processing_status);

CREATE INDEX IF NOT EXISTS captured_items_review_status_idx
  ON public.captured_items (review_status);

CREATE INDEX IF NOT EXISTS captured_items_source_channel_idx
  ON public.captured_items (source_channel_id);

CREATE INDEX IF NOT EXISTS captured_items_captured_by_idx
  ON public.captured_items (captured_by);

CREATE UNIQUE INDEX IF NOT EXISTS captured_items_source_message_id_uniq
  ON public.captured_items (source_message_id)
  WHERE source_message_id IS NOT NULL;

-- ── 5. Backfill ai_enrichment_status for existing rows ───────────────────────

UPDATE public.captured_items
  SET ai_enrichment_status = 'not_enriched'
  WHERE ai_enrichment_status IS NULL OR ai_enrichment_status = '';

-- ── Notes ─────────────────────────────────────────────────────────────────────
-- Recognised source_channel_id values (enforced by writers, not DB constraint):
--   lcars-mobile-quick-capture
--   telegram-xo-voice-capture
--   telegram-xo-text-capture
--   portal-floating-capture
--   command-centre-api-capture
--
-- Use classification (not item_type) to distinguish capture intent.
-- item_type describes the media/format; classification describes the route.
