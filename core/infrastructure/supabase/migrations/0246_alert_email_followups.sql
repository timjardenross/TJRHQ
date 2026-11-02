-- 0246_alert_email_followups.sql
--
-- Remember what an alert looked like when we last emailed it, so a later
-- escalation or a material wording change can be emailed as an [UPDATE], and an
-- alert that has ended can be emailed once as [LIFTED]. intelligence/
-- emergency_alerts.py (_send_follow_up_emails). All additive and nullable. An
-- alert emailed before this migration has null tier/hash: it is baselined
-- silently on first sight, never emailed retroactively.
--
-- Apply BEFORE deploying the ingestion change that reads them.

alter table alerts add column if not exists emergency_email_tier text;
alter table alerts add column if not exists emergency_email_hash text;
alter table alerts add column if not exists emergency_email_last_at timestamptz;
alter table alerts add column if not exists emergency_email_lifted_at timestamptz;

comment on column alerts.emergency_email_tier is
  'Severity of the alert when it was last emailed (emergency_warning / watch_and_act / unknown for BOM high attention).';
comment on column alerts.emergency_email_hash is
  'Fingerprint of headline+location+description at the last email; a different value means the wording changed.';
comment on column alerts.emergency_email_last_at is
  'When the last email (initial or update) went out; throttles update emails.';
comment on column alerts.emergency_email_lifted_at is
  'Set once the [LIFTED] notice has been sent (or silently, for alerts that predate this migration).';
