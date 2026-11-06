-- 0253_emergency_alert_domains_critical.sql
--
-- APPLIED 2026-11-06 to the USSTJR project via the Supabase tool (tracker name
-- `emergency_alert_domains_critical`), on the Captain's go-ahead.
--
-- A stale or failing emergency-alert collector directly breaks something the Captain relies on, so the
-- morning-brief Platform Health narrative (domain_registry.critical, migration 0173) must list it.
-- All 17 emergency_alert_* domains (16 collectors + the hourly summary) are marked critical.
--
-- NOTE: `critical` only drives that morning-brief card (core/platform/infra_narrative.py). It does NOT
-- page in real time. A real-time page (a feed-down email) is a separate change, not made here.

update domain_registry set critical = true where domain_key like 'emergency_alert\_%' escape '\';
