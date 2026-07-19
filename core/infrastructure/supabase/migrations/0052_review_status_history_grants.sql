-- Fix a silent gap found while investigating a "Decision failed" report on
-- the Knowledge Library approve flow: `review_status` and `review_history`
-- were added to processing_documents by migration 0047
-- (needs_review_resolution, MSN-0206J-1), but migration 0044's narrow
-- column-grant pattern for `authenticated` (revoke blanket UPDATE, grant
-- only the specific columns decide/route.ts writes) was never extended to
-- cover them. Confirmed directly via information_schema.column_privileges:
-- authenticated had UPDATE on review_decision/review_decided_at/
-- review_decided_by/review_reason/memory_document_id only. Every decided
-- document in the table has review_status = null and review_history = '[]'
-- as a result, regardless of whether the decision itself succeeded --
-- these two columns have never actually persisted for any approval.

grant update (review_status, review_history) on processing_documents to authenticated;
