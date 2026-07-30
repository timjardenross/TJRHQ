-- USS-TJR-MSN-0205D: LCARS Knowledge Library and Memory Approval Queue.
--
-- Additive columns on the existing processing_documents table (0042,
-- MSN-0205C) — same ADR-0020 exception already documented there, this is
-- a narrower follow-on (columns, not a new table) needed to record the
-- Captain's approval-queue decision separately from the processing
-- pipeline's own `status`. `status` stays exactly the 9-state pipeline
-- lifecycle defined in 0042 and is never overloaded with review outcomes
-- — a document can sit at status='awaiting_review' forever with
-- review_decision progressing from null to a terminal decision.
--
-- Also widens knowledge_documents.document_type (0001) to accept
-- 'Personal Archive' — the only new value, additive only — so approved
-- personal documents can be written into the existing Command Memory /
-- Working Memory pathway without inventing a parallel memory table.

alter table processing_documents
  add column if not exists review_decision text check (
    review_decision is null or review_decision in (
      'approved_metadata', 'approved_summary', 'approved_chunks',
      'rejected', 'needs_review'
    )
  ),
  add column if not exists review_decided_at timestamptz,
  add column if not exists review_decided_by text,
  add column if not exists review_reason text;

create index if not exists idx_processing_documents_review_decision
  on processing_documents (review_decision);

alter table knowledge_documents drop constraint if exists knowledge_documents_document_type_check;
alter table knowledge_documents add constraint knowledge_documents_document_type_check check (
  document_type in (
    'ADR', 'Architecture', 'Crew', 'Mission', 'Capability',
    'Knowledge Base', 'Specialist', 'Unknown', 'Personal Archive'
  )
);
