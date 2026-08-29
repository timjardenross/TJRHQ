-- Drop the anon_read policies on processing_documents / processing_chunks
-- (0042_document_processing_pipeline.sql) — an unauthenticated-readable
-- "for select to anon using (true)" policy on the Mac Collector Agent's
-- pre-approval staging table, which carries category='Financial|Legal|
-- Health|Identity|Property' / sensitivity='sensitive|restricted' rows with
-- full extracted_text and summary. The platform's anon key is public
-- (embedded in every browser client), so this let anyone holding it
-- SELECT every row of this content.
--
-- 0044_knowledge_library_authenticated_rls.sql already demonstrated this
-- exact leak in its own comment ("set role anon; select count(*) ... -- 3
-- (real rows)") and added the correct replacement (authenticated_read) —
-- but never dropped the original anon_read policy, so both stayed active
-- side by side. Same bug class already fixed once for missions/core_events
-- in 0145_missions_core_events_drop_anon.sql; this generalizes that fix to
-- the one other table pair found carrying it (permissions scoping pass,
-- 2026-08-29 — see docs/UI-Layer-Debt-Handoff-2026-08-29.md's sibling
-- permissions findings, not written up as their own file).
--
-- Verified before writing this migration: no lcars-portal frontend code
-- reads processing_documents/processing_chunks via the anon-key browser
-- client (grep found only server-side API routes, none using
-- createSupabaseBrowserClient) — dropping anon_read breaks no live caller.
-- authenticated_read (0044) remains the real, intended read path.

drop policy if exists "anon_read" on processing_documents;
drop policy if exists "anon_read" on processing_chunks;
