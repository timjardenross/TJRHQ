-- ADR-024 second-pass audit: two job/data domains have real heartbeat call
-- sites but no domain_registry row, so their record_heartbeat() calls
-- silently fail the FK on domain_heartbeats.domain_key (best-effort,
-- swallowed — no error surfaced, but the heartbeat is a no-op).
--
-- wellness-coaching: RESIL-HUMAN's escalation/push signal
-- (telegram-bots/recovery_officer/engagement_dispatcher.py's
-- publish_event(domain="wellness-coaching", ...) and
-- platform-runtime/human_systems_scheduler.py's _publish_core_event()) is
-- mirrored into core_events but was never tracked by the domain_heartbeats
-- self-health system, unlike every other RESIL-HUMAN surface
-- (health_daily_logs, human_systems, recovery_pulses already registered
-- in migration 0071).
--
-- mission_registry_sync: new job added in the same audit pass
-- (platform-runtime/proactive_scheduler.py, daily 06:45) — follows the
-- same job-level-domain pattern as migration 0072.
insert into domain_registry (domain_key, display_name, category, expected_cadence_minutes, grace_period_minutes, notes) values
  ('wellness-coaching', 'Wellness Coaching Signal', 'data', 1440, 480, 'RESIL-HUMAN escalation/push mirror into core_events — telegram-bots/recovery_officer/engagement_dispatcher.py and platform-runtime/human_systems_scheduler.py; Captain-paced, generous grace'),
  ('mission_registry_sync', 'Mission Registry Sync', 'job', 1440, 240, 'platform-runtime/proactive_scheduler.py, daily 06:45 (ADR-024 fix #3)')
on conflict (domain_key) do nothing;
