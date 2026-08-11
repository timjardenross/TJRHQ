-- ============================================================
-- Migration 0096 — captain_focus on comms_content (COMMS-002 follow-up to 0095)
--
-- Persisted rather than derived from research_angle text-matching, so the
-- Content Workbench's "Captain Priority" badge is a real stored signal, not a
-- string-match on a field the human can freely edit.
-- ============================================================

ALTER TABLE comms_content
  ADD COLUMN IF NOT EXISTS captain_focus boolean DEFAULT false;

COMMENT ON COLUMN comms_content.captain_focus IS
  'COMMS-002: mirrors content_signals.captain_focus — true when the capture-time '
  'scorer (lib/contentScoring.ts) matched a captain-focus keyword. Set once at '
  'capture in /api/content-workbench/capture, not recomputed on edit.';
