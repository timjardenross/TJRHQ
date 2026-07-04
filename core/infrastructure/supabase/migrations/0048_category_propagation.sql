-- USS-TJR-MSN-0206J-2 — Category Propagation.
--
-- Adds a `category` column to knowledge_documents (Command Memory) — the
-- durable table has never had a category taxonomy at all; only
-- processing_documents (pre-approval staging, MSN-0205C) and only for
-- Personal Archive rows. This phase gives EVERY row in knowledge_documents
-- — repo governance content and Personal Archive alike — a category from
-- one shared 8-value taxonomy, so search/filtering works across the whole
-- corpus, not just the personal-file subset.
--
-- Target categories (from the mission spec): Health, Financial, Legal,
-- Reference, Property, Operational Resilience, Learning, Other.
--
-- This taxonomy is deliberately DIFFERENT from processing_documents'
-- 10-value classifier category (Financial/Legal/Health/Correspondence/
-- Reference/Identity/Property/Photo/Administrative/Other) — that one is
-- tuned for the document-classification model's output; this one is
-- tuned for durable-memory browsing across governance + personal content
-- together. A mapping bridges the two (see below and
-- lcars-portal/src/lib/categoryPropagation.ts, the code counterpart used
-- for every future approval).
--
-- Backfill mapping, applied once here for the 237 existing rows:
--
--   Repo governance content (document_type <> 'Personal Archive'),
--   mapped from document_type:
--     ADR, Architecture, Mission            -> Operational Resilience
--     Crew, Capability, Specialist          -> Reference
--     Knowledge Base                        -> Learning
--     Unknown                               -> Other
--
--   Personal Archive rows, mapped from metadata->>'category'
--   (the processing_documents classifier category, MSN-0205C):
--     Health                                -> Health
--     Financial                             -> Financial
--     Legal, Identity                       -> Legal
--     Reference                             -> Reference
--     Property                              -> Property
--     Correspondence, Administrative, Photo -> Other
--     (missing/unrecognised)                -> Other
--
-- Column-only change to an existing table (ADR-0020: reuse before
-- create — knowledge_documents already exists from MSN-0004).

alter table knowledge_documents
  add column if not exists category text check (
    category is null or category in (
      'Health', 'Financial', 'Legal', 'Reference', 'Property',
      'Operational Resilience', 'Learning', 'Other'
    )
  );

create index if not exists idx_knowledge_documents_category
  on knowledge_documents (category);

-- -- Backfill: repo governance content, from document_type ------------------------------------------------

update knowledge_documents
set category = 'Operational Resilience'
where document_type in ('ADR', 'Architecture', 'Mission') and category is null;

update knowledge_documents
set category = 'Reference'
where document_type in ('Crew', 'Capability', 'Specialist') and category is null;

update knowledge_documents
set category = 'Learning'
where document_type = 'Knowledge Base' and category is null;

update knowledge_documents
set category = 'Other'
where document_type = 'Unknown' and category is null;

-- -- Backfill: Personal Archive rows, from metadata->>'category' ------------------------------------------------

update knowledge_documents
set category = 'Health'
where document_type = 'Personal Archive' and category is null
  and metadata ->> 'category' = 'Health';

update knowledge_documents
set category = 'Financial'
where document_type = 'Personal Archive' and category is null
  and metadata ->> 'category' = 'Financial';

update knowledge_documents
set category = 'Legal'
where document_type = 'Personal Archive' and category is null
  and metadata ->> 'category' in ('Legal', 'Identity');

update knowledge_documents
set category = 'Reference'
where document_type = 'Personal Archive' and category is null
  and metadata ->> 'category' = 'Reference';

update knowledge_documents
set category = 'Property'
where document_type = 'Personal Archive' and category is null
  and metadata ->> 'category' = 'Property';

-- Correspondence/Administrative/Photo, plus anything missing/unrecognised.
update knowledge_documents
set category = 'Other'
where document_type = 'Personal Archive' and category is null;

-- Rollback:
--
-- drop index if exists idx_knowledge_documents_category;
-- alter table knowledge_documents drop column if exists category;
