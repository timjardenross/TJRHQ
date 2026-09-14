-- 0204_captured_items_duplicate_detection.sql
--
-- Capture Workbench — cross-item semantic duplicate detection, see
-- core/capture/dedup.py.
--
-- captured_items_source_message_id_uniq (migration 0130) already catches
-- exact re-delivery of the same message from the same channel. Never
-- addressed until now: the same idea/link/note captured twice through
-- DIFFERENT channels — which enrichment_worker.py's hybrid auto-route
-- (MSN-0200-P2B) and Capture Promotion Bridge (MSN-0336) could otherwise
-- act on twice (a doubled captains_log_entries append, or two separate
-- intelligence_notes triage rows for one idea).
--
-- Additive only — no existing column, constraint, or row is touched.

alter table public.captured_items
  add column if not exists duplicate_of_id uuid references public.captured_items (id),
  add column if not exists duplicate_similarity numeric(4,3),
  add column if not exists duplicate_checked_at timestamptz;

comment on column public.captured_items.duplicate_of_id is
  'Set by core/capture/dedup.py when this item was found to be a semantic '
  'near-duplicate of another recent captured_items row (SemHash embedding '
  'similarity). Null means either no duplicate was found or dedup has not '
  'run yet for this row. A flagged duplicate is NEVER auto-dismissed — '
  'enrichment_worker.py skips classification/auto-route/promotion for it '
  'and leaves it visible in the inbox for a human to decide.';
comment on column public.captured_items.duplicate_similarity is
  'SemHash similarity score (0-1) against duplicate_of_id, at the '
  'threshold core/capture/dedup.DEFAULT_THRESHOLD was run with.';
comment on column public.captured_items.duplicate_checked_at is
  'When the duplicate check last ran for this row. Null until the first '
  'enrichment_worker.py pass touches it.';

create index if not exists captured_items_duplicate_of_id_idx
  on public.captured_items (duplicate_of_id) where duplicate_of_id is not null;
