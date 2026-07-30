-- USS-TJR-MSN-0205 — RLS gap fix: authenticated-role access for the
-- Knowledge Library and its Command Memory approval write path.
--
-- Root cause (found via a live smoke test, not by inspection alone):
-- migrations 0042/0043 only granted RLS access to `anon` and
-- `service_role`. lcars-portal's server-side Supabase client
-- (src/lib/supabase-server.ts) uses the anon *key*, but a real logged-in
-- Captain session resolves to the `authenticated` *role* once a session
-- JWT is present — and with no RLS policy matching that role, Postgres
-- silently returns zero rows for reads and rejects writes, regardless of
-- application-level filters. Verified empirically before writing this
-- migration:
--   set role authenticated; select count(*) from processing_documents;  -- 0
--   set role anon;          select count(*) from processing_documents;  -- 3 (real rows)
-- `knowledge_documents`/`document_chunks` (from 0001) have zero RLS
-- policies at all today — not even for anon/service_role — which will
-- separately block MSN-0205D's approval write (INSERT) the moment the
-- read-side gap above is fixed and a Captain can reach the Approve
-- button. Both gaps are fixed together here since they're the same class
-- of issue on the same feature's data path.
--
-- Authorised exception to ADR-0020 (reuse before create): policy/grant
-- changes only, no new table — same governance lineage as 0042/0043.
--
-- Deliberately narrow scope:
--   - SELECT for authenticated on processing_documents, processing_chunks,
--     knowledge_documents, document_chunks.
--   - INSERT for authenticated on knowledge_documents, document_chunks
--     only — the two tables MSN-0205D's decide route writes into.
--   - UPDATE for authenticated on processing_documents, restricted to
--     exactly the 5 columns decide/route.ts sets (review_decision,
--     review_decided_at, review_decided_by, review_reason,
--     memory_document_id), and only for rows that are currently
--     status = 'awaiting_review' with review_decision still null —
--     mirroring decide/route.ts's own 409 guard against re-deciding an
--     already-decided row. Column restriction requires REVOKEing
--     Supabase's default blanket UPDATE grant first: an RLS policy alone
--     narrows which ROWS are reachable, not which COLUMNS an UPDATE's SET
--     clause may touch, and the platform-default schema-wide grant
--     already includes UPDATE on every column for `authenticated`.
-- No blanket "for all"/"for update using (true)" policy is added for
-- `authenticated` anywhere. No other table is touched.

-- -- processing_documents ------------------------------------------------

create policy "authenticated_read" on processing_documents
  for select to authenticated
  using (true);

revoke update on processing_documents from authenticated;
grant update (
  review_decision, review_decided_at, review_decided_by, review_reason, memory_document_id
) on processing_documents to authenticated;

create policy "authenticated_update_review_decision" on processing_documents
  for update to authenticated
  using (status = 'awaiting_review' and review_decision is null)
  with check (status = 'awaiting_review');

-- -- processing_chunks ------------------------------------------------

create policy "authenticated_read" on processing_chunks
  for select to authenticated
  using (true);

-- -- knowledge_documents (Command Memory) ------------------------------------------------

create policy "authenticated_read" on knowledge_documents
  for select to authenticated
  using (true);

create policy "authenticated_insert" on knowledge_documents
  for insert to authenticated
  with check (true);

-- -- document_chunks (Command Memory chunk embeddings) ------------------------------------------------

create policy "authenticated_read" on document_chunks
  for select to authenticated
  using (true);

create policy "authenticated_insert" on document_chunks
  for insert to authenticated
  with check (true);
