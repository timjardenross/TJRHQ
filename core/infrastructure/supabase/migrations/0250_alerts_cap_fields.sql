-- 0250_alerts_cap_fields.sql
--
-- AUTHORED, NOT APPLIED. Do not apply from an agent session: the Captain
-- reviews and applies this, then sets EMERGENCY_ALERTS_CAP_FIELDS=1 on the
-- host that runs intelligence/emergency_alerts.py.
--
-- Keep the CAP (Common Alerting Protocol) urgency / certainty / severity /
-- event that some sources already provide, instead of discarding them at
-- ingest. Populated only where the source carries them: sa_cfs (CAP-AU <info>)
-- and vic_emergency warnings (embedded `cap` object); NULL for every other
-- source, never inferred.
--
-- Until this migration is applied the orchestrator strips these four keys from
-- every upsert (EMERGENCY_ALERTS_CAP_FIELDS unset or != "1"), because sending a
-- column PostgREST does not know about would fail the whole source's upsert.
-- Apply this migration BEFORE setting the flag.
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
