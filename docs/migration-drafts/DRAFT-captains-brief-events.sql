-- DRAFT, NOT APPLIED. Do not run without Captain approval (USS-TJR conversion-integration-2kq).
-- Records which events each Captain's brief contained (intelligence/brief_event_links.py, flag CAPTAINS_BRIEF_RECORD_EVENTS, default OFF).
-- intelligence_events.brief_id cannot be used: it is a foreign key to intelligence_briefs, not captains_daily_briefs.
-- Rollback: drop table captains_brief_events;

create table if not exists public.captains_brief_events (
    brief_id    uuid references public.captains_daily_briefs(id) on delete cascade,   -- null if the brief row could not be resolved
    brief_type  text not null,
    event_id    uuid not null references public.intelligence_events(event_id) on delete cascade,
    recorded_at timestamptz not null default now(),
    unique (brief_id, event_id)
);
create index if not exists captains_brief_events_event on public.captains_brief_events (event_id);
alter table public.captains_brief_events enable row level security;
