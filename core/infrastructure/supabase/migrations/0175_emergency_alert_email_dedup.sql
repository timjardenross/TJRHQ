-- 0175_emergency_alert_email_dedup.sql
--
-- Emergency Alert Hub email notifications (Captain-directed 2026-08-27):
-- send an email via Resend (core/notifications/resend_email.py) the first
-- time an alert reaches severity='emergency_warning'. This column is the
-- persistent dedupe state so a job restart never double-sends — same
-- discipline as domain_heartbeats being the persistent source of crawl
-- state rather than an in-memory cache.

alter table alerts add column if not exists emergency_email_sent_at timestamptz;

comment on column alerts.emergency_email_sent_at is
  'Set once an Emergency Warning-severity email notification has been sent for this alert (intelligence/emergency_alerts.py, core/notifications/resend_email.py). Persistent dedupe — survives job restarts, unlike an in-memory Map. Null means never notified.';
