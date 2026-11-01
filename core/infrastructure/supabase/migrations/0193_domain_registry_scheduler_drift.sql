-- 0193_domain_registry_scheduler_drift.sql
-- HQ V1 Integration QA §25 (scheduler/heartbeat consistency audit): two live
-- jobs write heartbeats with no domain_registry row, so every write silently
-- 409s (record_heartbeat never raises, only logs a warning) — same FK-409
-- class as migrations 0180/0188/0192.
--
--   google_tasks_sync     — intelligence/scheduler.py, ~every 15min
--                            (GOOGLE_TASKS_SYNC_INTERVAL_MINUTES); already in
--                            agentStatusJobs.ts's SCHEDULER_JOBS, so HQ
--                            Status has been rendering this job permanently
--                            'unknown' since it can never actually receive a
--                            recorded heartbeat.
--   episodic_memory_decay — intelligence/scheduler.py, CronTrigger Sunday
--                            03:00 (migration 0162's pruning job).

insert into domain_registry (domain_key, display_name, category, expected_cadence_minutes, grace_period_minutes, notes) values
  ('google_tasks_sync', 'Google Tasks Sync', 'job', 15, 30, 'intelligence/scheduler.py — bidirectional Ready Room/Google Tasks sync, ~every 15min'),
  ('episodic_memory_decay', 'Episodic Memory Decay', 'job', 10080, 1440, 'intelligence/scheduler.py, CronTrigger Sunday 03:00 — prunes zero-reuse research memories older than 90 days (migration 0162)')
on conflict (domain_key) do nothing;
