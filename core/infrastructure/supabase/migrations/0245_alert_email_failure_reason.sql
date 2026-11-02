-- 0245_alert_email_failure_reason.sql
--
-- Why an emergency email failed to send (0243 records only that it did). Short
-- text from core/notifications/resend_email.py (never the API key), shown next
-- to "Email FAILED" in the workbench. Additive, nullable. Apply BEFORE the
-- portal deploys: the alerts API selects it.

alter table alerts add column if not exists emergency_email_failure_reason text;

comment on column alerts.emergency_email_failure_reason is
  'Short reason the most recent emergency email send failed (e.g. "Resend rejected the send: HTTP 403 ..."). Ignored once emergency_email_sent_at is set.';
