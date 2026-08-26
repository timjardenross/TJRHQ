-- 0173_domain_registry_critical_flag.sql
--
-- Captain feedback 2026-08-26: the 🛰 PLATFORM HEALTH card in the morning
-- brief (intelligence/captains_brief.py, narrated by
-- core/platform/infra_narrative.py) is jargon-heavy and now redundant with
-- the Agent/Job dashboard (lcars-portal agent-status page, backed by
-- domain_heartbeats_latest) for ordinary job-level detail. Two items in
-- this morning's brief (health_mission_correlation,
-- downdetector_priority_tiered_collection) were the exact FK-409
-- registration-gap noise fixed yesterday in migration 0171 — real gaps,
-- but not P1: neither blocks a Captain-facing deliverable, and both
-- self-clear on their next successful run now that the FK is fixed.
--
-- Rather than re-triage every future scheduler job as it's added (the
-- 0170/0171/0172 treadmill), this adds a `critical` flag so the brief's
-- narrative can filter to P1-only while the Agent/Job dashboard (which
-- already reads domain_heartbeats_latest directly, unaffected by this
-- flag) keeps full job-level visibility for anyone who wants it.
--
-- Critical = a domain whose degradation directly breaks something the
-- Captain sees or relies on today, not just an internal enrichment/
-- analytics job running late. Deliberately narrow; everything else
-- defaults to non-critical and can be promoted later if it proves to
-- matter.

alter table domain_registry
  add column if not exists critical boolean not null default false;

comment on column domain_registry.critical is
  'P1 flag for the morning-brief Platform Health narrative (core/platform/infra_narrative.py): true means this domain going stale/never-succeeded directly breaks a Captain-facing deliverable, not just an internal job running late. Does not affect the Agent/Job dashboard, which shows every domain regardless of this flag.';

update domain_registry set critical = true where domain_key in (
  'command_centre_backend',   -- everything else depends on this being up
  'core_events',               -- platform event bus, continuous infra signal
  'verification_engine',       -- self: if this is blind, nothing else here can be trusted
  'captains_daily_briefs',     -- direct Captain-facing deliverable
  'intelligence_collection'    -- the data pipeline the rest of intelligence depends on
);
