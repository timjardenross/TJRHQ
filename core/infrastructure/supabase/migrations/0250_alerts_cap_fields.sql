-- 0250_alerts_cap_fields.sql
--
-- APPLIED 2026-11-06 to the USSTJR Supabase project (Captain-approved), via the
-- Supabase tool, so the migration tracker lists it as `alerts_cap_fields`, not
-- under this file name. The SQL below is exactly what ran.
--
-- Keep the CAP (Common Alerting Protocol) urgency / certainty / severity /
-- event that some sources already provide, instead of discarding them at
-- ingest. Populated only where the source carries them: sa_cfs (CAP-AU <info>)
-- and vic_emergency warnings (embedded `cap` object); NULL for every other
-- source, never inferred.
--
-- The orchestrator stores these four keys by default now that the columns exist.
-- Setting EMERGENCY_ALERTS_CAP_FIELDS to 0/false/off/no strips them from every
-- upsert again, for a database WITHOUT these columns (sending a column PostgREST
-- does not know about fails the whole source's upsert). When the migration was
-- first authored the default was the other way round (off until the flag was 1).
--
-- Additive, nullable, no backfill, no constraint (values are the source's own
-- free vocabulary, e.g. Expected / Likely / Unknown), no index.

alter table alerts add column if not exists cap_urgency   text;
alter table alerts add column if not exists cap_certainty text;
alter table alerts add column if not exists cap_severity  text;
alter table alerts add column if not exists cap_event     text;

comment on column alerts.cap_urgency   is 'CAP <urgency> as given by the source (sa_cfs, vic_emergency warnings only; NULL elsewhere). Written only when EMERGENCY_ALERTS_CAP_FIELDS=1.';
comment on column alerts.cap_certainty is 'CAP <certainty> as given by the source (sa_cfs, vic_emergency warnings only; NULL elsewhere).';
comment on column alerts.cap_severity  is 'CAP <severity> as given by the source (sa_cfs, vic_emergency warnings only; NULL elsewhere). Often literally ''Unknown'' on SA CFS. Not the same thing as alerts.severity (the AWS tier).';
comment on column alerts.cap_event     is 'CAP <event> as given by the source (sa_cfs, vic_emergency warnings only; NULL elsewhere).';
