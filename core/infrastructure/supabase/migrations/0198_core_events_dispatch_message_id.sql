-- ============================================================
-- Migration 0198 — core_events.dispatch_message_id
--
-- interrupt_dispatcher.py's notify() call gets a Telegram message_id back
-- in its NotificationResult but never persisted it anywhere — confirmed
-- 2026-09-10 while trying to clean up 4 events dispatched under the
-- pre-PR#94 bare-text bug: no stored reference meant the bad messages
-- couldn't be deleted/edited via the Bot API, only worked around by
-- resetting status and letting a corrected message go out alongside them.
-- Additive column so the next time a dispatch needs correcting, the
-- message it produced is actually addressable.
-- ============================================================

ALTER TABLE core_events
    ADD COLUMN IF NOT EXISTS dispatch_message_id bigint;

COMMENT ON COLUMN core_events.dispatch_message_id IS
  'Telegram message_id returned by notification_service.notify() when '
  'interrupt_dispatcher.py dispatches this event (INTERRUPT_NOW push). '
  'NULL for events never dispatched, or dispatched before this column '
  'existed. Lets a bad/duplicate push be deleted or edited later instead '
  'of only ever being supersede-by-resend.';
