-- MSN-0349: tracks each Home page load so the Executive Change Assembly
-- has a real "since the Captain last looked" boundary, and Home can detect
-- first-session-today / returning-after-absence.
create table if not exists home_sessions (
  id uuid primary key default gen_random_uuid(),
  viewed_at timestamptz not null default now()
);
create index if not exists idx_home_sessions_viewed_at on home_sessions(viewed_at desc);
alter table home_sessions enable row level security;
drop policy if exists home_sessions_auth_read on home_sessions;
create policy home_sessions_auth_read on home_sessions for select to authenticated using (true);
drop policy if exists home_sessions_auth_write on home_sessions;
create policy home_sessions_auth_write on home_sessions for all to authenticated using (true) with check (true);
