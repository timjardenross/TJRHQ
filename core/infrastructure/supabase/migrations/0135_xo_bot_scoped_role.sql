-- 0135_xo_bot_scoped_role.sql
-- Least-privilege Supabase access for the live XO Telegram bot
-- (telegram-bots/xo/app.py, @Starship_endeavour_xO_bot).
--
-- Background: XO has run on the `service_role` key since inception —
-- bypasses RLS on all 112 public tables, even though the bot's own code only
-- ever touches 13. See
-- .claude/skills/bot-reviews/fixes-2026-08-09/xo-bot-service-role-decision.md
-- (Option C) for the accepted architecture decision and
-- .claude/skills/bot-reviews/fixes-2026-08-09/xo-bot-scoped-role-implemented.md
-- for the implementation record. Reuses this platform's own proven pattern
-- from migration 0015_telegram_engineer_ro.sql (scoped nologin Postgres role
-- + a self-minted PostgREST JWT carrying a custom `role` claim, minted from
-- SUPABASE_JWT_SECRET) rather than inventing a new mechanism.
--
-- Operation list below was re-verified fresh against the current
-- telegram-bots/xo/app.py, voice_capture.py, and every in-process module it
-- imports (engagement_dispatcher.py, wellness_officer/intelligence.py) —
-- NOT copied forward from the prior investigation's table list, which
-- predates tonight's debrief_engine logging fix and recovery-pulse
-- redesign. Every other command handler in app.py (/advise, /challenge,
-- /learning, /patterns, /captain, /pending, /operating_picture, /daily,
-- mission-governance writes) was traced and confirmed to use either the
-- LCARS Portal HTTP API or a *different*, unaffected credential
-- (SUPABASE_SERVICE_ROLE_KEY via core/health/supabase_client.py,
-- tools/supabase/client.py's CommanderSupabaseClient, or
-- core/platform/heartbeat.py / core/platform/event_bus.py) — none of those
-- paths read SUPABASE_KEY, so they are untouched by this migration or by
-- the .env change that will eventually consume it.
--
-- Two known landmines fixed here that do NOT exist for `authenticated`
-- today (would have silently broken live bot paths if copied verbatim):
--   * captured_items has no `authenticated` DELETE policy live, but
--     handle_voice_debrief_decision_callback deletes a row on every
--     "debrief" decision (app.py). xo_bot gets an explicit DELETE policy.
--   * recovery_pulses has no `authenticated` UPDATE policy live, but
--     voice_capture.py's promote_recovery_pulse() UPDATEs an existing pulse
--     row's notes, and app.py's pulse-write path uses .upsert() (INSERT ON
--     CONFLICT DO UPDATE). xo_bot gets an explicit UPDATE policy.
--
-- Full table/operation matrix (13 tables — not the 9 the prior
-- investigation surfaced; wellness_officer/intelligence.py's
-- health_daily_logs/health_insights and recovery_officer/
-- engagement_dispatcher.py's wellness_reminder_log dedup ledger were found
-- on this pass by tracing every function the bot's own Supabase client is
-- passed into, not just app.py's direct .table() calls):
--   missions                      SELECT
--   recovery_confidence_today (view over recovery_pulses)   SELECT
--   recovery_pulses               SELECT, INSERT, UPDATE
--   activity_logs                 SELECT, INSERT
--   weight_logs                   SELECT, INSERT, UPDATE
--   intelligence_briefs           SELECT
--   intelligence_events            SELECT
--   intelligence_source_health    SELECT
--   intelligence_source_registry  SELECT
--   captured_items                SELECT, INSERT, UPDATE, DELETE
--   health_daily_logs             SELECT
--   health_insights                SELECT
--   wellness_reminder_log         SELECT, INSERT
--
-- Idempotent (drop-then-create policies; role/grants guarded).

-- 1) The scoped role. NOLOGIN: only ever reached via PostgREST SET ROLE
--    (authenticator switches into it based on the JWT's "role" claim).
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'xo_bot') then
    create role xo_bot nologin;
  end if;
end$$;

grant xo_bot to authenticator;
grant usage on schema public to xo_bot;

-- 2) missions — SELECT only. All mission mutations (/mission_create,
--    /captain_approve, /captain_reject, /mission_submit,
--    /handoff_engineering) go through the LCARS Portal HTTP API with its
--    own X-Bot-Secret auth, never through Supabase directly.
grant select on public.missions to xo_bot;
drop policy if exists xo_bot_select on public.missions;
create policy xo_bot_select on public.missions for select to xo_bot using (true);

-- 3) recovery_confidence_today — read-only view over recovery_pulses.
grant select on public.recovery_confidence_today to xo_bot;

-- 4) recovery_pulses — SELECT (status reads, wellness snapshot, 7-day
--    history), INSERT (voice-capture promotion, new pulse rows), UPDATE
--    (voice-capture promotion appending to an existing row's notes; the
--    button-flow .upsert() is INSERT-ON-CONFLICT-DO-UPDATE and needs both).
grant select, insert, update on public.recovery_pulses to xo_bot;

drop policy if exists xo_bot_select on public.recovery_pulses;
create policy xo_bot_select on public.recovery_pulses for select to xo_bot using (true);

drop policy if exists xo_bot_insert on public.recovery_pulses;
create policy xo_bot_insert on public.recovery_pulses for insert to xo_bot with check (true);

drop policy if exists xo_bot_update on public.recovery_pulses;
create policy xo_bot_update on public.recovery_pulses for update to xo_bot using (true) with check (true);

-- 5) activity_logs — SELECT (wellness snapshot), INSERT (/log_activity).
--    id is bigint/nextval(activity_logs_id_seq) — INSERT needs sequence
--    USAGE too, not just the table grant (caught by in-transaction testing
--    pre-cutover: "permission denied for sequence activity_logs_id_seq"
--    on the first real insert attempt with only the table grant applied).
grant select, insert on public.activity_logs to xo_bot;
grant usage, select on public.activity_logs_id_seq to xo_bot;

drop policy if exists xo_bot_select on public.activity_logs;
create policy xo_bot_select on public.activity_logs for select to xo_bot using (true);

drop policy if exists xo_bot_insert on public.activity_logs;
create policy xo_bot_insert on public.activity_logs for insert to xo_bot with check (true);

-- 6) weight_logs — SELECT (wellness snapshot), INSERT+UPDATE (/log_weight
--    .upsert() on the log_date unique constraint). Same sequence-grant
--    landmine as activity_logs — id is bigint/nextval(weight_logs_id_seq).
grant select, insert, update on public.weight_logs to xo_bot;
grant usage, select on public.weight_logs_id_seq to xo_bot;

drop policy if exists xo_bot_select on public.weight_logs;
create policy xo_bot_select on public.weight_logs for select to xo_bot using (true);

drop policy if exists xo_bot_insert on public.weight_logs;
create policy xo_bot_insert on public.weight_logs for insert to xo_bot with check (true);

drop policy if exists xo_bot_update on public.weight_logs;
create policy xo_bot_update on public.weight_logs for update to xo_bot using (true) with check (true);

-- 7) intelligence_briefs — SELECT only (/brief, /themes).
grant select on public.intelligence_briefs to xo_bot;
drop policy if exists xo_bot_select on public.intelligence_briefs;
create policy xo_bot_select on public.intelligence_briefs for select to xo_bot using (true);

-- 8) intelligence_events — SELECT only (/signals).
grant select on public.intelligence_events to xo_bot;
drop policy if exists xo_bot_select on public.intelligence_events;
create policy xo_bot_select on public.intelligence_events for select to xo_bot using (true);

-- 9) intelligence_source_health — SELECT only (/source_status). Already
--    anon-readable live; xo_bot still needs its own table-level GRANT
--    (privilege and policy are separate checks).
grant select on public.intelligence_source_health to xo_bot;
drop policy if exists xo_bot_select on public.intelligence_source_health;
create policy xo_bot_select on public.intelligence_source_health for select to xo_bot using (true);

-- 10) intelligence_source_registry — SELECT only (/source_status).
grant select on public.intelligence_source_registry to xo_bot;
drop policy if exists xo_bot_select on public.intelligence_source_registry;
create policy xo_bot_select on public.intelligence_source_registry for select to xo_bot using (true);

-- 11) captured_items — SELECT, INSERT, UPDATE, DELETE. Voice capture
--     (insert), /note (insert), capture-confirmation buttons (update x3),
--     voice-debrief-decision buttons (select + update + DELETE on the
--     "start a debrief" path). The DELETE policy is the landmine the prior
--     investigation flagged as missing for `authenticated` — added here
--     for xo_bot explicitly, verified by the standalone test script before
--     any cutover.
grant select, insert, update, delete on public.captured_items to xo_bot;

drop policy if exists xo_bot_select on public.captured_items;
create policy xo_bot_select on public.captured_items for select to xo_bot using (true);

drop policy if exists xo_bot_insert on public.captured_items;
create policy xo_bot_insert on public.captured_items for insert to xo_bot with check (true);

drop policy if exists xo_bot_update on public.captured_items;
create policy xo_bot_update on public.captured_items for update to xo_bot using (true) with check (true);

drop policy if exists xo_bot_delete on public.captured_items;
create policy xo_bot_delete on public.captured_items for delete to xo_bot using (true);

-- 12) health_daily_logs — SELECT only (wellness snapshot; this table is
--     written by the health-logging portal/pipeline, not by XO).
grant select on public.health_daily_logs to xo_bot;
drop policy if exists xo_bot_select on public.health_daily_logs;
create policy xo_bot_select on public.health_daily_logs for select to xo_bot using (true);

-- 13) health_insights — SELECT only (wellness snapshot; written by the
--     weekly insight-generation job, not by XO).
grant select on public.health_insights to xo_bot;
drop policy if exists xo_bot_select on public.health_insights;
create policy xo_bot_select on public.health_insights for select to xo_bot using (true);

-- 14) wellness_reminder_log — SELECT (dedup check) + INSERT (dedup marker)
--     from engagement_dispatcher.py's run_dispatch_check(), reached via
--     XO's own /dispatch command with its own client passed in explicitly.
grant select, insert on public.wellness_reminder_log to xo_bot;

drop policy if exists xo_bot_select on public.wellness_reminder_log;
create policy xo_bot_select on public.wellness_reminder_log for select to xo_bot using (true);

drop policy if exists xo_bot_insert on public.wellness_reminder_log;
create policy xo_bot_insert on public.wellness_reminder_log for insert to xo_bot with check (true);
