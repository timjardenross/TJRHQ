-- ============================================================================
-- Migration 0201 -- intelligence_source_registry: extend source_type CHECK
-- constraint to match real, wired adapter types (found during USS-TJR-MSN-0368
-- watchlist activation)
-- ============================================================================
-- Purpose:
--   Running tools/intelligence/seed_source_registry.py for real against this
--   project failed outright -- ALL 165 sources, not just new ones -- with a
--   23514 check-constraint violation. The live constraint only allowed:
--     'rss', 'api', 'scrape', 'manual', 'github_markdown', 'downdetector'
--   Same pattern as issue #187 (missions_status_check vs _VALID_TRANSITIONS):
--   code assumed a value the schema never actually had. Confirmed real
--   before deciding to extend rather than narrow the code, exactly like
--   #187's resolution:
--     - 'browser': intelligence/ingestion/browser_adapter.py exists, is
--       registered in collection_engine.py's _ADAPTER_MAP, and 3 existing
--       seed_source_registry.py sources (incl. National Emergency
--       Management Agency) already use it -- meaning those sources have
--       never successfully seeded since being added, until this migration.
--     - 'changedetection' / 'uptime_kuma': USS-TJR-MSN-0366 Stream 6's
--       watchlist execution engine (deploy/docker-compose.watchlist.yml),
--       activated for real under USS-TJR-MSN-0368 -- both registered in
--       the same _ADAPTER_MAP, both backing real, live, ticking containers
--       (changedetection.io watching 3 real AU regulator pages, Uptime
--       Kuma probing 6 real vendor status pages, both confirmed live
--       2026-09-12).
--   All 5 are real, wired, non-experimental collection mechanisms this
--   codebase already ships code for -- none are aspirational.
--
-- Apply via Supabase SQL Editor or psql.
-- ============================================================================

ALTER TABLE intelligence_source_registry DROP CONSTRAINT IF EXISTS intelligence_source_registry_source_type_check;

ALTER TABLE intelligence_source_registry
  ADD CONSTRAINT intelligence_source_registry_source_type_check
  CHECK (source_type IN (
    'rss',
    'api',
    'scrape',
    'manual',
    'github_markdown',
    'downdetector',
    'browser',
    'changedetection',
    'uptime_kuma'
  ));
