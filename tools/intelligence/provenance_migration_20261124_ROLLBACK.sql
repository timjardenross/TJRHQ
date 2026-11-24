-- provenance_migration_20261124_ROLLBACK.sql -- NOT APPLIED. Reverses provenance_migration_20261124.sql.
-- Order: (1) set INTEL_PROVENANCE_COLUMNS=0 (or unset) on the writer and the brief reader and restart them, so no code touches the columns;
--        (2) run this. DESTRUCTIVE: drops the 8 columns and any provenance values in them. If the backfill ran, the backup table
--        intelligence_events_provenance_bak_20261124 lists the rows it touched (it holds only event_id + rule; values are re-derivable by rerunning the backfill).
-- Dropping the columns also drops the 4 CHECK constraints that reference them.
BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE public.intelligence_events
    DROP COLUMN IF EXISTS publisher_domain,
    DROP COLUMN IF EXISTS publisher_family,
    DROP COLUMN IF EXISTS published_at_basis,
    DROP COLUMN IF EXISTS published_at_precision,
    DROP COLUMN IF EXISTS published_at_confidence,
    DROP COLUMN IF EXISTS published_at_label,
    DROP COLUMN IF EXISTS event_window_start,
    DROP COLUMN IF EXISTS event_window_end;
COMMIT;
-- Softer rollback that keeps the columns (backfill only): see the REVERSE block at the bottom of provenance_backfill_20261124.sql.
