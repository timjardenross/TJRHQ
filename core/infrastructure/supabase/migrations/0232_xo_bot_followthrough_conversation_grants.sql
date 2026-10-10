-- 0232_xo_bot_followthrough_conversation_grants.sql
-- Complete the least-privilege grants for the scoped `xo_bot` role
-- (created in 0135) for the tables the live XO bot touches that 0135 and
-- later migrations never granted. Without these, XO on the scoped role
-- gets "permission denied" on follow-through actions, conversation recall,
-- the /brief regenerate cooldown and the voice debrief flow.
--
-- Found by comparing every `.table("<name>")` call in telegram-bots/xo/*.py
-- with has_table_privilege('xo_bot', ...) on the live database.
--
-- Operation matrix (call site -> operation). Line numbers are
-- telegram-bots/xo/ at the time of writing.
--
--   personal_tasks (RLS on)
--     app.py _ft_snooze/_ft_defer_tomorrow/_ft_decompose_and_start (select
--       deferral_count / title,micro_action,restart_cue)      SELECT
--     app.py _ft_mark_done/_ft_snooze/_ft_defer_tomorrow/_ft_snooze_weekday/
--       _ft_decompose_and_start/_ft_block/_ft_drop (update)   UPDATE, limited
--       to the 8 columns those calls write (column-level grant):
--       work_state, completed_at, deferral_count, snoozed_until,
--       next_review_at, micro_action, blocker_category, follow_through_mode
--     No INSERT (capture goes through captured_items) and no DELETE.
--
--   follow_through_events (RLS on)
--     app.py _ft_insert_event (insert)                         INSERT
--     + SELECT: supabase-py sends Prefer: return=representation on insert,
--       so PostgREST runs INSERT ... RETURNING, which needs SELECT.
--     No UPDATE, no DELETE.
--
--   follow_through_sends (RLS on)
--     app.py cmd_message reply-to-reminder lookup (select)     SELECT
--     (rows are WRITTEN by intelligence/adhd/follow_through_engine.py on the
--     service key, not by XO.) No INSERT/UPDATE/DELETE.
--
--   conversation_turns (RLS on)
--     app.py _log_conversation_turn (insert)                   INSERT
--     app.py _get_recent_turns (select)                        SELECT
--     No UPDATE (consolidated_at is set by a separate job), no DELETE.
--
--   bot_rate_limits (RLS on)
--     app.py _get_brief_regen_started_at (select)              SELECT
--     app.py _set_brief_regen_started_at (upsert on PK rate_key)
--                                                              INSERT, UPDATE
--     No DELETE.
--
--   debrief_sessions (RLS on; xo_bot policies exist from 0215, table
--   privileges never granted)
--     debrief_engine.py (select / insert / update)             SELECT, INSERT, UPDATE
--   debrief_logs (RLS on; same)
--     debrief_engine.py (insert; RETURNING needs select)       SELECT, INSERT
--
-- RLS: already enabled on all seven tables. Their existing policies are
-- scoped to service_role / authenticated and do not match xo_bot (the
-- conversation_turns write policy keys on auth.role() = 'service_role'),
-- so each table gets explicit xo_bot policies, one per granted operation.
-- The debrief tables already have xo_bot policies (0215) and only need the
-- table privileges. Policies are `using (true)`: XO is a single-Captain bot
-- and the privilege boundary here is the table/operation/column grant.
--
-- All tables use uuid primary keys with gen_random_uuid(), so no sequence
-- grants are needed.
--
-- Idempotent: grants are repeatable, policies are drop-then-create.
--
-- ROLLBACK (run manually if XO must lose these again):
--   revoke select, insert, update on public.debrief_sessions from xo_bot;
--   revoke select, insert on public.debrief_logs from xo_bot;
--   revoke select, update on public.personal_tasks from xo_bot;
--   revoke select, insert on public.follow_through_events from xo_bot;
--   revoke select on public.follow_through_sends from xo_bot;
--   revoke select, insert on public.conversation_turns from xo_bot;
--   revoke select, insert, update on public.bot_rate_limits from xo_bot;
--   drop policy if exists xo_bot_select on public.personal_tasks;
--   drop policy if exists xo_bot_update on public.personal_tasks;
--   drop policy if exists xo_bot_select on public.follow_through_events;
--   drop policy if exists xo_bot_insert on public.follow_through_events;
--   drop policy if exists xo_bot_select on public.follow_through_sends;
--   drop policy if exists xo_bot_select on public.conversation_turns;
--   drop policy if exists xo_bot_insert on public.conversation_turns;
--   drop policy if exists xo_bot_select on public.bot_rate_limits;
--   drop policy if exists xo_bot_insert on public.bot_rate_limits;
--   drop policy if exists xo_bot_update on public.bot_rate_limits;

-- personal_tasks: SELECT + column-limited UPDATE
grant select on public.personal_tasks to xo_bot;
grant update (work_state, completed_at, deferral_count, snoozed_until,
              next_review_at, micro_action, blocker_category,
              follow_through_mode)
  on public.personal_tasks to xo_bot;

drop policy if exists xo_bot_select on public.personal_tasks;
create policy xo_bot_select on public.personal_tasks
  for select to xo_bot using (true);
drop policy if exists xo_bot_update on public.personal_tasks;
create policy xo_bot_update on public.personal_tasks
  for update to xo_bot using (true) with check (true);

-- follow_through_events: INSERT (+ SELECT for RETURNING)
grant select, insert on public.follow_through_events to xo_bot;

drop policy if exists xo_bot_select on public.follow_through_events;
create policy xo_bot_select on public.follow_through_events
  for select to xo_bot using (true);
drop policy if exists xo_bot_insert on public.follow_through_events;
create policy xo_bot_insert on public.follow_through_events
  for insert to xo_bot with check (true);

-- follow_through_sends: SELECT only
grant select on public.follow_through_sends to xo_bot;

drop policy if exists xo_bot_select on public.follow_through_sends;
create policy xo_bot_select on public.follow_through_sends
  for select to xo_bot using (true);

-- conversation_turns: SELECT + INSERT
grant select, insert on public.conversation_turns to xo_bot;

drop policy if exists xo_bot_select on public.conversation_turns;
create policy xo_bot_select on public.conversation_turns
  for select to xo_bot using (true);
drop policy if exists xo_bot_insert on public.conversation_turns;
create policy xo_bot_insert on public.conversation_turns
  for insert to xo_bot with check (true);

-- bot_rate_limits: SELECT + INSERT + UPDATE (upsert on rate_key)
grant select, insert, update on public.bot_rate_limits to xo_bot;

drop policy if exists xo_bot_select on public.bot_rate_limits;
create policy xo_bot_select on public.bot_rate_limits
  for select to xo_bot using (true);
drop policy if exists xo_bot_insert on public.bot_rate_limits;
create policy xo_bot_insert on public.bot_rate_limits
  for insert to xo_bot with check (true);
drop policy if exists xo_bot_update on public.bot_rate_limits;
create policy xo_bot_update on public.bot_rate_limits
  for update to xo_bot using (true) with check (true);

-- debrief_sessions / debrief_logs: table privileges only (policies: 0215)
grant select, insert, update on public.debrief_sessions to xo_bot;
grant select, insert on public.debrief_logs to xo_bot;
