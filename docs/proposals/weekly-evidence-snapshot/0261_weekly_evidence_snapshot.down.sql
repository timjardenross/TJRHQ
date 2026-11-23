-- ROLLBACK for 0261_weekly_evidence_snapshot.up.sql — PROPOSED, NOT APPLIED.
-- Safe because the table is new and nothing else references it. Take the optional export first.
--   COPY (SELECT * FROM public.weekly_evidence_snapshot) TO STDOUT WITH CSV HEADER;   -- run via a client, not server files
DROP INDEX IF EXISTS public.idx_weekly_evidence_snapshot_week;
DROP TABLE IF EXISTS public.weekly_evidence_snapshot;
