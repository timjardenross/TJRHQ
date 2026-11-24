-- ============================================================================================================
-- provenance_migration_20261124.sql  --  STEP 1 of the provenance activation. *** NOT APPLIED. Needs owner approval. ***
--
-- Additive and backward compatible: 8 NULLABLE columns on intelligence_events, no defaults, no table rewrite (metadata-only
-- ALTER in Postgres 11+), 4 CHECK constraints added NOT VALID (not scanned, so no long lock; validated after the backfill).
-- Existing readers/writers are unaffected: PostgREST selects in the repo are explicit column lists, the 4 dependent views
-- (intelligence_ingestion_quality_daily, ori_sector_activity, ori_theme_frequency, ori_watch_items) name their columns, and the
-- table has no triggers. Code only touches the new columns when INTEL_PROVENANCE_COLUMNS=1 (default OFF).
--
-- Verified against the LIVE schema on 2026-11-24 (information_schema / pg_indexes / pg_constraint, SELECT only):
--   * intelligence_events: 61 columns, 45,427 rows, 135 MB, RLS on. NONE of the 8 new column names exist; none of the 4 constraint
--     names exist. No name or type conflict.
--   * Unique index on dedup_hash present: intelligence_events_dedup_hash_key (UNIQUE (dedup_hash)); 0 NULL hashes. The writer's
--     on_conflict=dedup_hash upsert depends on it and this migration does not touch it.
-- Idempotent: safe to re-run (IF NOT EXISTS / existence-guarded constraints).
-- Rollback: tools/intelligence/provenance_migration_20261124_ROLLBACK.sql
-- ============================================================================================================
BEGIN;
SET LOCAL lock_timeout = '5s';        -- fail fast rather than queue behind (and block) the live writer
SET LOCAL statement_timeout = '60s';

ALTER TABLE public.intelligence_events
    ADD COLUMN IF NOT EXISTS publisher_domain           text,
    ADD COLUMN IF NOT EXISTS publisher_family           text,
    ADD COLUMN IF NOT EXISTS published_at_basis         text,
    ADD COLUMN IF NOT EXISTS published_at_precision     text,
    ADD COLUMN IF NOT EXISTS published_at_confidence    text,
    ADD COLUMN IF NOT EXISTS published_at_label         text,
    ADD COLUMN IF NOT EXISTS event_window_start         timestamptz,
    ADD COLUMN IF NOT EXISTS event_window_end           timestamptz;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.intelligence_events'::regclass AND conname='intelligence_events_pub_basis_chk') THEN
    ALTER TABLE public.intelligence_events ADD CONSTRAINT intelligence_events_pub_basis_chk CHECK (published_at_basis IS NULL OR published_at_basis IN
        ('feed','feed_corrected_utc','aggregator_claimed','date_only','collected_fallback','unknown')) NOT VALID;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.intelligence_events'::regclass AND conname='intelligence_events_pub_precision_chk') THEN
    ALTER TABLE public.intelligence_events ADD CONSTRAINT intelligence_events_pub_precision_chk CHECK (published_at_precision IS NULL OR published_at_precision IN
        ('second','minute','day','unknown')) NOT VALID;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.intelligence_events'::regclass AND conname='intelligence_events_pub_confidence_chk') THEN
    ALTER TABLE public.intelligence_events ADD CONSTRAINT intelligence_events_pub_confidence_chk CHECK (published_at_confidence IS NULL OR published_at_confidence IN
        ('verified','claimed','feed','unknown')) NOT VALID;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.intelligence_events'::regclass AND conname='intelligence_events_pub_label_chk') THEN
    ALTER TABLE public.intelligence_events ADD CONSTRAINT intelligence_events_pub_label_chk CHECK (published_at_label IS NULL OR published_at_label IN
        ('publication','catalogue_addition','event')) NOT VALID;
  END IF;
END $$;

COMMENT ON COLUMN public.intelligence_events.publisher_domain IS 'Display/diagnosis only. Never proof of independence (family/aggregator based).';
COMMENT ON COLUMN public.intelligence_events.published_at_precision IS 'Exactness of published_at; separate from confidence. day + verified = explicit primary-source publication date.';
COMMENT ON COLUMN public.intelligence_events.published_at_confidence IS 'Trust that published_at is the PUBLICATION time. An event date must never be stored here (use event_window_*).';
COMMENT ON COLUMN public.intelligence_events.published_at_label IS 'Kind of date in published_at: publication | catalogue_addition | event. CISA KEV dateAdded is catalogue_addition: it dates the KEV entry, NOT the CVE disclosure, so it implies nothing about time since disclosure.';
COMMENT ON COLUMN public.intelligence_events.event_window_start IS 'When the EVENT is scheduled to start (e.g. maintenance window); not a publication time.';

COMMIT;

-- Post-apply check (SELECT): expect 8 rows, all is_nullable=YES, and 4 constraints with convalidated=false until the backfill is done.
--   SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_schema='public' AND table_name='intelligence_events'
--     AND column_name IN ('publisher_domain','publisher_family','published_at_basis','published_at_precision','published_at_confidence','published_at_label','event_window_start','event_window_end');
--   SELECT conname, convalidated FROM pg_constraint WHERE conrelid='public.intelligence_events'::regclass AND conname LIKE 'intelligence_events_pub_%_chk';
