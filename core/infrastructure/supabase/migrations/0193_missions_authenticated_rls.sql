-- RLS gap fix: authenticated-role access for public.missions, same root
-- cause and fix pattern as 0044_knowledge_library_authenticated_rls.sql.
--
-- Root cause (found via a live "Failed to create mission: new row violates
-- row-level security policy for table 'missions' code=42501" error, once
-- PR #67/#68 stopped hiding it as "[object Object]"): a full scan of every
-- migration ever written against public.missions turns up exactly one
-- policy, ever — xo_bot_select (SELECT, to the xo_bot role only) — plus a
-- since-dropped anon_read. There has never been a policy granting SELECT
-- or INSERT to the `authenticated` role. lcars-portal's server-side
-- Supabase client (src/lib/supabase-server.ts) uses the anon *key*, but a
-- real logged-in Captain session resolves to the `authenticated` *role*
-- once a session JWT is present — with no RLS policy matching that role,
-- Postgres silently returns zero rows for reads and unconditionally
-- rejects writes, regardless of application-level filters. This means
-- POST /api/missions (lcars-portal/src/app/api/missions/route.ts) could
-- never have succeeded for a real Captain session, and its GET handler —
-- used by the same route to hydrate HQ Evolution's "did my Create Mission
-- handoff succeed" polling — was equally likely returning silently-empty
-- results the whole time. Fixed together since they're the same class of
-- issue on the same table's same feature's data path (0044's own stated
-- rationale for doing the same).
--
-- Deliberately narrow, matching 0044's own scope discipline:
--   - SELECT for authenticated on missions — read access only.
--   - INSERT for authenticated on missions, unrestricted `with check (true)`
--     — matches 0044's own knowledge_documents/document_chunks INSERT
--     policies (a create is a full-row create by definition; there is no
--     narrower column-level equivalent for UPDATE's role in that
--     migration). App-level validation (title required, status enum
--     checked against VALID_STATUSES) already happens in route.ts before
--     this INSERT is ever issued.
--   - No UPDATE or DELETE policy added — this migration only unblocks the
--     two operations route.ts actually performs (GET, POST). Any future
--     authenticated-role UPDATE/DELETE path needs its own scoped policy,
--     not a blanket grant added speculatively here.
-- No other table is touched.

create policy "authenticated_select" on public.missions
  for select to authenticated
  using (true);

create policy "authenticated_insert" on public.missions
  for insert to authenticated
  with check (true);
