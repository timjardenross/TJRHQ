-- USS-TJR-MSN-0206J-1 — Needs Review Resolution.
--
-- Fixes a real deadlock discovered while designing this phase: the decide
-- route's "already decided" guard blocks on `review_decision IS NOT NULL`,
-- which includes `needs_review` — so a document the Captain marked
-- "Needs Review" (intending to revisit it later with more information)
-- becomes permanently undecidable. Confirmed against 3 live rows stuck in
-- exactly this state before this migration
-- (smoke-test-report.pdf, wp-total-business-value-integrated-risk-
-- managment.pdf, Jetstar MMB.pdf — all `review_decision = 'needs_review'`
-- with reasons like "not enough data" / "wrong", never resolvable through
-- the existing UI or API).
--
-- Two new columns on processing_documents:
--   - review_status: the CURRENT workflow state, distinct from
--     review_decision (which is a point-in-time decision label, kept
--     unchanged for backward compatibility). Three values:
--       - awaiting_followup: `needs_review` was chosen — the document
--         stays open for a future decision, does NOT block re-deciding.
--       - resolved: an approve decision (metadata/summary/chunks) was
--         made — memory write happened, terminal.
--       - rejected: explicitly rejected — no memory write, terminal.
--     The decide route's guard changes from "review_decision is not null"
--     to "review_status in ('resolved','rejected')" — only these two
--     values are actually terminal now.
--   - review_history: append-only jsonb array of every decision made on
--     this document over time (decision/decided_by/reason/at), so a
--     document that cycled through needs_review more than once keeps its
--     full audit trail — not just the latest decision's 4 scalar columns
--     (review_decision/review_decided_at/review_decided_by/review_reason,
--     unchanged from 0043, still updated as the "latest decision"
--     snapshot).
--
-- Backfill: every existing decided row gets review_status derived from its
-- current review_decision, and a single retrospective review_history entry
-- reconstructed from its existing review_decision/_at/_by/_reason columns
-- — so the 3 real needs_review documents above become immediately
-- resolvable (review_status = 'awaiting_followup') the moment this
-- migration lands, with their existing "why" (review_reason) preserved as
-- history entry #1.
--
-- Column-only change to an existing table (ADR-0020: reuse before
-- create — processing_documents already exists from 0042).

alter table processing_documents
  add column if not exists review_status text check (
    review_status is null or review_status in (
      'awaiting_followup', 'resolved', 'rejected'
    )
  );

alter table processing_documents
  add column if not exists review_history jsonb not null default '[]'::jsonb;

create index if not exists idx_processing_documents_review_status
  on processing_documents (review_status);

-- Backfill review_status from the existing review_decision.
update processing_documents
set review_status = 'awaiting_followup'
where review_decision = 'needs_review' and review_status is null;

update processing_documents
set review_status = 'rejected'
where review_decision = 'rejected' and review_status is null;

update processing_documents
set review_status = 'resolved'
where review_decision in ('approved_metadata', 'approved_summary', 'approved_chunks')
  and review_status is null;

-- Backfill review_history with one retrospective entry per already-decided row.
update processing_documents
set review_history = jsonb_build_array(
  jsonb_build_object(
    'decision', review_decision,
    'decided_by', review_decided_by,
    'reason', review_reason,
    'at', review_decided_at,
    'note', 'backfilled retrospectively by migration 0047'
  )
)
where review_decision is not null
  and review_history = '[]'::jsonb;

-- Rollback:
--
-- drop index if exists idx_processing_documents_review_status;
-- alter table processing_documents drop column if exists review_status;
-- alter table processing_documents drop column if exists review_history;
