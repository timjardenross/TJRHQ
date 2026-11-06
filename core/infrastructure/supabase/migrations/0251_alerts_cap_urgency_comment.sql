-- 0251_alerts_cap_urgency_comment.sql
--
-- APPLIED 2026-11-06 to the USSTJR Supabase project (Captain-approved), via the
-- Supabase tool, so the migration tracker lists it as `alerts_cap_urgency_comment`.
--
-- Metadata only, no behaviour change. 0250 left the cap_urgency column comment saying
-- "Written only when EMERGENCY_ALERTS_CAP_FIELDS=1". Since the orchestrator now stores
-- CAP fields by default (EMERGENCY_ALERTS_CAP_FIELDS=0/false/off/no turns it off), that
-- sentence was wrong. The other three cap_* comments never mentioned the flag.

comment on column alerts.cap_urgency is 'CAP <urgency> as given by the source (sa_cfs, vic_emergency warnings only; NULL elsewhere). Stored by default; set EMERGENCY_ALERTS_CAP_FIELDS=0 to stop writing it (only for a database without this column).';
