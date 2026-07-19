-- 0015_telegram_engineer_ro.sql
-- Least-privilege Supabase access for the Telegram "Chief Engineer" agent
-- (/opt/starship-endeavour/telegram-bot). Two mandates only:
--   * READ the Command-Memory context tables (SELECT).
--   * APPEND build requests to build_request_inbox (INSERT only — no select/update/delete).
-- The agent authenticates with a PostgREST JWT carrying role: telegram_engineer_ro,
-- minted from SUPABASE_JWT_SECRET (see telegram-bot/supabase_readonly.py).

-- 1) The scoped role. NOLOGIN: only ever reached via PostgREST SET ROLE.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'telegram_engineer_ro') then
    create role telegram_engineer_ro nologin;
  end if;
end$$;

-- 2) Let the PostgREST authenticator switch into it, and see the schema.
grant telegram_engineer_ro to authenticator;
grant usage on schema public to telegram_engineer_ro;

-- 3) Read mandate: SELECT on the five Command-Memory context tables.
grant select on
  public.commander_memory_events,
  public.missions,
  public.decisions,
  public.lessons_learned,
  public.research_memory
to telegram_engineer_ro;

-- 3a) Four of those tables have RLS enabled, so a GRANT alone yields zero rows.
--     Add permissive SELECT policies scoped to this role. (research_memory has RLS
--     disabled today; the policy is inert until RLS is enabled, harmless now and
--     future-proof.)
do $$
declare t text;
begin
  foreach t in array array[
    'commander_memory_events','missions','decisions','lessons_learned','research_memory'
  ] loop
    execute format('drop policy if exists telegram_engineer_ro_select on public.%I', t);
    execute format(
      'create policy telegram_engineer_ro_select on public.%I for select to telegram_engineer_ro using (true)', t);
  end loop;
end$$;

-- 4) Append mandate: the build-request inbox table (governance PENDING_TRIAGE queue).
create table if not exists public.build_request_inbox (
  id                   uuid primary key default gen_random_uuid(),
  request_id           text not null unique,
  source               text not null default 'telegram',
  requested_by         text,
  title                text not null,
  summary              text,
  rationale            text,
  risks                text,
  suggested_next_step  text,
  conversation_context text,
  record_path          text,
  status               text not null default 'pending_triage',
  created_at           timestamptz not null default now()
);

comment on table public.build_request_inbox is
  'Append-only build requests logged by the Telegram Chief Engineer agent. Markdown in Missions/Telegram-Inbox is canonical; this mirrors them for governance. See migration 0015.';

alter table public.build_request_inbox enable row level security;

-- service_role (governance tooling) gets full access; it bypasses RLS anyway.
grant all on public.build_request_inbox to service_role;

-- The agent role may ONLY insert. With return=minimal it needs no SELECT, keeping
-- the table strictly append-only from the agent's side.
grant insert on public.build_request_inbox to telegram_engineer_ro;
drop policy if exists telegram_engineer_ro_insert on public.build_request_inbox;
create policy telegram_engineer_ro_insert
  on public.build_request_inbox for insert to telegram_engineer_ro with check (true);
