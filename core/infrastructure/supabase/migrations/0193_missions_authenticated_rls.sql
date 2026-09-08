-- RLS gap fix: authenticated-role INSERT access for public.missions, same
-- root cause and fix pattern as 0044_knowledge_library_authenticated_rls.sql.
--
-- Root cause (found via a live "Failed to create mission: new row violates
-- row-level security policy for table 'missions' code=42501" error, once
-- PR #67/#68 stopped hiding it as "[object Object]"): verified directly
-- against the live database's pg_policy catalog (not just this repo's
-- migration history, which is known to drift from reality — see also the
-- xo-bot.service/tg-xo.service naming drift found earlier this session).
-- public.missions currently has auth_read (SELECT, authenticated) and
-- auth_update (UPDATE, authenticated) — both applied directly against the
-- live database at some point, untracked by any migration file in this
-- repo — plus xo_bot_select (SELECT, xo_bot role) and telegram_engineer_ro_select
-- (SELECT, telegram_engineer_ro role). There has never been a policy
-- granting INSERT to the `authenticated` role, in either the live database
-- or this repo's tracked history.
--
-- lcars-portal's server-side Supabase client (src/lib/supabase-server.ts)
-- uses the anon *key*, but a real logged-in Captain session resolves to
-- the `authenticated` *role* once a session JWT is present — with no
-- INSERT policy matching that role, Postgres unconditionally rejects the
-- write regardless of application-level filters. POST /api/missions
-- (lcars-portal/src/app/api/missions/route.ts) could never have succeeded
-- for a real Captain session until this policy exists. GET already works
-- today (auth_read covers it) — no SELECT policy added here, it would
-- just be a redundant duplicate of the one already live.
--
-- Deliberately narrow, matching 0044's own scope discipline: only INSERT
-- for authenticated on missions, unrestricted `with check (true)` —
-- matches 0044's own knowledge_documents/document_chunks INSERT policies
-- (a create is a full-row create by definition). App-level validation
-- (title required, status enum checked against VALID_STATUSES) already
-- happens in route.ts before this INSERT is ever issued. No other policy,
-- grant, or table is touched.

create policy "authenticated_insert" on public.missions
  for insert to authenticated
  with check (true);
