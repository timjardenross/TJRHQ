-- USS-TJR-MSN-0206B — Content Eligibility Engine.
--
-- Adds a new `excluded` terminal status to processing_documents so
-- recreational content (ebooks, novels, self-help/puzzle books) and
-- junk/placeholder files never consume a Captain's review-queue slot or an
-- OCR/classify/summarise/embed cycle. Companion code change:
-- vm-processing/eligibility.py + worker.py wiring — see
-- Missions/MSN-0206B-Content-Eligibility-Engine.md.
--
-- `exclusion_reason` is one of the three reason codes from the mission
-- spec: recreational_content, unsupported_media, temporary_document.
-- Nullable — only set when status = 'excluded'.
--
-- Column-only change to an existing table (ADR-0020: reuse before create —
-- same table introduced under 0042's authorised exception, no new table
-- needed for this phase).

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
      'excluded'
    )
  );

alter table processing_documents
  add column if not exists exclusion_reason text check (
    exclusion_reason is null or exclusion_reason in (
      'recreational_content', 'unsupported_media', 'temporary_document'
    )
  );

-- Rollback:
--
-- alter table processing_documents drop constraint if exists processing_documents_status_check;
-- alter table processing_documents add constraint processing_documents_status_check check (
--   status in (
--     'received', 'extracted', 'ocr_required', 'ocr_complete', 'classified',
--     'summarised', 'embedded', 'failed', 'awaiting_review'
--   )
-- );
-- alter table processing_documents drop column if exists exclusion_reason;
--
-- Note: rollback will fail if any row has status = 'excluded' at the time
-- it's run (the narrowed CHECK constraint would reject those rows) — reset
-- any excluded rows to another status first, e.g.
-- update processing_documents set status = 'received', exclusion_reason = null
-- where status = 'excluded';
