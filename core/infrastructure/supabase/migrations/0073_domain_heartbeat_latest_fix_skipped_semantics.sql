-- Fix: a 'skipped' heartbeat (job ran, correctly decided no action needed -
-- e.g. a threshold-driven job with no actionable signal) is evidence the
-- domain is ALIVE, same as 'ok'. Only 'failed' should NOT count toward
-- liveness. The original view (migration 0071) only treated 'ok' as proof
-- of life, which would falsely stale-flag quiet-but-healthy threshold-driven
-- jobs (spec §4.3 / §9 principle: silence is a valid, positive state, and
-- must say so - conflating "correctly silent" with "gone stale" would
-- violate that).
create or replace view domain_heartbeat_latest as
select
  r.domain_key,
  r.display_name,
  r.category,
  r.expected_cadence_minutes,
  r.grace_period_minutes,
  alive.checked_at   as last_success_at,
  latest.checked_at  as last_checked_at,
  latest.status      as last_status,
  latest.error_message as last_error_message,
  (alive.checked_at is null) as never_succeeded,
  (
    alive.checked_at is null
    or alive.checked_at < now() - ((r.expected_cadence_minutes + r.grace_period_minutes) || ' minutes')::interval
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
) alive on true;

comment on view domain_heartbeat_latest is
  'One row per domain: last proof-of-life (ok or skipped - both mean the job/source ran without error), last attempt of any status, and computed is_stale against that domain''s own cadence+grace. Backs the Sure/Unsure verification pass (spec §4.3). Only "failed" heartbeats do not count as proof of life, so a domain that keeps failing loudly is correctly flagged even while a stale "ok" would otherwise mask it, and a correctly-quiet threshold-driven job is never mistaken for a dead one.';
