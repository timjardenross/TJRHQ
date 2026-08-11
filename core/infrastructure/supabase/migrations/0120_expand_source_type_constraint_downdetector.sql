-- 0120_expand_source_type_constraint_downdetector.sql
--
-- 2026-08-10: Downdetector Australia adapter (crowdsourced outage
-- report-volume signal) needs its own source_type value -- genuinely
-- distinct fetch/parse mechanism from rss/api/scrape/manual/github_markdown
-- (see intelligence/ingestion/downdetector_adapter.py). Same class of
-- additive, non-breaking CHECK-constraint widen already used for this table
-- (expand_jurisdiction_constraint_source_registry,
-- 0036d_source_registry_category_expand,
-- add_cybersecurity_category_to_source_registry) -- existing rows/values
-- unaffected, only one new literal permitted.
--
-- Applied live via Supabase MCP (mcp__plugin_supabase_supabase__apply_migration,
-- name "expand_source_type_constraint_downdetector") as part of the
-- Downdetector adapter implementation -- this file is the repo-tracked
-- mirror of that change, matching this directory's established
-- migrations-as-source-of-truth convention.

ALTER TABLE intelligence_source_registry
  DROP CONSTRAINT intelligence_source_registry_source_type_check;

ALTER TABLE intelligence_source_registry
  ADD CONSTRAINT intelligence_source_registry_source_type_check
  CHECK (source_type = ANY (ARRAY[
    'rss'::text, 'api'::text, 'scrape'::text, 'manual'::text,
    'github_markdown'::text, 'downdetector'::text
  ]));
