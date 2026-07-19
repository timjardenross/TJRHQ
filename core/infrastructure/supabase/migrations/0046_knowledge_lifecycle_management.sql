-- USS-TJR-MSN-0206D — Knowledge Lifecycle Management.
--
-- Adds retention classification to knowledge_documents (Command Memory) —
-- the durable table, not the pre-approval processing_documents staging
-- area (MSN-0206B's exclusion_reason work). Four new columns:
--   - retention_policy: one of 5 classes (Permanent/Long-Term/Temporary/
--     Expiring/Archived). Assigned automatically at approval time
--     (see lcars-portal src/lib/retentionPolicy.ts, wired into
--     decide/route.ts) based on document category — 'Archived' is never
--     auto-assigned, only set via an explicit Captain action.
--   - expiry_date: nullable — the date a document's content is considered
--     stale enough to warrant reconsideration. NOT an auto-deletion
--     trigger (mission requirement: no automatic deletion) — purely
--     informational, surfaced for the Captain to act on manually.
--   - archive_status: 'active' | 'archived' — simple current-state flag,
--     separate from retention_policy so "what class is this?" and "is it
--     currently archived?" can change independently (a Permanent document
--     can still be manually archived without reclassifying it).
--   - review_due_date: not nullable — every approved document gets a
--     future review nudge, even Permanent ones (identity documents still
--     warrant periodic re-confirmation, e.g. a passport renewal).
--
-- Backfill: existing rows (governance content authored before this
-- pipeline existed, plus any already-approved Personal Archive rows from
-- MSN-0205E) get one-time retention values using the same policy logic
-- applied going forward — see the UPDATE statements below. This is a
-- metadata-only backfill; no content is modified.
--
-- Column-only change to an existing table (ADR-0020: reuse before
-- create — knowledge_documents already exists from MSN-0004).

alter table knowledge_documents
  add column if not exists retention_policy text check (
    retention_policy is null or retention_policy in (
      'Permanent', 'Long-Term', 'Temporary', 'Expiring', 'Archived'
    )
  );

alter table knowledge_documents
  add column if not exists expiry_date timestamptz;

alter table knowledge_documents
  add column if not exists archive_status text not null default 'active' check (
    archive_status in ('active', 'archived')
  );

alter table knowledge_documents
  add column if not exists review_due_date timestamptz;

create index if not exists idx_knowledge_documents_retention_policy
  on knowledge_documents (retention_policy);

create index if not exists idx_knowledge_documents_review_due_date
  on knowledge_documents (review_due_date);

-- -- Backfill: repo governance content (everything except Personal Archive) ------------------------------------------------
-- ADRs, Architecture, Crew, Mission, Capability, Knowledge Base, Specialist,
-- Unknown — operational knowledge with no natural expiry.

update knowledge_documents
set
  retention_policy = 'Permanent',
  archive_status = coalesce(archive_status, 'active'),
  review_due_date = coalesce(review_due_date, now() + interval '5 years')
where document_type is distinct from 'Personal Archive'
  and retention_policy is null;

-- -- Backfill: Personal Archive rows already approved (MSN-0205E), by category ------------------------------------------------
-- Mirrors the category -> policy table in lcars-portal/src/lib/retentionPolicy.ts.

update knowledge_documents
set retention_policy = 'Permanent', expiry_date = null, review_due_date = coalesce(review_due_date, now() + interval '5 years')
where document_type = 'Personal Archive' and retention_policy is null
  and metadata ->> 'category' in ('Identity', 'Legal', 'Property');

update knowledge_documents
set retention_policy = 'Long-Term', expiry_date = coalesce(expiry_date, now() + interval '7 years'),
    review_due_date = coalesce(review_due_date, now() + interval '3 years')
where document_type = 'Personal Archive' and retention_policy is null
  and metadata ->> 'category' in ('Financial', 'Health');

update knowledge_documents
set retention_policy = 'Long-Term', expiry_date = null, review_due_date = coalesce(review_due_date, now() + interval '3 years')
where document_type = 'Personal Archive' and retention_policy is null
  and metadata ->> 'category' = 'Reference';

update knowledge_documents
set retention_policy = 'Temporary', expiry_date = coalesce(expiry_date, now() + interval '2 years'),
    review_due_date = coalesce(review_due_date, now() + interval '1 year')
where document_type = 'Personal Archive' and retention_policy is null
  and metadata ->> 'category' in ('Correspondence', 'Administrative');

update knowledge_documents
set retention_policy = 'Temporary', expiry_date = coalesce(expiry_date, now() + interval '5 years'),
    review_due_date = coalesce(review_due_date, now() + interval '2 years')
where document_type = 'Personal Archive' and retention_policy is null
  and metadata ->> 'category' = 'Photo';

-- Anything left over (Personal Archive with a missing/unrecognised
-- category) gets the most conservative class — shortest review window.
update knowledge_documents
set retention_policy = 'Expiring', expiry_date = coalesce(expiry_date, now() + interval '1 year'),
    review_due_date = coalesce(review_due_date, now() + interval '6 months')
where document_type = 'Personal Archive' and retention_policy is null;

-- Rollback:
--
-- drop index if exists idx_knowledge_documents_retention_policy;
-- drop index if exists idx_knowledge_documents_review_due_date;
-- alter table knowledge_documents drop column if exists retention_policy;
-- alter table knowledge_documents drop column if exists expiry_date;
-- alter table knowledge_documents drop column if exists archive_status;
-- alter table knowledge_documents drop column if exists review_due_date;
