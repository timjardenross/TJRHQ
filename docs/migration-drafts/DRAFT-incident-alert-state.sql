-- DRAFT, NOT APPLIED. Do not run without Captain approval (USS-TJR conversion-integration-2kq, PR on claude/clustering-tiers-2kq).
-- Durable state for intelligence/alert_dispatcher.py (default OFF). The in-memory store used in tests and dry-run mirrors these columns.
-- Rollback: drop table incident_alert_sends; drop table incident_alert_state;
-- Number is deliberately not assigned: take the next free one in core/infrastructure/supabase/migrations/ when approved.

create table if not exists public.incident_alert_state (
    incident_key        text primary key,                       -- 'inc-' + sha1(earliest report id | its subject)[:10] (tiered_brief.incident_id)
    headline            text not null,
    event_ids           uuid[] not null default '{}',           -- every report id seen for the incident; any overlap = same incident
    alerted_at          timestamptz,                            -- set only by a REAL send
    restoration_sent_at timestamptz,                            -- set only by a REAL send
    dry_alerted_at      timestamptz,                            -- dry-run rehearsal, never consumes the real "once"
    dry_restoration_at  timestamptz,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);
create index if not exists incident_alert_state_event_ids_gin on public.incident_alert_state using gin (event_ids);

create table if not exists public.incident_alert_sends (          -- rate-limit ledger (sends per rolling window)
    id            bigserial primary key,
    incident_key  text not null references public.incident_alert_state(incident_key) on delete cascade,
    kind          text not null check (kind in ('alert','restoration')),
    mode          text not null check (mode in ('real','dry')),
    sent_at       timestamptz not null default now()
);
create index if not exists incident_alert_sends_sent_at on public.incident_alert_sends (mode, sent_at desc);

alter table public.incident_alert_state enable row level security;   -- service role only; no policies = no anon/auth access
alter table public.incident_alert_sends enable row level security;
