-- Decommissioning-discipline drift check follow-up (2026-08-29): missions,
-- health_daily_logs, captains_log flagged stale (missions since 08-22,
-- health_daily_logs since 08-11, captains_log since 08-09). Confirmed with
-- Captain: these are no longer part of the workbenches and not intended to
-- be revived - not a pipeline bug, a genuine retirement. Same active=false
-- soft-delete pattern as migration 0112 (governance_records) and 0181
-- (recovery_pulses) - keeps the rows/history, drops them from
-- domain_heartbeat_latest / run_verification_pass() degraded-domain
-- reporting so they stop generating a false "degraded" signal.
update domain_registry
set
  active = false,
  notes  = notes || ' -- RETIRED 2026-08-29: no longer part of the workbenches, Captain confirmed not intended to be revived.'
where domain_key in ('missions', 'health_daily_logs', 'captains_log');
