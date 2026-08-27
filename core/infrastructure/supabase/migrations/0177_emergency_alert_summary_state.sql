-- 0177_emergency_alert_summary_state.sql
--
-- Hourly Emergency Alert Hub summary email (Captain-directed 2026-08-27):
-- "post the event cycle running each hour, produce an email summary using
-- an LLM". Only fires when something actually changed — this single-row
-- state table holds a fingerprint of the last-sent active-alert set so
-- the hourly job's default case (nothing changed) is a cheap DB diff, not
-- an LLM call or email send.

create table if not exists emergency_alert_summary_state (
  id                 int primary key default 1,
  last_fingerprint   text,
  last_sent_at       timestamptz,
  constraint emergency_alert_summary_state_singleton check (id = 1)
);

comment on table emergency_alert_summary_state is
  'Single-row state for the hourly Emergency Alert Hub summary email (intelligence/emergency_alert_summary.py). last_fingerprint is a hash of the current active-alert set (id+severity+status); the hourly job only calls the LLM and sends an email when this changes, so an unchanged hour is a cheap DB diff, not an LLM call.';

alter table emergency_alert_summary_state enable row level security;
drop policy if exists emergency_alert_summary_state_read on emergency_alert_summary_state;
create policy emergency_alert_summary_state_read on emergency_alert_summary_state for select using (true);
drop policy if exists emergency_alert_summary_state_service_write on emergency_alert_summary_state;
create policy emergency_alert_summary_state_service_write on emergency_alert_summary_state
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');

insert into domain_registry (domain_key, display_name, category, expected_cadence_minutes, grace_period_minutes, notes) values
  ('emergency_alert_hourly_summary', 'Emergency Alert Hub — Hourly Summary Email', 'job', 60, 30, 'intelligence/emergency_alert_summary.py — checks hourly, only calls LLM/sends email when the active-alert set changed since last send')
on conflict (domain_key) do nothing;
