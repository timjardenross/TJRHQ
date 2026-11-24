-- DRAFT, NOT APPLIED. Do not run without Captain approval (USS-TJR conversion-integration-2kq).
-- Read-only snapshot of clustered/tiered incidents for the HQ Workbench (lcars-portal: Intelligence page, Home Needs You, Decisions inbox).
-- Written by tools/intelligence/publish_incident_snapshot.py (dry-run by default); read by lcars-portal/src/lib/incidents.ts behind INCIDENT_VIEW_V1.
-- incident_key = 'inc-' + sha1(earliest report id | its subject)[:10] (tiered_brief.incident_id): the same key the Telegram alert payload carries (one incident = one entry).
-- Rollback: drop table intelligence_incident_snapshots;

create table if not exists public.intelligence_incident_snapshots (
    incident_key       text primary key,
    headline           text not null,
    tier               text not null check (tier in ('IMMEDIATE_ALERT','SCHEDULED_BRIEF','MONITOR','CONTEXT','REFERENCE_RETAIN')),
    restoration_status text not null,
    n_reports          integer not null,
    why                text not null,
    reports            jsonb not null default '[]',      -- [{relation, event_id, title, published_at, restoration}]
    material_exception boolean not null default false,
    snapshot_at        timestamptz not null,
    last_report_at     timestamptz
);
create index if not exists intelligence_incident_snapshots_snapshot_at on public.intelligence_incident_snapshots (snapshot_at desc);
alter table public.intelligence_incident_snapshots enable row level security;
create policy "authenticated read incident snapshots" on public.intelligence_incident_snapshots for select to authenticated using (true);
