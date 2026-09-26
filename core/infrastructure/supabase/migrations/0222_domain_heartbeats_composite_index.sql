-- 0222_domain_heartbeats_composite_index.sql
--
-- Root-causes the intermittent "HQ Status is unavailable" / overview_read_
-- failed (Postgres error 57014, statement timeout) reported live on
-- production, first seen 2026-09-06. Confirmed via EXPLAIN (ANALYZE,
-- BUFFERS) on domain_heartbeat_latest (migration 0071's view, which
-- api/agent-status-workbench/overview and the underlying
-- domain_heartbeats_latest read every poll):
--
--   Index Scan using idx_domain_heartbeats_checked_at on domain_heartbeats
--     Filter: (domain_key = r.domain_key)
--     Rows Removed by Filter: 10710   <- per domain, per lateral, x59 domains
--   Buffers: shared hit=704869        <- total for one view call
--   Execution Time: 1947.853 ms
--
-- The view's two per-domain lateral subqueries (latest attempt, latest
-- 'ok'/'skipped' attempt) both filter on domain_key then order by
-- checked_at desc limit 1. Only a checked_at-only index existed
-- (migration 0071), so the planner walks the *global* checked_at-ordered
-- index and discards every row belonging to a different domain_key before
-- finding a match -- cost scales with total table rows (103,770 at time of
-- writing), not with one domain's own row count, and gets worse as
-- higher-frequency domains (core_events every 30min, command_centre_
-- backend every 5min) grow relative to low-frequency ones. This is exactly
-- the shape that eventually blows the 60s poll interval's request headroom
-- under Supabase's statement_timeout.
--
-- Fix: a composite index with domain_key leading lets the planner do a
-- direct index range scan within just that domain's rows, already in
-- checked_at desc order -- O(1) per lateral instead of O(total rows).
-- Plain (non-CONCURRENTLY) CREATE INDEX: table is 103,770 rows / 24MB at
-- time of writing, so the build completes in well under a second -- the
-- brief write lock this implies is negligible against that, and
-- CONCURRENTLY cannot run inside the transaction this migration tool wraps
-- its statements in.

create index if not exists idx_domain_heartbeats_domain_key_checked_at
  on domain_heartbeats (domain_key, checked_at desc);

comment on index idx_domain_heartbeats_domain_key_checked_at is
  'Composite, domain_key-leading index for domain_heartbeat_latest''s (migration 0071) per-domain lateral subqueries -- the pre-existing single-column idx_domain_heartbeats_checked_at forced a full-table scan-and-filter per domain. Fixes the intermittent statement-timeout behind "HQ Status is unavailable" (overview_read_failed), confirmed via EXPLAIN ANALYZE, 2026-09-20.';
