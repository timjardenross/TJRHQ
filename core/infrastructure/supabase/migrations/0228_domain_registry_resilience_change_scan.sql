-- 0228_domain_registry_resilience_change_scan.sql
--
-- Registers the Operational Resilience Advisor's daily regulatory change scan
-- (intelligence/scheduler.py _resilience_change_scan_job, 06:50 AEST) so its
-- record_heartbeat() writes land. domain_heartbeats.domain_key is a foreign key
-- against domain_registry (migration 0071); an unregistered job's heartbeats
-- silently 409 — the exact failure class migration 0171 cleaned up.

insert into domain_registry (domain_key, display_name, category, expected_cadence_minutes, grace_period_minutes, notes) values
  ('resilience_change_scan', 'Resilience Change Scan', 'job', 1440, 240,
   'intelligence/scheduler.py, daily 06:50 — flags regulatory-corpus frameworks (knowledge/regulatory-corpus) that new APRA/BIS publications may affect; see platform-runtime/lib/resilience/change_flags.py')
on conflict (domain_key) do nothing;
