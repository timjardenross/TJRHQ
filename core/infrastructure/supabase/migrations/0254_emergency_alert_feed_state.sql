-- 0254_emergency_alert_feed_state.sql
--
-- AUTHORED, NOT APPLIED. The Captain reviews and applies this. Until it is applied the orchestrator logs a warning
-- and sends no [FEED] (feed down / recovered) emails: without somewhere to remember what it already told you it would
-- repeat the email every run. Everything else is unaffected.
--
-- One row per alert source, holding whether that source is currently down or quiet and whether we have already emailed
-- about it (intelligence/emergency_alerts.py, _send_feed_emails):
--   problem      'failed' (the run failed) | 'stale' (the feed went quiet) | null (healthy)
--   consecutive  runs in a row with a problem
--   since        when the current problem started
--   emailed_at   last time a feed-down email was sent for it (a reminder follows 12 h later while it stays down)
--   detail       the error / STALE text
-- Operational state only (source names, error text). Authenticated read, service-role write.

create table if not exists emergency_alert_feed_state (
  source_key   text primary key,
  problem      text check (problem in ('failed', 'stale')),
  consecutive  integer not null default 0,
  since        timestamptz,
  emailed_at   timestamptz,
  detail       text,
  updated_at   timestamptz not null default now()
);

comment on table emergency_alert_feed_state is
  'Whether each alert source is currently down/quiet and whether a [FEED] email has been sent (intelligence/emergency_alerts.py). One row per source_key.';

alter table emergency_alert_feed_state enable row level security;

drop policy if exists emergency_alert_feed_state_read on emergency_alert_feed_state;
create policy emergency_alert_feed_state_read on emergency_alert_feed_state
  for select to authenticated using (true);
drop policy if exists emergency_alert_feed_state_service_write on emergency_alert_feed_state;
create policy emergency_alert_feed_state_service_write on emergency_alert_feed_state
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
