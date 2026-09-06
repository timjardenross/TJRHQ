-- Fleet Engineering Review 2026-08-11 (Chief Engineer + XO gate-review):
-- missions.anon_read let anyone holding the public anon key read every
-- mission row. core_events' select/insert/update policies granted anon
-- alongside authenticated, making the platform's Event Bus world-readable
-- AND world-writable. All legitimate access to both tables already goes
-- through session-gated API routes (authenticated role); anon was never
-- needed. Applied live via apply_migration 2026-08-11, tracked here so a
-- rebuild reproduces the fix rather than reopening it.
--
-- Renumbered from 0145 to 0195 by HQ V1 Integration QA §I10: 0145 was also
-- claimed by 0145_exec_assistant_tables.sql (authored 2026-08-10, one day
-- earlier — kept at 0145). Cosmetic only: Supabase tracks this migration by
-- its own applied version (20260811055928), not this filename.

drop policy if exists anon_read on public.missions;

alter policy core_events_select on public.core_events to authenticated;
alter policy core_events_insert_authenticated on public.core_events to authenticated;
alter policy core_events_update on public.core_events to authenticated;
