-- 0243_alert_email_failure.sql
--
-- Record when an emergency email could not be sent, so the workbench can tell
-- "failed" apart from "not attempted yet". emergency_email_sent_at (0175) only
-- ever records success. intelligence/emergency_alerts.py sets this on a failed
-- send (the next 15-minute run retries); the UI ignores it once emergency_email_sent_at is set.
-- Additive, nullable, no backfill.

alter table alerts add column if not exists emergency_email_failed_at timestamptz;

comment on column alerts.emergency_email_failed_at is
  'Time of the most recent failed emergency email send for this alert (intelligence/emergency_alerts.py). Ignored once emergency_email_sent_at is set. Retried each run until emergency_email_sent_at is set.';
