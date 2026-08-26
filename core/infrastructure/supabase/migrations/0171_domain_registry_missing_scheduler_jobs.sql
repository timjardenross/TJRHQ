-- 0171_domain_registry_missing_scheduler_jobs.sql
--
-- Root cause found 2026-08-25 of ~9 of the 21 "never heartbeated" jobs on
-- the Agent Status workbench: domain_heartbeats.domain_key is a foreign
-- key against domain_registry(domain_key) (migration 0071). Every one of
-- these jobs runs its business logic successfully (confirmed via
-- journalctl) and calls record_heartbeat() correctly, but was never
-- inserted into domain_registry — so every write silently 409 Conflicts.
-- Previously invisible (intelligence/scheduler.py's heartbeat wrapper
-- swallowed the exception with a bare `except: pass`); now logged as a
-- warning per today's companion fix, and confirmed live in journalctl for
-- evolved_captain_insight_generation and downdetector_priority_tiered_collection
-- at tonight's 18:37/18:38 restart.
--
-- This is exactly why mission_registry_sync (registered in migration
-- 0083) succeeds at its 06:45 daily slot while source_fidelity_audit
-- (same time, same scheduler, unregistered) does not.

insert into domain_registry (domain_key, display_name, category, expected_cadence_minutes, grace_period_minutes, notes) values
  ('intraday_status_collection',              'Intraday Status Collection',            'job', 180,  60,   'intelligence/scheduler.py, interval INTRADAY_STATUS_INTERVAL_MINUTES (default 180min) — found unregistered 2026-08-25, job runs fine, heartbeat writes were 409ing on the domain_registry FK'),
  ('intelligence_suppression_audit',           'Intelligence Suppression Audit',         'job', 1440, 240,  'intelligence/scheduler.py, daily 06:40 — found unregistered 2026-08-25, same FK-409 class as intraday_status_collection'),
  ('health_mission_correlation',                'Health-Mission Correlation',             'job', 1440, 240,  'intelligence/scheduler.py, daily 07:30 — found unregistered 2026-08-25, same FK-409 class'),
  ('downdetector_priority_tiered_collection',  'Downdetector Priority Polling',          'job', 120,  60,   'intelligence/scheduler.py, interval _PRIORITY_TIERED_INTERVAL_MINUTES (120min) — found unregistered 2026-08-25, 409 confirmed live in journalctl at the 2026-08-25 18:38 restart'),
  ('downdetector_threshold_recompute',          'Downdetector Threshold Recompute',       'job', 1440, 240,  'intelligence/scheduler.py, daily 05:00 — found unregistered 2026-08-25, same FK-409 class'),
  ('source_fidelity_audit',                     'Source Fidelity Audit',                  'job', 1440, 240,  'intelligence/scheduler.py, daily 06:45 — found unregistered 2026-08-25; same time slot as mission_registry_sync (registered, succeeds), this one was unregistered and 409ing'),
  ('evolved_captain_insight_generation',        'Captain Insight Generation',              'job', 240,  60,   'intelligence/scheduler.py, interval CAPTAIN_INSIGHT_INTERVAL_MINUTES (240min) — found unregistered 2026-08-25, 409 confirmed live in journalctl at the 2026-08-25 18:37 restart'),
  ('brief_qa_agent_nightly',                    'Brief QA Pre-screen',                    'job', 1440, 240,  'intelligence/scheduler.py, daily 02:00 — found unregistered 2026-08-25, same FK-409 class'),
  ('content_pipeline',                          'Content Signal-to-Draft Pipeline',       'job', 1440, 240,  'intelligence/proactive_cadences.py, daily 06:15 — found unregistered 2026-08-25, same FK-409 class'),
  ('pending_research_sweep',                    'Pending Research Sweep',                 'job', 5,    15,   'intelligence/proactive_cadences.py, interval 5min — found unregistered AND missing its heartbeat call entirely 2026-08-25 (job runs successfully hundreds of times/day per journalctl); both fixed same commit')
on conflict (domain_key) do nothing;
