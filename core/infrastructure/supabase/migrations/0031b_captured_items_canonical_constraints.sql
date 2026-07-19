-- Migration 0031b: Canonical captured_items constraints
--
-- Supersedes 0031 (which used non-canonical values: 'command-centre' hyphen,
-- 'manual', 'slack', 'pending_decision').
--
-- Applied 2026-06-27. Constraint names confirmed via pg_constraint query before
-- DROP — avoids IF NOT EXISTS footgun on named constraints.
--
-- Source of truth: MSN-DISCOVERY schema as observed in live Supabase project
-- cjvrpjwewsrumnbdydgg, expanded to cover all active capture surfaces.

-- ── source_type ───────────────────────────────────────────────────────────────
ALTER TABLE public.captured_items
  DROP CONSTRAINT IF EXISTS captured_items_source_type_check;

ALTER TABLE public.captured_items
  ADD CONSTRAINT captured_items_source_type_check
  CHECK (source_type IN (
    'channel_message',      -- Slack message (existing)
    'channel_file',         -- Slack file attachment (existing)
    'telegram_voice',       -- XO Telegram voice-to-capture
    'command_centre',       -- LCARS Command Centre quick-capture (underscore)
    'portal_quick_capture'  -- LCARS Portal quick-capture widget
  ));

-- ── item_type ─────────────────────────────────────────────────────────────────
ALTER TABLE public.captured_items
  DROP CONSTRAINT IF EXISTS captured_items_item_type_check;

ALTER TABLE public.captured_items
  ADD CONSTRAINT captured_items_item_type_check
  CHECK (item_type IN (
    'url',        -- Slack: link capture (existing)
    'text_note',  -- Slack: text note (existing)
    'file',       -- Slack: file upload (existing)
    'image',      -- Slack: image (existing)
    'screenshot', -- Slack: screenshot (existing)
    'note',       -- voice / CC: general note, thing_to_do
    'idea',       -- voice / CC: mission_idea, content_idea
    'health',     -- voice / CC: recovery_pulse
    'decision',   -- voice / CC: decision record
    'task'        -- CC: task item
  ));

-- ── processing_status ────────────────────────────────────────────────────────
ALTER TABLE public.captured_items
  DROP CONSTRAINT IF EXISTS captured_items_processing_status_check;

ALTER TABLE public.captured_items
  ADD CONSTRAINT captured_items_processing_status_check
  CHECK (processing_status IN (
    'pending',      -- Awaiting triage (default)
    'in_progress',  -- Being processed
    'completed',    -- Processing done
    'failed',       -- Processing failed
    'routed',       -- Routed to downstream table (missions, captains_log, etc.)
    'dismissed'     -- Dismissed without routing
    -- NOTE: 'pending_decision' removed — decisions stay 'pending' for human triage
  ));
