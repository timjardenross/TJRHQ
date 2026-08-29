-- self-improvement-findings council follow-up (2026-08-29): orchestrator.py
-- now calls record_heartbeat('self_improvement_cycle', ...) on every run,
-- but domain_heartbeats.domain_key is a FK into domain_registry - no row
-- existed for this domain, so every write 409'd silently (record_heartbeat
-- never raises, only logs a warning; caught by running the orchestrator
-- manually and reading its own stderr). Seeding the missing row.
insert into domain_registry (domain_key, display_name, category, expected_cadence_minutes, grace_period_minutes, notes) values
  ('self_improvement_cycle', 'Self-Improvement Cycle', 'job', 1440, 240, 'scripts/self_improvement/orchestrator.py via self-improving-system.timer, daily ~07:00 Australia/Melbourne')
on conflict (domain_key) do nothing;
