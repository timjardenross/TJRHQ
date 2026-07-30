-- Additional job-level domains discovered while wiring platform-runtime/
-- proactive_scheduler.py's existing _shakedown_log() into record_heartbeat().
-- Each job_id used by _shakedown_log becomes its own domain_key here so the
-- FK on domain_heartbeats.domain_key resolves for every call site.
insert into domain_registry (domain_key, display_name, category, expected_cadence_minutes, grace_period_minutes, notes) values
  ('morning_brief', 'Morning Brief Push', 'job', 1440, 240, 'platform-runtime/proactive_scheduler.py, daily at BRIEF_TIME (default 07:30)'),
  ('appointment_prep', 'Appointment Preparation Check', 'job', 1440, 240, 'platform-runtime/proactive_scheduler.py, daily 08:45'),
  ('shakedown_digest', 'Shakedown Digest', 'job', 1440, 240, 'platform-runtime/proactive_scheduler.py, daily 20:00'),
  ('decision_review', 'Pending Decision Review', 'job', 10080, 2880, 'platform-runtime/proactive_scheduler.py, Friday 16:00'),
  ('knowledge_freshness', 'Knowledge Freshness Check', 'job', 10080, 2880, 'platform-runtime/proactive_scheduler.py, weekly'),
  ('decision_outcome_reminder', 'Decision Outcome Reminder', 'job', 10080, 2880, 'platform-runtime/proactive_scheduler.py, weekly'),
  ('pain_escalation', 'Pain Escalation Detection', 'job', 10080, 10080, 'platform-runtime/proactive_scheduler.py - RETIRED D-3C-04, not currently scheduled; registered for completeness if revived'),
  ('stale_missions_job', 'Stale Mission Alert Job', 'job', 10080, 10080, 'platform-runtime/proactive_scheduler.py - RETIRED D-3C-04, not currently scheduled; distinct from the "missions" data-freshness domain')
on conflict (domain_key) do nothing;
