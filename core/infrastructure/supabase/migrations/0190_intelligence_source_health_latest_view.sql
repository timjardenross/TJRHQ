-- intelligence_source_health_latest: one row per source_id, most recent check.
--
-- Same bug class 0168 fixed for domain_heartbeats_latest, recurring here:
-- /api/agent-status-workbench/overview and /sources were fetching the 1500
-- most recent rows across ALL sources and deduplicating in JS. With 19.8k+
-- rows and high-frequency sources dominating recency, only ~112 of 136
-- distinct sources with any health history land in that window — a source
-- checked less often can fall out of it entirely, at which point it isn't
-- shown as "unknown" (the honest fallback both routes otherwise use for
-- true no-data cases) but simply vanishes from the Needs Attention count
-- with no signal that anything was dropped. 2026-09-06 fix: efficient
-- DISTINCT ON view + both routes updated to query it directly, matching
-- 0168's approach exactly.

CREATE OR REPLACE VIEW public.intelligence_source_health_latest AS
SELECT DISTINCT ON (source_id)
  source_id,
  status,
  error_message,
  checked_at
FROM public.intelligence_source_health
ORDER BY source_id, checked_at DESC;

-- Grant read access to authenticated and anon roles (matches intelligence_source_health RLS).
GRANT SELECT ON public.intelligence_source_health_latest TO authenticated;
GRANT SELECT ON public.intelligence_source_health_latest TO anon;

-- Rollback:
-- DROP VIEW IF EXISTS public.intelligence_source_health_latest;
