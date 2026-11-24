-- ============================================================================================================
-- *** DRAFT - NOT APPLIED. Backfill for provenance v1. Run only AFTER the migration, and only with Captain approval. ***
-- Conservative: existing rows get the least-trusting honest label. Nothing is ever promoted to 'verified'.
-- Back up first (AGENTS.md: back up rows before any data fix), e.g.
--   CREATE TABLE intelligence_events_provenance_bak_YYYYMMDD AS
--   SELECT event_id, published_at FROM intelligence_events WHERE published_at_basis IS NULL;
-- Run in batches (add LIMIT via a CTE on event_id) to keep locks short.
-- ============================================================================================================

-- 1. Rows with no published time were timed by collection: say so.
UPDATE intelligence_events
   SET published_at_basis = 'collected_fallback', published_at_precision = 'unknown', published_at_confidence = 'unknown'
 WHERE published_at_basis IS NULL AND published_at IS NULL;

-- 2. Google News rows: pubDate is the aggregator's claim. (Publisher domain/name cannot be recovered from stored rows.)
UPDATE intelligence_events e
   SET published_at_basis = 'aggregator_claimed', published_at_precision = 'second', published_at_confidence = 'claimed'
  FROM intelligence_source_registry r
 WHERE e.source_id = r.source_id AND e.published_at_basis IS NULL AND e.published_at IS NOT NULL
   AND (e.canonical_url ILIKE '%news.google.com%' OR r.source_name ILIKE 'Google News%');

-- 3. Everything else with a published time came from the source's own feed/page: feed basis, second precision (unverified clock).
UPDATE intelligence_events
   SET published_at_basis = 'feed', published_at_precision = 'unknown', published_at_confidence = 'feed'
 WHERE published_at_basis IS NULL AND published_at IS NOT NULL;

-- 4. Validate the NOT VALID constraints once backfilled.
-- ALTER TABLE intelligence_events VALIDATE CONSTRAINT intelligence_events_pub_basis_chk;
-- ALTER TABLE intelligence_events VALIDATE CONSTRAINT intelligence_events_pub_precision_chk;
-- ALTER TABLE intelligence_events VALIDATE CONSTRAINT intelligence_events_pub_confidence_chk;
