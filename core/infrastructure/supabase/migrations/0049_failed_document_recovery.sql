-- USS-TJR-MSN-0206J-4 — Failed Document Recovery.
--
-- `failed` has been a dead end since processing_documents was introduced
-- (0042/MSN-0205C): no retry mechanism exists at all. This was flagged as
-- a known gap in MSN-0206A's closure report ("No auto-retry mechanism
-- exists for failed documents... reprocessing required a manually
-- Captain-approved SQL update"). This migration adds the three new states
-- a bounded, manual retry mechanism needs — the mechanics (retry_count
-- cap, artifact reset before re-processing) live entirely in
-- vm-processing/worker.py; this migration is schema-only.
--
-- Three new statuses added to the existing CHECK constraint:
--   - retry_pending: set by `worker.py retry --id ID` on a `failed`
--     document that is still under `max_retries` — process_batch() picks
--     these up like any other non-terminal status.
--   - retrying: the in-flight state while stale artifacts from the
--     previous failed attempt are cleared and the document is re-run from
--     extraction. A retry that fails again returns to plain `failed`
--     (unchanged _mark_failed path) — retriable again if still under cap.
--   - permanently_failed: set instead of `retry_pending` when
--     `worker.py retry` is requested but `retry_count` has already reached
--     `max_retries` — a new terminal state. `worker.py override --id ID`
--     (MSN-0206J-1's existing manual escape hatch) remains the only way
--     to force a permanently_failed document back to `received` beyond
--     the cap; no separate override mechanism is introduced here.
--
-- Two new columns:
--   - retry_count: how many times `worker.py retry` has been invoked for
--     this document. Defaults to 0 — the existing default backfills every
--     current row automatically, no explicit backfill statement needed.
--   - last_retry_at: timestamp of the most recent retry request. Nullable
--     — null until the first retry.
--
-- No backfill needed: no existing row can already have one of the three
-- new statuses (they didn't exist until this migration), and the column
-- defaults handle retry_count/last_retry_at for all existing rows.
--
-- Column/constraint-only change to an existing table (ADR-0020: reuse
-- before create — same table introduced under 0042's authorised
-- exception, extended by 0045/0047/0048; no new table needed here).

alter table processing_documents
  drop constraint if exists processing_documents_status_check;

alter table processing_documents
  add constraint processing_documents_status_check check (
    status in (
      'received',
      'extracted',
      'ocr_required',
      'ocr_complete',
      'classified',
      'summarised',
      'embedded',
      'failed',
      'awaiting_review',
      'excluded',
      'retry_pending',
      'retrying',
      'permanently_failed'
    )
  );

alter table processing_documents
  add column if not exists retry_count integer not null default 0;

alter table processing_documents
  add column if not exists last_retry_at timestamptz;

create index if not exists idx_processing_documents_retry_count
  on processing_documents (retry_count);

-- Rollback:
--
-- drop index if exists idx_processing_documents_retry_count;
-- alter table processing_documents drop column if exists last_retry_at;
-- alter table processing_documents drop column if exists retry_count;
-- alter table processing_documents drop constraint if exists processing_documents_status_check;
-- alter table processing_documents add constraint processing_documents_status_check check (
--   status in (
--     'received', 'extracted', 'ocr_required', 'ocr_complete', 'classified',
--     'summarised', 'embedded', 'failed', 'awaiting_review', 'excluded'
--   )
-- );
--
-- Note: rollback will fail if any row has status in
-- ('retry_pending', 'retrying', 'permanently_failed') at the time it's run
-- (the narrowed CHECK constraint would reject those rows) — reset any such
-- rows to another status first, e.g.
-- update processing_documents set status = 'failed'
-- where status in ('retry_pending', 'retrying', 'permanently_failed');
