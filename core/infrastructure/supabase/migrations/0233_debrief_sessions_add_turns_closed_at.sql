-- 0233_debrief_sessions_add_turns_closed_at.sql
-- The live public.debrief_sessions predates migration 0206 (which was written
-- from an uncommitted original), so 0206's `create table if not exists` was a
-- no-op and the table never got the columns telegram-bots/xo/debrief_engine.py
-- writes:
--   turns      jsonb  -- _save_turns(), start_session_with_first_turn(), _close_session()
--   closed_at  timestamptz -- _close_session()
-- Symptom (2026-10-11): any plain Telegram message hit
-- PGRST204 "Could not find the 'turns' column of 'debrief_sessions'" whenever a
-- debrief session was active, and the generic "something went wrong" reply
-- was sent. The live table keeps its other columns (ended_at, current_mode,
-- turn_count, last_activity_at, stale_prompt_pending); they are not touched.
--
-- Grants: xo_bot already holds TABLE-level select/insert/update on
-- debrief_sessions (0232), which covers columns added later, so no new
-- grant is needed. Verify after applying with has_column_privilege().
--
-- Idempotent. Followed by a PostgREST schema-cache reload.
--
-- ROLLBACK:
--   alter table public.debrief_sessions drop column if exists turns;
--   alter table public.debrief_sessions drop column if exists closed_at;

alter table public.debrief_sessions
  add column if not exists turns jsonb not null default '[]'::jsonb;

alter table public.debrief_sessions
  add column if not exists closed_at timestamptz;

notify pgrst, 'reload schema';
