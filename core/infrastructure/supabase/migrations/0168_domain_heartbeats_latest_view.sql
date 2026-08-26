-- domain_heartbeats_latest: one row per domain_key, most recent heartbeat.
--
-- The agent-status API (lcars-portal/src/app/api/agent-status/route.ts) was
-- fetching the 500 most recent rows across ALL domains and deduplicating in JS.
-- With 35k+ rows and high-frequency domains (core_events, verification_engine)
-- writing every few minutes, infrequent jobs (health_osint_weekly_fetch,
-- brief_qa_agent_nightly) were buried beyond the 500-row limit and showed
-- as "Unknown" even when they had valid heartbeats from prior days.
-- 2026-08-23 fix: efficient DISTINCT ON view + API updated to query it directly.

CREATE OR REPLACE VIEW public.domain_heartbeats_latest AS
SELECT DISTINCT ON (domain_key)
  heartbeat_id,
  domain_key,
  checked_at,
  status,
  detail,
  error_message,
  latency_ms
FROM public.domain_heartbeats
ORDER BY domain_key, checked_at DESC;

-- Grant read access to authenticated and anon roles (matches domain_heartbeats RLS).
GRANT SELECT ON public.domain_heartbeats_latest TO authenticated;
GRANT SELECT ON public.domain_heartbeats_latest TO anon;

-- Rollback:
-- DROP VIEW IF EXISTS public.domain_heartbeats_latest;
