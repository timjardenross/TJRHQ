-- ============================================================
-- Migration 0037 — Content Signals display field denormalization
--
-- Problem: the join between content_signals.event_id_text and
-- intelligence_events.event_id was failing silently in the portal
-- API (UUID type mismatch, stale references, or RLS). This caused
-- every signal card to show "(no title)" because the enrichment
-- step returned empty results.
--
-- Fix: store raw_title, raw_summary, canonical_url, and collected_at
-- directly on content_signals at score time. The intelligence_events
-- join is preserved as a live-data override but the stored copies
-- are the reliable fallback.
--
-- Also: corrects event_id to store the actual intelligence_events UUID
-- (previously score_and_persist() was generating a new random UUID,
-- making the FK column meaningless).
-- ============================================================

ALTER TABLE content_signals
  ADD COLUMN IF NOT EXISTS raw_title     text,
  ADD COLUMN IF NOT EXISTS raw_summary   text,
  ADD COLUMN IF NOT EXISTS canonical_url text,
  ADD COLUMN IF NOT EXISTS collected_at  timestamptz;

COMMENT ON COLUMN content_signals.raw_title IS
  'MSN-0202: denormalized from intelligence_events for resilient portal display.';

COMMENT ON COLUMN content_signals.raw_summary IS
  'MSN-0202: denormalized from intelligence_events for resilient portal display.';

COMMENT ON COLUMN content_signals.canonical_url IS
  'MSN-0202: denormalized from intelligence_events for resilient portal display.';

COMMENT ON COLUMN content_signals.collected_at IS
  'MSN-0202: copied from intelligence_events.collected_at at score time.';
