-- PROPOSED migration — NOT APPLIED. Lives in docs/proposals/ on purpose so no tooling can pick it up.
-- Number 0261 follows the latest filed migration (0260) at the time of writing; re-check it is
-- still free before filing (AGENTS.md check-first rule).
--
-- Purpose: a small, durable, append-only record that (a) gives database-size growth a measured
-- history so a forecast can be shown, and (b) preserves the evidence cited by each weekly report
-- so retention can be introduced later without losing traceability.
-- Contains NO personal health data: sizes, counts, and public-source event metadata only.

CREATE TABLE IF NOT EXISTS public.weekly_evidence_snapshot (
  id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  week_start       date        NOT NULL,                     -- local Monday of the reported week
  method_version   text        NOT NULL,                     -- e.g. 'wk-evidence/0.1.0-prototype'
  created_at       timestamptz NOT NULL DEFAULT now(),
  db_size_mb       numeric(10,2),
  table_sizes_mb   jsonb       NOT NULL DEFAULT '{}'::jsonb, -- {"intelligence_events": 96.8, ...}
  universe         jsonb       NOT NULL DEFAULT '{}'::jsonb, -- exact counts: usable, duplicates, au_events...
  cited_evidence   jsonb       NOT NULL DEFAULT '[]'::jsonb, -- [{event_id,title,source,url,collected_at}]
  report_sha256    text,                                      -- hash of the rendered shadow/real brief
  notes            text,
  CONSTRAINT weekly_evidence_snapshot_uq UNIQUE (week_start, method_version),
  CONSTRAINT weekly_evidence_snapshot_cited_is_array CHECK (jsonb_typeof(cited_evidence) = 'array'),
  CONSTRAINT weekly_evidence_snapshot_size_nonneg CHECK (db_size_mb IS NULL OR db_size_mb >= 0)
);

COMMENT ON TABLE public.weekly_evidence_snapshot IS
  'Append-only weekly snapshot: DB size history for gated growth forecasts, and the evidence cited by each weekly brief so retention cannot erase report traceability. No personal health data.';

CREATE INDEX IF NOT EXISTS idx_weekly_evidence_snapshot_week ON public.weekly_evidence_snapshot (week_start DESC);

-- Deny-all by default: no policies, so only the service role (which bypasses RLS) can read or write.
ALTER TABLE public.weekly_evidence_snapshot ENABLE ROW LEVEL SECURITY;

-- Deliberately NOT included (each needs its own approval): a pg_cron job to write rows, any
-- retention/DELETE job, any change to existing tables.
