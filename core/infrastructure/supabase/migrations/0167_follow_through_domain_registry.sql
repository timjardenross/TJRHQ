-- ============================================================
-- Migration 0167 — Domain registry rows for Follow-Through
-- USS Starship Endeavour NCC-170230
--
-- Registers the follow_through_engine job (the adhd_task_nudge
-- scheduler slot, repurposed per this mission) with Agent & Job
-- Status. Also backfills adhd_task_nudge itself, which was confirmed
-- missing from domain_registry despite the job writing heartbeats
-- every run since it shipped — it has been invisible to the Agent &
-- Job Status workbench this whole time. Cheap, clearly-correct fix
-- while touching this exact system.
--
-- Additive & idempotent. Safe to re-run.
-- ============================================================

INSERT INTO domain_registry (domain_key, display_name, category, expected_cadence_minutes, grace_period_minutes, notes)
VALUES
  ('adhd_task_nudge', 'ADHD Task Nudge (legacy slot)', 'job', 60, 30,
   'intelligence/scheduler.py IntervalTrigger, ADHD_NUDGE_INTERVAL_MINUTES (default 60). Backfilled 2026-08-23 — job has run and written heartbeats since Issue 26 but was never registered, so it was invisible to Agent & Job Status.'),
  ('follow_through_engine', 'Adaptive Follow-Through Engine', 'job', 60, 30,
   'intelligence/adhd/follow_through_engine.py, run via the adhd_task_nudge job slot in intelligence/scheduler.py. Scans personal_tasks for due follow-through and dispatches via XO.')
ON CONFLICT (domain_key) DO NOTHING;
