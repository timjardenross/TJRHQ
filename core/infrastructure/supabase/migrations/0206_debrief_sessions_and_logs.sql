-- 0206_debrief_sessions_and_logs.sql
--
-- Recreates debrief_sessions/debrief_logs — the tables behind
-- telegram-bots/xo/debrief_engine.py. That module was built 2026-07-07
-- (XO Voice Daily Debrief), is still imported live at three call sites in
-- telegram-bots/xo/app.py (cmd_message, cmd_voice_note,
-- handle_voice_debrief_decision_callback — all three already catch
-- ImportError and degrade to plain quick-capture), but the source file
-- was never committed to git (`git log --all` returns zero hits for the
-- filename) and is now gone from every checkout. Confirmed by the Chief
-- Engineer review at .claude/skills/bot-reviews/xo-telegram-bot/
-- chief-engineer-review.md, Finding 6 — logged there as a correctness
-- gap, not a security one. This migration and debrief_engine.py's own
-- rebuild are the fix.
--
-- debrief_sessions/debrief_logs already existed as out-of-band,
-- uncommitted tables when the original module was live — `create table
-- if not exists` below is deliberately non-destructive: if a live table
-- from the original build still exists with a different column shape,
-- this migration is a no-op against it (never drops/alters), and the
-- rebuilt debrief_engine.py's column names below would need reconciling
-- against whatever that live shape turns out to be. debrief_logs' shape
-- IS independently verified, though — intelligence/captains_brief.py's
-- _get_recent_debrief_logs() (a real, currently-working consumer that
-- predates this migration) already selects exactly these columns:
-- title, key_themes, stressors, energy_sources, open_loops,
-- ideas_captured, decisions_emerging, change_talk, follow_up_candidate,
-- log_date — so this migration's debrief_logs shape is constrained to
-- match that real, live reader, not guessed independently.

create table if not exists debrief_sessions (
  id          uuid primary key default gen_random_uuid(),
  chat_id     bigint not null,
  status      text not null default 'active' check (status in ('active', 'closed')),
  -- Ordered turn history: [{"role": "captain"|"xo", "text": "...", "at": "<iso8601>"}, ...].
  -- Kept on the session row (not a separate table) — a debrief session is
  -- short-lived and read/written as one whole unit every turn, never
  -- queried per-turn independently.
  turns       jsonb not null default '[]'::jsonb,
  started_at  timestamptz not null default now(),
  closed_at   timestamptz,
  created_at  timestamptz not null default now()
);

-- One active session per chat is the invariant get_active_session()/
-- route_debrief_interaction() rely on — partial unique index enforces it
-- at the database level rather than trusting application code alone.
create unique index if not exists idx_debrief_sessions_one_active_per_chat
  on debrief_sessions(chat_id) where status = 'active';

comment on table debrief_sessions is
  'One row per XO voice-debrief conversation (telegram-bots/xo/debrief_engine.py). status=active until a closing utterance is detected or the LLM synthesis step runs, then closed. At most one active row per chat_id (partial unique index).';

create table if not exists debrief_logs (
  id                   uuid primary key default gen_random_uuid(),
  session_id           uuid references debrief_sessions(id) on delete set null,
  log_date             date not null default (now() at time zone 'Australia/Brisbane')::date,
  title                text,
  key_themes           jsonb not null default '[]'::jsonb,
  stressors            jsonb not null default '[]'::jsonb,
  energy_sources       jsonb not null default '[]'::jsonb,
  open_loops           jsonb not null default '[]'::jsonb,
  ideas_captured       jsonb not null default '[]'::jsonb,
  decisions_emerging   jsonb not null default '[]'::jsonb,
  change_talk          jsonb not null default '[]'::jsonb,
  follow_up_candidate  text,
  -- Raw concatenated Captain turns, always written regardless of whether
  -- LLM synthesis of the structured fields above succeeds — a synthesis
  -- failure must never mean the session's actual content is lost, only
  -- that it's unstructured until re-processed.
  raw_transcript       text,
  created_at           timestamptz not null default now()
);

create index if not exists idx_debrief_logs_log_date on debrief_logs(log_date desc);

comment on table debrief_logs is
  'One row per closed debrief_sessions row, holding the LLM-synthesized structured summary. Column shape is constrained by intelligence/captains_brief.py::_get_recent_debrief_logs() and generate_weekly_debrief_digest(), both real, already-live consumers — do not rename these columns without updating that reader.';

alter table debrief_sessions enable row level security;
alter table debrief_logs     enable row level security;

-- Same convention as alerts/alert_silences (migrations 0174/0205):
-- service_role (the XO bot's own Supabase client) does all reads/writes;
-- authenticated (any future LCARS Portal read-only view) gets select only.
drop policy if exists debrief_sessions_service_write on debrief_sessions;
create policy debrief_sessions_service_write on debrief_sessions
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
drop policy if exists debrief_sessions_authenticated_read on debrief_sessions;
create policy debrief_sessions_authenticated_read on debrief_sessions
  for select to authenticated using (true);

drop policy if exists debrief_logs_service_write on debrief_logs;
create policy debrief_logs_service_write on debrief_logs
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
drop policy if exists debrief_logs_authenticated_read on debrief_logs;
create policy debrief_logs_authenticated_read on debrief_logs
  for select to authenticated using (true);
