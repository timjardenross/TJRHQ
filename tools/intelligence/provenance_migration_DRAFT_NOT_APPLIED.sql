-- ============================================================================================================
-- *** DRAFT - NOT APPLIED. Do not run against production without Captain approval. ***
-- Provenance v1: additive, nullable columns on intelligence_events. No defaults, no rewrite of existing rows.
-- Code in this repo behaves identically whether or not these columns exist (see intelligence/provenance.py:
-- columns are only written/read when INTEL_PROVENANCE_COLUMNS=1). Apply this FIRST, then flip the flag.
-- ============================================================================================================
BEGIN;

ALTER TABLE intelligence_events
    ADD COLUMN IF NOT EXISTS publisher_domain           text,
    ADD COLUMN IF NOT EXISTS publisher_family           text,
    ADD COLUMN IF NOT EXISTS published_at_basis         text,
    ADD COLUMN IF NOT EXISTS published_at_precision     text,
    ADD COLUMN IF NOT EXISTS published_at_confidence    text,
    ADD COLUMN IF NOT EXISTS event_window_start         timestamptz,
    ADD COLUMN IF NOT EXISTS event_window_end           timestamptz;

ALTER TABLE intelligence_events
    ADD CONSTRAINT intelligence_events_pub_basis_chk CHECK (published_at_basis IS NULL OR published_at_basis IN
        ('feed','feed_corrected_utc','aggregator_claimed','date_only','collected_fallback','unknown')) NOT VALID,
    ADD CONSTRAINT intelligence_events_pub_precision_chk CHECK (published_at_precision IS NULL OR published_at_precision IN
        ('second','minute','day','unknown')) NOT VALID,
    ADD CONSTRAINT intelligence_events_pub_confidence_chk CHECK (published_at_confidence IS NULL OR published_at_confidence IN
        ('verified','claimed','feed','unknown')) NOT VALID;

COMMENT ON COLUMN intelligence_events.publisher_domain IS 'Display/diagnosis only. Never proof of independence (family/aggregator based).';
COMMENT ON COLUMN intelligence_events.event_window_start IS 'When the EVENT is scheduled to start (e.g. maintenance window); not a publication time.';

COMMIT;
-- Rollback (also NOT APPLIED): ALTER TABLE intelligence_events DROP COLUMN publisher_domain, ... (constraints drop with the columns).
