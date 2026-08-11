-- Chief Engineer follow-up (.claude/skills/bot-reviews/fixes-2026-08-09/monitoring-fixes.md,
-- item "governance_records — zero references anywhere in the repo").
--
-- governance_records was seeded into domain_registry (migration 0071) but has
-- never had a corresponding write path anywhere in the repo (Python or
-- TypeScript) beyond the seed row itself, confirmed independently via a
-- fresh repo-wide grep. Its own registry note ("Manual, mission-close-out
-- driven - low-alert domain") is consistent with there never having been an
-- automated writer. Result: it has sat permanently in run_verification_pass()'s
-- degraded list with zero real heartbeat rows, generating a false "never
-- recorded" signal rather than a genuine one.
--
-- domain_registry has no existing soft-delete/status column, so rather than
-- a hard DELETE (which would also cascade-delete any future heartbeat
-- history via domain_heartbeats' FK, and leaves no audit trail of the
-- decision), this adds the same `active boolean not null default true`
-- pattern already established by intelligence_source_registry (migration
-- 0004) and its idx_isr_active index, then deactivates governance_records.
-- Everything else in domain_registry defaults to active=true, so no other
-- domain's behavior changes.

alter table domain_registry
  add column if not exists active boolean not null default true;

create index if not exists idx_domain_registry_active on domain_registry(active);

comment on column domain_registry.active is
  'Soft-delete flag. Inactive domains are excluded from domain_heartbeat_latest and therefore from run_verification_pass() degraded-domain reporting, without losing the row or any historical domain_heartbeats it may have.';

-- Retire governance_records: no code path has ever written to it.
update domain_registry
set
  active = false,
  notes  = notes || ' -- RETIRED 2026-08-10: no write path found anywhere in the repo (Python or TypeScript) beyond this seed row; removed from monitored/degraded-domain reporting per Chief Engineer review. Re-activate if/when a real governance_records writer is built.'
where domain_key = 'governance_records';

-- Recreate domain_heartbeat_latest (from migration 0073) scoped to active
-- domains only, so retired rows silently stop appearing anywhere the view
-- is read (verification_engine.py's degraded-domain scan, infra_narrative.py),
-- while remaining fully queryable directly against domain_registry/domain_heartbeats
-- for anyone who needs the retired history.
create or replace view domain_heartbeat_latest as
select
  r.domain_key,
  r.display_name,
  r.category,
  r.expected_cadence_minutes,
  r.grace_period_minutes,
  ok.checked_at      as last_success_at,
  latest.checked_at  as last_checked_at,
  latest.status      as last_status,
  latest.error_message as last_error_message,
  (ok.checked_at is null) as never_succeeded,
  (
    ok.checked_at is null
    or ok.checked_at < now() - ((r.expected_cadence_minutes + r.grace_period_minutes) || ' minutes')::interval
  ) as is_stale
from domain_registry r
left join lateral (
  select checked_at, status, error_message
  from domain_heartbeats hb
  where hb.domain_key = r.domain_key
  order by hb.checked_at desc
  limit 1
) latest on true
left join lateral (
  select checked_at
  from domain_heartbeats hb2
  where hb2.domain_key = r.domain_key and hb2.status in ('ok', 'skipped')
  order by hb2.checked_at desc
  limit 1
) ok on true
where r.active;

comment on view domain_heartbeat_latest is
  'One row per ACTIVE domain: last proof-of-life (ok or skipped - both mean the job/source ran without error), last attempt of any status, and computed is_stale against that domain''s own cadence+grace. Backs the Sure/Unsure verification pass (spec §4.3). Retired domains (active=false, see migration 0112) are excluded entirely rather than reported as perpetually degraded.';
