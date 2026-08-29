-- Decommissioning-discipline drift check (2026-08-29) caught this: recovery_pulses
-- has been flagged stale in domain_heartbeat_latest since 2026-08-21, and a direct
-- check confirms why - last row written 2026-08-22, 0 rows since. This matches the
-- MY CAPACITY TODAY full-stack migration (2026-08-22, same day) which replaced
-- recovery_pulses everywhere with capacity_checkins as the sole capture path. The
-- table is still read by plenty of legacy code (history/display), but nothing
-- writes to it anymore - the domain_registry row was never updated after that
-- migration, so it sat generating a false "degraded" signal for a week.
--
-- Same active=false soft-delete pattern as migration 0112 (governance_records) -
-- keeps the row and any heartbeat history, just excludes it from
-- domain_heartbeat_latest / run_verification_pass() degraded-domain reporting.
update domain_registry
set
  active = false,
  notes  = notes || ' -- RETIRED 2026-08-29: superseded by capacity_checkins as the sole capture path per the 2026-08-22 MY CAPACITY TODAY migration; last real write 2026-08-22, confirmed via direct table query. Re-activate only if recovery_pulses regains a real writer.'
where domain_key = 'recovery_pulses';

-- The replacement was never registered either - retiring the old domain
-- without seeding the new one just recreates the same gap in the other
-- direction. Confirmed live: 16 rows in the last 7 days, latest today.
insert into domain_registry (domain_key, display_name, category, expected_cadence_minutes, grace_period_minutes, notes) values
  ('capacity_checkins', 'Capacity Check-ins', 'data', 480, 240, 'Sole health-capture path since the 2026-08-22 MY CAPACITY TODAY migration (replaces recovery_pulses, see this migration''s retirement above). Written via Telegram capacitybot + LCARS portal + Command Centre.')
on conflict (domain_key) do nothing;
