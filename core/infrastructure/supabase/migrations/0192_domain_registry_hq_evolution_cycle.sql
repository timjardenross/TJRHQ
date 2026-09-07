-- 0192_domain_registry_hq_evolution_cycle.sql
-- Same FK-409 class as migrations 0180 (self_improvement_cycle) and 0188
-- (intraday_media_collection): evolution_orchestrator.py now calls
-- record_heartbeat('hq_evolution_cycle', ...) on every run (deploy/
-- hq-evolution.timer, daily ~03:00 Australia/Melbourne), but
-- domain_heartbeats.domain_key is a FK into domain_registry — no row
-- exists for this domain yet, so every write would 409 silently
-- (record_heartbeat never raises, only logs a warning). Seeding it before
-- the timer goes live, not after a day of silently-dropped heartbeats.

insert into domain_registry (domain_key, display_name, category, expected_cadence_minutes, grace_period_minutes, notes) values
  ('hq_evolution_cycle', 'HQ Evolution Cycle', 'job', 1440, 240, 'scripts/self_improvement/evolution_orchestrator.py via hq-evolution.timer, daily ~03:00 Australia/Melbourne — overnight discovery/investigation only, never remediates or creates Missions')
on conflict (domain_key) do nothing;
