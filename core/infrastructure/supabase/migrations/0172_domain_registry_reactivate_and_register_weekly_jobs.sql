-- 0172_domain_registry_reactivate_and_register_weekly_jobs.sql
--
-- Continuation of 0171: the weekly/monthly cluster of the same "Agent
-- Status shows never-heartbeated" investigation, 2026-08-25.
--
-- Part 1 — reactivate 3 domains retired 2026-08-10 for having no live
-- writer: decision_review, knowledge_freshness, decision_outcome_reminder.
-- Their own retirement notes said "Re-activate if a real live writer is
-- built" — that happened 2026-08-23 when these jobs migrated from the
-- dead platform-runtime/proactive_scheduler.py (only reachable via the
-- disabled starfleet-slack-bot.service) to intelligence/proactive_cadences.py
-- (owned by intelligence-scheduler.service, confirmed live and running).
-- Ad-hoc triggered all 3 tonight to confirm the write path (job_decision_
-- review/job_knowledge_freshness/job_decision_outcome_reminder all
-- executed cleanly once a separate same-night code fix closed a
-- sys.path/ImportError gap in their shared heartbeat helper).
update domain_registry
set
  active = true,
  notes  = notes || ' -- REACTIVATED 2026-08-25: live writer confirmed (intelligence/proactive_cadences.py, owned by intelligence-scheduler.service, migrated from the dead Slack-bot scheduler 2026-08-23). Ad-hoc triggered tonight to verify the write path end-to-end.'
where domain_key in ('decision_review', 'knowledge_freshness', 'decision_outcome_reminder');

-- Part 2 — register the remaining weekly/monthly jobs that were never in
-- domain_registry at all (same FK-409 class as migration 0171, confirmed
-- via ad-hoc trigger tonight for weekly_review/forgotten_decisions before
-- this row existed).
insert into domain_registry (domain_key, display_name, category, expected_cadence_minutes, grace_period_minutes, notes) values
  ('weekly_review',            'Weekly Review',                    'job', 10080, 2880,  'intelligence/proactive_cadences.py, Fri 16:30 -- found unregistered 2026-08-25, same FK-409 class as migration 0171''s jobs'),
  ('forgotten_decisions',      'Forgotten Decisions Alert',         'job', 4320,  1440,  'intelligence/proactive_cadences.py, Mon+Thu 09:30 -- found unregistered 2026-08-25; also had a missing heartbeat call on its common "nothing to report" branch, fixed same commit'),
  ('monthly_lessons_digest',   'Monthly Lessons Digest',            'job', 43200, 10080, 'intelligence/proactive_cadences.py, 1st of month 08:00 -- found unregistered AND missing its heartbeat call entirely 2026-08-25 (ad-hoc test confirmed zero heartbeat calls in the function); both fixed same commit'),
  ('ko_monthly_brief',         'KO Monthly Brief',                  'job', 43200, 10080, 'intelligence/proactive_cadences.py, 1st of month 08:30 -- found unregistered AND missing its heartbeat call entirely 2026-08-25 (ad-hoc test confirmed zero heartbeat calls in the function); both fixed same commit'),
  ('attention_engine_drill',   'Attention Engine Weekly Drill',     'job', 10080, 2880,  'intelligence/scheduler.py, Mon 08:00 -- found unregistered 2026-08-25'),
  ('health_osint_weekly_fetch','Health OSINT Weekly Fetch',        'job', 10080, 2880,  'intelligence/scheduler.py, Sun 02:00 -- found unregistered 2026-08-25'),
  ('health_osint_auto_curation','Health OSINT Auto-Curation',      'job', 10080, 2880,  'intelligence/scheduler.py, Sun 02:00 (same run as health_osint_weekly_fetch) -- found unregistered 2026-08-25')
on conflict (domain_key) do nothing;
