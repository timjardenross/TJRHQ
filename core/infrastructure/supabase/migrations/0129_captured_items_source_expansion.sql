-- Migration 0031: Expand captured_items constraints for multi-source capture
--
-- The MSN-DISCOVERY migration scoped captured_items to Slack-only sources
-- (channel_message | channel_file) and Slack-only item types (url | text_note | ...).
--
-- This migration expands all three constrained enums to cover:
--   - Command Centre quick-capture (source: command-centre)
--   - Telegram XO voice notes    (source: telegram_voice)
--   - Future manual / Slack      (source: manual, slack)
--   - Command Centre item types  (note, idea, health, decision)
--   - capture.js routing states  (pending_decision, routed, dismissed)

-- ── source_type ───────────────────────────────────────────────────────────────
ALTER TABLE public.captured_items
  DROP CONSTRAINT IF EXISTS captured_items_source_type_check;

ALTER TABLE public.captured_items
  ADD CONSTRAINT captured_items_source_type_check
  CHECK (source_type IN (
    'channel_message',  -- Slack message (existing)
    'channel_file',     -- Slack file attachment (existing)
    'command-centre',   -- LCARS / Command Centre quick-capture
    'telegram_voice',   -- XO Telegram voice-to-capture
    'manual',           -- Direct / unattributed entry
    'slack'             -- Slack generic (future)
  ));

-- ── item_type ─────────────────────────────────────────────────────────────────
ALTER TABLE public.captured_items
  DROP CONSTRAINT IF EXISTS captured_items_item_type_check;

ALTER TABLE public.captured_items
  ADD CONSTRAINT captured_items_item_type_check
  CHECK (item_type IN (
    'url',          -- Slack: link capture (existing)
    'text_note',    -- Slack: text note (existing)
    'file',         -- Slack: file upload (existing)
    'image',        -- Slack: image (existing)
    'screenshot',   -- Slack: screenshot (existing)
    'note',         -- Command Centre / voice: general note, thing_to_do
    'idea',         -- Command Centre / voice: mission_idea, content_idea
    'health',       -- Command Centre / voice: recovery_pulse
    'decision'      -- Command Centre / voice: decision record
  ));

-- ── processing_status ────────────────────────────────────────────────────────
ALTER TABLE public.captured_items
  DROP CONSTRAINT IF EXISTS captured_items_processing_status_check;

ALTER TABLE public.captured_items
  ADD CONSTRAINT captured_items_processing_status_check
  CHECK (processing_status IN (
    'pending',           -- Awaiting triage (default)
    'in_progress',       -- Being processed (existing)
    'completed',         -- Processing done (existing)
    'failed',            -- Processing failed (existing)
    'pending_decision',  -- Decision item awaiting Captain review
    'routed',            -- Routed to downstream table (missions, log, etc.)
    'dismissed'          -- Dismissed without routing
  ));
