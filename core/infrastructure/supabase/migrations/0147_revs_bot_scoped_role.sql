-- 0147_revs_bot_scoped_role.sql
-- Schema + least-privilege Supabase access for the new REVS Telegram bot
-- (telegram-bots/revs/app.py, @tjrmindbody_bot).
--
-- Background: REVS_Telegram_Prompt_Library.md / REVS_Telegram_Worksheet_
-- Mapping.md (TJRHQ repo root, added 2026-08-14) specify a scheduled,
-- multi-user Telegram bot delivering the REVS coaching framework to the
-- public. This is a DIFFERENT product from the existing `/revs_generate`
-- command in telegram-bots/xo/app.py, which triggers
-- services/revs-content-agents (marketing asset generation) and is
-- Captain-only. No code or table overlap between the two — flagged here
-- only because of the shared "REVS" name.
--
-- This bot is deliberately NOT added to the XO bot (tg-xo.service). XO is
-- hard-allowlisted to a single chat_id (Captain only — see
-- migration 0135_xo_bot_scoped_role.sql / app.py::_global_auth_gate) and
-- runs with host/shell control. Routing public, health-adjacent traffic
-- from arbitrary Telegram users through that process would put stranger
-- input in the same trust boundary as mission-governance and host
-- commands. This bot gets its own token, own systemd unit, own scoped
-- Postgres role — reusing only the *pattern* migration 0135 established
-- (nologin role + self-minted PostgREST JWT), not the role or the tables.
--
-- Row-level scoping note: policies below use `using (true)` for the
-- `revs_bot` role, same as migration 0135's `xo_bot` policies. This is a
-- table/operation-level allowlist, not per-row tenant isolation — REVS is
-- a single trusted backend process (never a client-issued per-user JWT),
-- so cross-user isolation is enforced in application code (every query
-- scoped by telegram user id), the same trust model XO already runs on.
-- The RLS layer's job here is defense-in-depth against `anon`/other roles,
-- not against a bug in this bot's own query code.
--
-- Idempotent (drop-then-create policies; role/grants/tables guarded).

-- ============================================================
-- 1) Tables
-- ============================================================

create table if not exists public.revs_users (
  id                  bigint primary key,               -- Telegram user id
  first_name          text,
  locale              text check (locale in ('AU', 'UK', 'US', 'OTHER')),
  consent_at          timestamptz,
  pem_flag            boolean,
  pem_certainty       text check (pem_certainty in ('stated', 'precautionary', 'cleared')),
  pem_set_at          timestamptz,
  pem_override_at     timestamptz,
  stage               text check (stage in ('RECOGNISE', 'REGULATE', 'REBUILD', 'REDESIGN')),
  stage_set_at        timestamptz,
  am_time             time,
  pm_time             time,
  pm_enabled          boolean not null default true,
  weekly_day          text,
  weekly_time         time,
  baseline            text,
  onboarding_step     text not null default 'welcome',
  onboarding_complete boolean not null default false,
  paused_until        timestamptz,
  quiet_until         timestamptz,
  whatheld_enabled    boolean not null default false,
  activity_window     text,
  recovery_window     text,
  last_seen_at        timestamptz,
  downward_trend_alert_at        timestamptz,  -- §5.1: last time the trend alert fired
  downward_trend_suppressed_until timestamptz, -- §5.1 "Leave me be" -> 72h
  silence_notice_sent_at         timestamptz,  -- §5.5: sent-once guard
  weekly_skip_count              int not null default 0,   -- §3.1 "three skipped reviews"
  weekly_pause_offer_sent        boolean not null default false,
  weekly_skip_last_counted       date,  -- guards against counting the same missed week twice across scan runs
  pending_pem_trigger            text,  -- §5.6 audit label for the next PEM answer when it's a re-screen, not initial onboarding (see onboarding.py)
  created_at          timestamptz not null default now()
);

create table if not exists public.revs_checkins (
  id             bigserial primary key,
  user_id        bigint not null references public.revs_users(id) on delete cascade,
  checkin_date   date not null,
  period         text not null check (period in ('am', 'pm')),
  state          text,                       -- am: steady/low/depleted/wound_up/skip; pm: under/about_right/over/no_idea/skip
  shape          text,                       -- am steady sub-branch: light/normal/heavy/unknown
  recovery_plan  text,                       -- am heavy sub-branch: scheduled/find_it/none
  cause          text,                       -- pm over sub-branch
  note           text,                       -- free text (what-held / about-right note)
  note_non_replayable boolean not null default false,
  created_at     timestamptz not null default now(),
  unique (user_id, checkin_date, period)
);

create table if not exists public.revs_weekly_reviews (
  id            bigserial primary key,
  user_id       bigint not null references public.revs_users(id) on delete cascade,
  week_start    date not null,
  what_held     text,
  what_didnt    text,
  why_cause     text,
  system_1      text,
  system_1_rating text,
  system_2      text,
  system_2_rating text,
  next_week     text,
  created_at    timestamptz not null default now(),
  unique (user_id, week_start)
);

create table if not exists public.revs_tools (
  id                bigserial primary key,
  user_id           bigint not null references public.revs_users(id) on delete cascade,
  slot              int not null check (slot between 1 and 3),
  approach          text not null check (approach in ('somatic', 'breath', 'grounding', 'movement', 'sound', 'connection', 'cognitive')),
  instruction       text not null,
  non_replayable    boolean not null default false,
  created_at        timestamptz not null default now(),
  unique (user_id, slot)
);

create table if not exists public.revs_setbacks (
  id                    bigserial primary key,
  user_id               bigint not null references public.revs_users(id) on delete cascade,
  occurred_at           timestamptz not null default now(),
  reflection_status     text not null default 'pending' check (reflection_status in ('pending', 'done', 'declined')),
  reflection_due_at     timestamptz,
  precursor             text,
  saw_it_coming         text,                 -- yes_kept_going / yes_too_late / no_warning / not_sure
  warning_signal        text,
  warning_non_replayable boolean not null default false,
  created_at            timestamptz not null default now()
);

create table if not exists public.revs_crisis_events (
  id                 bigserial primary key,
  user_id            bigint not null references public.revs_users(id) on delete cascade,
  trigger_type       text not null check (trigger_type in ('language', 'nontext')),
  triggered_at       timestamptz not null default now(),
  recontact_due_at   timestamptz,
  recontact_sent_at  timestamptz,
  dont_show_again    boolean not null default false,
  suppressed_until   timestamptz
);

create table if not exists public.revs_pem_screen_log (
  id           bigserial primary key,
  user_id      bigint not null references public.revs_users(id) on delete cascade,
  result       text not null check (result in ('yes', 'uncertain', 'no')),
  trigger      text not null,   -- onboarding / expand_gate2 / setback_followup / periodic_90d / user_command
  created_at   timestamptz not null default now()
);

create index if not exists revs_checkins_user_date_idx on public.revs_checkins (user_id, checkin_date desc);
create index if not exists revs_weekly_reviews_user_week_idx on public.revs_weekly_reviews (user_id, week_start desc);
create index if not exists revs_setbacks_pending_idx on public.revs_setbacks (user_id, reflection_status) where reflection_status = 'pending';
create index if not exists revs_crisis_recontact_idx on public.revs_crisis_events (recontact_due_at) where recontact_sent_at is null;

-- ============================================================
-- 2) Scoped role — NOLOGIN, reached only via PostgREST SET ROLE
--    (same mechanism as migration 0135_xo_bot_scoped_role.sql).
-- ============================================================

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'revs_bot') then
    create role revs_bot nologin;
  end if;
end$$;

grant revs_bot to authenticator;
grant usage on schema public to revs_bot;

-- revs_users — full CRUD (onboarding creates/updates; /deleteme deletes).
grant select, insert, update, delete on public.revs_users to revs_bot;
drop policy if exists revs_bot_select on public.revs_users;
create policy revs_bot_select on public.revs_users for select to revs_bot using (true);
drop policy if exists revs_bot_insert on public.revs_users;
create policy revs_bot_insert on public.revs_users for insert to revs_bot with check (true);
drop policy if exists revs_bot_update on public.revs_users;
create policy revs_bot_update on public.revs_users for update to revs_bot using (true) with check (true);
drop policy if exists revs_bot_delete on public.revs_users;
create policy revs_bot_delete on public.revs_users for delete to revs_bot using (true);

-- revs_checkins — SELECT/INSERT/UPDATE (upsert on the daily unique
-- constraint) + DELETE (/deleteme, and cascade already handles it, but the
-- bot's own /deleteme path deletes explicitly rather than relying only on
-- FK cascade, per "deletion is immediate and total").
grant select, insert, update, delete on public.revs_checkins to revs_bot;
grant usage, select on public.revs_checkins_id_seq to revs_bot;
drop policy if exists revs_bot_select on public.revs_checkins;
create policy revs_bot_select on public.revs_checkins for select to revs_bot using (true);
drop policy if exists revs_bot_insert on public.revs_checkins;
create policy revs_bot_insert on public.revs_checkins for insert to revs_bot with check (true);
drop policy if exists revs_bot_update on public.revs_checkins;
create policy revs_bot_update on public.revs_checkins for update to revs_bot using (true) with check (true);
drop policy if exists revs_bot_delete on public.revs_checkins;
create policy revs_bot_delete on public.revs_checkins for delete to revs_bot using (true);

-- revs_weekly_reviews
grant select, insert, update, delete on public.revs_weekly_reviews to revs_bot;
grant usage, select on public.revs_weekly_reviews_id_seq to revs_bot;
drop policy if exists revs_bot_select on public.revs_weekly_reviews;
create policy revs_bot_select on public.revs_weekly_reviews for select to revs_bot using (true);
drop policy if exists revs_bot_insert on public.revs_weekly_reviews;
create policy revs_bot_insert on public.revs_weekly_reviews for insert to revs_bot with check (true);
drop policy if exists revs_bot_update on public.revs_weekly_reviews;
create policy revs_bot_update on public.revs_weekly_reviews for update to revs_bot using (true) with check (true);
drop policy if exists revs_bot_delete on public.revs_weekly_reviews;
create policy revs_bot_delete on public.revs_weekly_reviews for delete to revs_bot using (true);

-- revs_tools — stores the user's own free-text regulation instructions.
-- §5.7: screened at storage time by the bot; non_replayable is a data
-- column here, not an RLS concern.
grant select, insert, update, delete on public.revs_tools to revs_bot;
grant usage, select on public.revs_tools_id_seq to revs_bot;
drop policy if exists revs_bot_select on public.revs_tools;
create policy revs_bot_select on public.revs_tools for select to revs_bot using (true);
drop policy if exists revs_bot_insert on public.revs_tools;
create policy revs_bot_insert on public.revs_tools for insert to revs_bot with check (true);
drop policy if exists revs_bot_update on public.revs_tools;
create policy revs_bot_update on public.revs_tools for update to revs_bot using (true) with check (true);
drop policy if exists revs_bot_delete on public.revs_tools;
create policy revs_bot_delete on public.revs_tools for delete to revs_bot using (true);

-- revs_setbacks — warning_signal is the other §5.7-screened free-text field.
grant select, insert, update, delete on public.revs_setbacks to revs_bot;
grant usage, select on public.revs_setbacks_id_seq to revs_bot;
drop policy if exists revs_bot_select on public.revs_setbacks;
create policy revs_bot_select on public.revs_setbacks for select to revs_bot using (true);
drop policy if exists revs_bot_insert on public.revs_setbacks;
create policy revs_bot_insert on public.revs_setbacks for insert to revs_bot with check (true);
drop policy if exists revs_bot_update on public.revs_setbacks;
create policy revs_bot_update on public.revs_setbacks for update to revs_bot using (true) with check (true);
drop policy if exists revs_bot_delete on public.revs_setbacks;
create policy revs_bot_delete on public.revs_setbacks for delete to revs_bot using (true);

-- revs_crisis_events
grant select, insert, update, delete on public.revs_crisis_events to revs_bot;
grant usage, select on public.revs_crisis_events_id_seq to revs_bot;
drop policy if exists revs_bot_select on public.revs_crisis_events;
create policy revs_bot_select on public.revs_crisis_events for select to revs_bot using (true);
drop policy if exists revs_bot_insert on public.revs_crisis_events;
create policy revs_bot_insert on public.revs_crisis_events for insert to revs_bot with check (true);
drop policy if exists revs_bot_update on public.revs_crisis_events;
create policy revs_bot_update on public.revs_crisis_events for update to revs_bot using (true) with check (true);
drop policy if exists revs_bot_delete on public.revs_crisis_events;
create policy revs_bot_delete on public.revs_crisis_events for delete to revs_bot using (true);

-- revs_pem_screen_log
grant select, insert, delete on public.revs_pem_screen_log to revs_bot;
grant usage, select on public.revs_pem_screen_log_id_seq to revs_bot;
drop policy if exists revs_bot_select on public.revs_pem_screen_log;
create policy revs_bot_select on public.revs_pem_screen_log for select to revs_bot using (true);
drop policy if exists revs_bot_insert on public.revs_pem_screen_log;
create policy revs_bot_insert on public.revs_pem_screen_log for insert to revs_bot with check (true);
drop policy if exists revs_bot_delete on public.revs_pem_screen_log;
create policy revs_bot_delete on public.revs_pem_screen_log for delete to revs_bot using (true);

-- Enable RLS (tables are newly created, but make the intent explicit and
-- idempotent rather than relying on default-on for new tables).
alter table public.revs_users enable row level security;
alter table public.revs_checkins enable row level security;
alter table public.revs_weekly_reviews enable row level security;
alter table public.revs_tools enable row level security;
alter table public.revs_setbacks enable row level security;
alter table public.revs_crisis_events enable row level security;
alter table public.revs_pem_screen_log enable row level security;
