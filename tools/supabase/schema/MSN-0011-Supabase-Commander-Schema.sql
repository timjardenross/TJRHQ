-- USS-TJR-MSN-0011: Slack <-> Supabase Commander Integration schema contract.
-- Apply manually in Supabase SQL editor or convert into a migration when ready.

create extension if not exists pgcrypto;

create table if not exists commander_events (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),
  source text not null,
  channel_id text,
  user_id text,
  thread_ts text,
  message_ts text,
  message_text text not null,
  route text,
  confidence numeric,
  event_type text,
  status text default 'received',
  metadata jsonb default '{}'::jsonb
);

create table if not exists commander_decisions (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),
  decision_title text not null,
  decision_summary text not null,
  source text default 'slack',
  channel_id text,
  user_id text,
  thread_ts text,
  message_ts text,
  route text,
  confidence numeric,
  status text default 'draft',
  metadata jsonb default '{}'::jsonb
);

create table if not exists commander_mission_candidates (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),
  mission_title text not null,
  mission_summary text not null,
  source text default 'slack',
  channel_id text,
  user_id text,
  thread_ts text,
  message_ts text,
  route text,
  confidence numeric,
  status text default 'candidate',
  metadata jsonb default '{}'::jsonb
);

create table if not exists commander_memory_events (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),
  memory_text text not null,
  source text default 'slack',
  channel_id text,
  user_id text,
  thread_ts text,
  message_ts text,
  route text,
  confidence numeric,
  tags text[] default '{}',
  metadata jsonb default '{}'::jsonb
);

create index if not exists idx_commander_events_created_at on commander_events (created_at desc);
create index if not exists idx_commander_decisions_created_at on commander_decisions (created_at desc);
create index if not exists idx_commander_mission_candidates_created_at on commander_mission_candidates (created_at desc);
create index if not exists idx_commander_memory_events_created_at on commander_memory_events (created_at desc);
