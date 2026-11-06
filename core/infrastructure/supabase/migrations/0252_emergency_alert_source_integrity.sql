-- 0252_emergency_alert_source_integrity.sql
--
-- AUTHORED, NOT APPLIED. The Captain reviews and applies this. Until it is applied the
-- orchestrator logs a warning and carries on (the write is best-effort), so deploying the
-- code first is harmless; the digest section and the portal integrity panel simply stay empty.
--
-- One row per alert source, overwritten on every emergency-alert run (batched into a single
-- upsert per run), holding what that run's drop ledger saw. It turns the integrity text that
-- only lives inside the heartbeat `detail` string into queryable data for the portal and
-- the daily digest ("what is the hub currently dropping, and is any feed going quiet?").
--
--   status         'ok' or 'failed' (failed = the integrity gate rejected the run)
--   items_seen     raw items the adapter looked at, before any exclusion
--   accepted       alerts produced
--   excluded       {reason: count}        deliberate, Captain-directed filters
--   invalid        {reason: count}        structural failures
--   unmapped       {label: count}         unrecognised tier labels / new BOM products
--   samples        {ledger key: [headline, ...]}  up to 3 public feed titles per reason
--   newest_item_at newest source-side timestamp across every item looked at
--   warnings       ["STALE: ...", "FIELD DRIFT: ...", "WARNING: x% invalid ..."]
--
-- Public feed titles and counts only: no site data, no secrets. Authenticated read (the 0239
-- end state), service-role write. Additive; nothing existing is altered.

create table if not exists emergency_alert_source_integrity (
  source_key      text primary key,
  checked_at      timestamptz not null default now(),
  status          text not null check (status in ('ok', 'failed')),
  items_seen      integer not null default 0,
  accepted        integer not null default 0,
  excluded        jsonb not null default '{}'::jsonb,
  invalid         jsonb not null default '{}'::jsonb,
  unmapped        jsonb not null default '{}'::jsonb,
  samples         jsonb not null default '{}'::jsonb,
  newest_item_at  timestamptz,
  warnings        jsonb not null default '[]'::jsonb,
  updated_at      timestamptz not null default now()
);

comment on table emergency_alert_source_integrity is
  'Latest drop-ledger result per alert source (intelligence/emergency_alerts.py). One row per source_key, overwritten each run.';

alter table emergency_alert_source_integrity enable row level security;

drop policy if exists emergency_alert_source_integrity_read on emergency_alert_source_integrity;
create policy emergency_alert_source_integrity_read on emergency_alert_source_integrity
  for select to authenticated using (true);
drop policy if exists emergency_alert_source_integrity_service_write on emergency_alert_source_integrity;
create policy emergency_alert_source_integrity_service_write on emergency_alert_source_integrity
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
