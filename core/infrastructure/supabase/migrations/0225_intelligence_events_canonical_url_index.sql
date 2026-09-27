-- Cross-run dedup looks events up by canonical_url on every collection run
-- (intelligence_store.filter_unpersisted_events, batched as `in.(...)`
-- since the Supabase usage review 2026-09-27). dedup_hash is indexed
-- (unique + idx_ie_dedup); canonical_url was not, so each lookup was a
-- sequential scan of intelligence_events (~26k rows). Partial: most
-- lookups are for non-null URLs and null rows are never matched.
create index if not exists idx_ie_canonical_url
  on intelligence_events (canonical_url)
  where canonical_url is not null;
