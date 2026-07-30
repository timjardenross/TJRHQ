-- STARSHIP-REDESIGN.md §4 verification engine.
-- Generalizes the intelligence_source_health pattern (migration 0004)
-- platform-wide: every domain - external data source, internal job, and
-- infra/process signal - heartbeats through this same table. Per spec §4.1
-- this is non-negotiable: internal self-health is watched by the same
-- pipeline that watches the outside world, not a separate mechanism.
--
-- Note: an existing `system_heartbeat` table (component/status/created_at)
-- already exists but only tracks a single Supabase pg_cron liveness ping
-- (component='supabase_cron', once daily) - it has no domain concept, no
-- cadence/grace model, and is not generalized here. It is left untouched.

create table if not exists domain_registry (
  domain_key                text primary key,
  display_name              text not null,
  category                  text not null check (category in ('data','job','infra')),
  expected_cadence_minutes  int  not null,
  grace_period_minutes      int  not null,
  notes                     text,
  created_at                timestamptz not null default now()
);

comment on table domain_registry is
  'Static config: one row per domain (data source, internal job, or infra/process signal). expected_cadence_minutes + grace_period_minutes define when a domain counts as missed. Populated by the Phase 0 docs/DOMAINS.md inventory.';

create table if not exists domain_heartbeats (
  heartbeat_id   uuid primary key default gen_random_uuid(),
  domain_key     text not null references domain_registry(domain_key) on delete cascade,
  checked_at     timestamptz not null default now(),
  status         text not null check (status in ('ok','failed','skipped')),
  detail         text,
  error_message  text,
  latency_ms     int
);

create index if not exists idx_domain_heartbeats_domain_key on domain_heartbeats(domain_key);
create index if not exists idx_domain_heartbeats_checked_at on domain_heartbeats(checked_at desc);

comment on table domain_heartbeats is
  'Rolling event log, one row per run attempt of a domain (mirrors intelligence_source_health / migration 0004). Latest ok row per domain_key gives last-success-at; a domain with zero rows is exactly as visible as one with stale rows - never silently dropped.';

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
  where hb2.domain_key = r.domain_key and hb2.status = 'ok'
  order by hb2.checked_at desc
  limit 1
) ok on true;

comment on view domain_heartbeat_latest is
  'One row per domain: last success, last attempt (any status), and computed is_stale against that domain''s own cadence+grace. Backs the Sure/Unsure verification pass (spec §4.3). is_stale is driven by last SUCCESS, not last attempt, so a domain that keeps failing loudly is correctly flagged even if it never lapses into silence.';

create table if not exists verification_state (
  state_id           uuid primary key default gen_random_uuid(),
  computed_at        timestamptz not null default now(),
  state              text not null check (state in ('sure','unsure')),
  degraded_domains   jsonb not null default '[]'::jsonb,
  reason             text
);

create index if not exists idx_verification_state_computed_at on verification_state(computed_at desc);

comment on table verification_state is
  'One row per verification pass run (spec §4). state is sure/unsure only - the pass never asserts blind about itself, since a pass that cannot run cannot self-report. blind is derived downstream (API endpoint / dead-man''s switch) by checking whether computed_at itself has gone stale against this table''s own expected cadence. degraded_domains is a small JSON array of {domain_key, display_name} for the plain-language degradation copy in spec §4.3 (e.g. "the Telstra feed").';

alter table domain_registry enable row level security;
alter table domain_heartbeats enable row level security;
alter table verification_state enable row level security;

drop policy if exists domain_registry_read on domain_registry;
create policy domain_registry_read on domain_registry for select using (true);

drop policy if exists domain_heartbeats_read on domain_heartbeats;
create policy domain_heartbeats_read on domain_heartbeats for select using (true);

drop policy if exists verification_state_read on verification_state;
create policy verification_state_read on verification_state for select using (true);

drop policy if exists domain_registry_service_write on domain_registry;
create policy domain_registry_service_write on domain_registry
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');

drop policy if exists domain_heartbeats_service_write on domain_heartbeats;
create policy domain_heartbeats_service_write on domain_heartbeats
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');

drop policy if exists verification_state_service_write on verification_state;
create policy verification_state_service_write on verification_state
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');

-- Seed the domain registry per docs/DOMAINS.md (Phase 0 inventory).
insert into domain_registry (domain_key, display_name, category, expected_cadence_minutes, grace_period_minutes, notes) values
  ('missions', 'Mission Registry', 'data', 1440, 720, 'Slack/Telegram-driven updates; daily stale-check in platform-runtime/proactive_scheduler.py'),
  ('decisions', 'Decisions Ledger', 'data', 10080, 2880, 'Event-driven; Friday 16:00 weekly review'),
  ('health_daily_logs', 'Daily Health Log', 'data', 1440, 720, 'Captain-authored daily check-in'),
  ('weekly_health_synthesis', 'Weekly Health Synthesis', 'job', 10080, 1440, 'core/health/weekly_synthesis.py, Saturday 08:00'),
  ('lessons_learned', 'Lessons Learned', 'data', 10080, 4320, 'Event-driven at mission/decision close'),
  ('insight_outcomes', 'Insight Outcomes', 'data', 10080, 4320, 'Event-driven, feeds confidence calibration'),
  ('engineering_handoff', 'Engineering Handoff / Delivery Ledger', 'job', 15, 30, 'deploy/delivery-reconciler.timer, every 15 min'),
  ('intelligence_collection', 'Intelligence Source Collection', 'job', 1440, 240, 'intelligence/scheduler.py daily collection 06:00; rolls up the existing intelligence_source_health per-source detail'),
  ('captains_daily_briefs', 'Captain''s Daily Briefs', 'job', 780, 180, 'intelligence/scheduler.py, 07:00/12:30/18:00 daily'),
  ('human_systems', 'Human Systems / Capacity Advisor', 'job', 1440, 360, 'platform-runtime/human_systems_scheduler.py, morning/evening/weekly/degradation jobs'),
  ('physical_readiness', 'Physical Readiness', 'data', 10080, 10080, 'Captain-paced, no fixed cadence expected - generous grace, low-alert domain'),
  ('recovery_pulses', 'Recovery Pulses', 'data', 480, 240, 'Expected ~4x/day via Telegram recovery_officer bot - write point not yet wired, see Phase 1 report'),
  ('captains_log', 'Captain''s Log', 'data', 1440, 720, 'Captain-authored daily reflection'),
  ('knowledge_library', 'Knowledge Library Ingestion', 'job', 60, 60, 'core/infrastructure/vm-processing worker + healthcheck; already had a real per-pipeline healthcheck, now folded in here'),
  ('content_intelligence', 'Content Intelligence', 'job', 1440, 240, 'Part of the daily intelligence/ingestion/collection_engine.py run'),
  ('governance_records', 'Governance / Capability Records', 'data', 40320, 10080, 'Manual, mission-close-out driven - low-alert domain'),
  ('advisory_sessions', 'Advisory Council Sessions', 'data', 10080, 10080, 'On-demand, non-persistent process - low-alert domain'),
  ('captured_items', 'Captured Items (Captain''s Inbox)', 'data', 60, 60, 'Event-driven on capture; async classification'),
  ('core_events', 'Core Event Bus', 'infra', 30, 30, 'Continuous, via core/platform/event_bus.py'),
  ('command_centre_backend', 'Command Centre Backend (port 5000)', 'infra', 5, 10, 'HTTP health check, same probe as core/coordination/command_bus.py _backend_healthy()'),
  ('verification_engine', 'Verification Engine (self)', 'infra', 5, 15, 'Self-heartbeat - the pass reports its own successful completion here, per spec''s non-negotiable internal-self-health rule')
on conflict (domain_key) do nothing;
