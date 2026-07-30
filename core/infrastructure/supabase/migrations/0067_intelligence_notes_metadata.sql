-- Migration 0067 — Intelligence Notes Provenance (MSN-0336)
--
-- intelligence_notes had no metadata/provenance column at all. The
-- Capture Promotion Bridge (captured_items -> intelligence_notes) needs
-- somewhere to record full provenance without lossily cramming multiple
-- distinct facts (source captured_item id, source channel, capture
-- timestamp, author, promotion timestamp, promotion reason) into
-- unrelated existing text fields (source/source_url/tags). Matches the
-- same additive pattern already used successfully for
-- knowledge_documents.metadata (MSN-0332/0333).

ALTER TABLE public.intelligence_notes
  ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN public.intelligence_notes.metadata IS
  'MSN-0336: full provenance envelope when this note originated from a '
  'promoted captured_item -- captured_item_id, source_channel, '
  'captured_at, captured_by, promoted_at, promotion_reason. Empty {} '
  'for notes created directly (the existing Notebook web form, Slack '
  '/note-capture) -- those already have no promotion provenance to record.';
