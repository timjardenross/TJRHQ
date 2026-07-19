-- RLS gap fix: escalation_history, escalation_events, captains_daily_briefs
-- had Row Level Security fully DISABLED (not "enabled with zero policies"
-- like the 0044 precedent) -- meaning every row was readable/writable by
-- the anon and authenticated Supabase client roles with no restriction at
-- all. Surfaced by Supabase's own security advisor during MSN-0207D.
--
-- Verified access paths before writing this migration (grep across the
-- repo, no schema guesswork):
--   - escalation_history / escalation_events: written and read exclusively
--     by slack-bot/escalation_manager.py and slack-bot/alert_metrics.py,
--     both using CommanderSupabaseClient with SUPABASE_SERVICE_ROLE_KEY.
--     No lcars-portal route or any authenticated/anon call site references
--     either table. service_role bypasses RLS regardless of policies, so
--     enabling RLS with NO authenticated/anon policy fully closes the
--     exposure with zero functional change.
--   - captains_daily_briefs: written by intelligence/captains_brief.py via
--     service_role (unaffected by RLS either way). Read by lcars-portal's
--     GET /api/intelligence?view=daily_briefs route
--     (src/app/api/intelligence/route.ts), which uses the anon *key* but
--     resolves to the `authenticated` *role* for a real logged-in Captain
--     session (same mechanism documented in migration 0044) -- this is the
--     one real access path that needs an explicit policy or it silently
--     breaks the moment RLS is enabled.
--
-- Deliberately narrow scope, same discipline as 0044:
--   - No policy at all for escalation_history/escalation_events -- nothing
--     outside service_role reads or writes them today.
--   - SELECT only for authenticated on captains_daily_briefs -- no INSERT/
--     UPDATE/DELETE policy; writes remain service_role-only.
--   - No anon policy on any of the three tables.

alter table escalation_history enable row level security;
alter table escalation_events enable row level security;
alter table captains_daily_briefs enable row level security;

create policy "authenticated_read" on captains_daily_briefs
  for select to authenticated
  using (true);
