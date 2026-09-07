-- Migration 0185 — Content Workbench scheduling (MSN-0363)
--
-- Adds a scheduled publish time + optional linked Google Calendar event id
-- to comms_content, so the Content Workbench's "Coming Up" (Today view)
-- and Schedule/Publish flow (brief §5/§16) have somewhere real to persist
-- to. Both columns are nullable and purely additive — no existing row,
-- query, or RLS policy is affected. Reuses the existing Google Calendar
-- OAuth connection (lib/google-calendar.ts) rather than building a
-- parallel editorial-calendar store; calendar_event_id just lets the
-- Content Workbench find/update the event it created.

ALTER TABLE comms_content
  ADD COLUMN IF NOT EXISTS scheduled_for timestamptz,
  ADD COLUMN IF NOT EXISTS calendar_event_id text;

COMMENT ON COLUMN comms_content.scheduled_for IS
  'MSN-0363: Captain-chosen publish time for an approved/ready_to_publish item. Null means unscheduled (publish-now candidate). Independent of comms_content.status.';
COMMENT ON COLUMN comms_content.calendar_event_id IS
  'MSN-0363: Google Calendar event id created via lib/google-calendar.ts for this scheduled item, so the Content Workbench can find/update/cancel it without a second calendar system.';

CREATE INDEX IF NOT EXISTS idx_comms_content_scheduled_for
  ON comms_content (scheduled_for) WHERE scheduled_for IS NOT NULL;
