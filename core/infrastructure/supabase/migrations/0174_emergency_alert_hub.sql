-- 0174_emergency_alert_hub.sql
--
-- Tier 1 Emergency Alert Hub (see repo-root
-- Emergency_Alert_Hub_Workbench_Mission_and_Scope.md). New workbench, own
-- dedicated schema — deliberately NOT bolted onto intelligence_source_registry
-- / intelligence_events (migration 0004): that pair is shaped for the ORI
-- resilience-brief product (banking/CPS230 relevance scoring, brief-inclusion
-- linkage, AU/APAC/GLOBAL-only jurisdiction) and has no severity/expiry/
-- active-alert lifecycle. Same discipline as 0004 and 0071 (registry + health
-- + canonical record + RLS), new tables because the shape is genuinely
-- different, not a fork of the concept — see the scope doc's §3.
--
-- Source health/crawl-run logging is NOT duplicated here — every jurisdiction
-- source registers as a domain_registry row below and reuses the existing
-- domain_heartbeats / domain_heartbeat_latest mechanism (migration 0071) and
-- the Agent/Job dashboard, same as every other scheduled job on the platform.

create table if not exists alert_sources (
  source_key                text primary key,
  jurisdiction               text not null check (jurisdiction in ('NSW','VIC','QLD','WA','SA','TAS','NT','ACT')),
  source_name                text not null,
  source_type                text not null check (source_type in ('geojson','json','atom_cap','georss','scrape')),
  base_url                   text not null,
  feed_url                   text,
  active                     boolean not null default true,
  fetch_interval_minutes     int  not null,
  notes                      text,
  created_at                 timestamptz not null default now(),
  updated_at                 timestamptz not null default now()
);

comment on table alert_sources is
  'Explicit Tier 1 allowlist for the Emergency Alert Hub, one row per official AU state/territory/national source. Editable allowlist per the source brief — enable/disable via `active`, same soft-delete convention as domain_registry.active (migrations 0112/0117).';

create table if not exists alerts (
  id               uuid primary key default gen_random_uuid(),
  source_key       text not null references alert_sources(source_key) on delete cascade,
  jurisdiction     text not null,
  alert_type       text not null default 'other' check (alert_type in (
                     'bushfire','flood','storm','cyclone','heatwave','hazard_reduction',
                     'structure_fire','other'
                   )),
  severity         text not null default 'unknown' check (severity in (
                     'emergency_warning','watch_and_act','advice','unknown'
                   )),
  headline         text not null,
  description      text,
  location         text,
  issued_at        timestamptz,
  updated_at_src   timestamptz,
  expiry           timestamptz,
  status           text not null default 'new' check (status in (
                     'new','active','updated','superseded','expired','inactive','errored'
                   )),
  is_active        boolean not null default true,
  canonical_url    text,
  raw_text         text,
  event_key        text not null,
  latitude         double precision,
  longitude        double precision,
  first_seen_at    timestamptz not null default now(),
  last_seen_at     timestamptz not null default now()
);

create unique index if not exists idx_alerts_canonical_url on alerts(canonical_url) where canonical_url is not null;
create unique index if not exists idx_alerts_event_key      on alerts(source_key, event_key);
create index if not exists idx_alerts_jurisdiction  on alerts(jurisdiction);
create index if not exists idx_alerts_is_active     on alerts(is_active);
create index if not exists idx_alerts_severity      on alerts(severity);
create index if not exists idx_alerts_last_seen_at  on alerts(last_seen_at desc);

comment on table alerts is
  'Canonical Tier 1 emergency alert record. Dedup: canonical_url first (unique, nulls allowed for sources with no per-item URL), then (source_key, event_key) — mirrors intelligence_events.dedup_hash''s dedup-by-hash approach (migration 0004) but keyed for this table''s own shape. Lifecycle per the state machine in the scope doc: new -> active -> updated -> superseded/expired -> inactive, or errored on a parse failure that could not produce a usable record.';

alter table alert_sources enable row level security;
alter table alerts        enable row level security;

drop policy if exists alert_sources_read on alert_sources;
create policy alert_sources_read on alert_sources for select using (true);
drop policy if exists alert_sources_service_write on alert_sources;
create policy alert_sources_service_write on alert_sources
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');

drop policy if exists alerts_read on alerts;
create policy alerts_read on alerts for select using (true);
drop policy if exists alerts_service_write on alerts;
create policy alerts_service_write on alerts
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');

-- Seed the Tier 1 source allowlist. feed_url is null for the 3 sources
-- confirmed (2026-08-26, live-checked) to have no public structured feed —
-- WA DFES's public incident feed (DFES-055) was decommissioned 2024-09-13
-- and its replacement (DFES-058..070) requires an access application; TAS
-- and NT's public feed existence could not be confirmed live (JS-rendered
-- pages, no feed URL discoverable via page source). Those three are
-- source_type='scrape' via the existing Firecrawl adapter
-- (intelligence/ingestion/firecrawl_client.py) rather than a fabricated
-- feed URL. The other five were fetched live 2026-08-26 and confirmed
-- returning real current data at the exact feed_url stored here.
insert into alert_sources (source_key, jurisdiction, source_name, source_type, base_url, feed_url, active, fetch_interval_minutes, notes) values
  ('nsw_rfs',    'NSW', 'NSW Rural Fire Service — Major Incidents', 'geojson',  'https://www.rfs.nsw.gov.au/fire-information/fires-near-me', 'https://www.rfs.nsw.gov.au/feeds/majorIncidents.json', true, 15,  'Confirmed live 2026-08-26 (GeoJSON FeatureCollection, properties.category = Advice/Watch and Act/Emergency Warning, updated every 30min per official page).'),
  ('vic_emergency', 'VIC', 'VicEmergency — Incidents and Warnings', 'json', 'https://emergency.vic.gov.au/respond/', 'https://data.emergency.vic.gov.au/Show?pageId=getIncidentJSON', true, 15, 'Confirmed live 2026-08-26 (results[] array, incidentStatus/category1/agency fields). EMV recommends readers refresh at least every 5 minutes.'),
  ('qld_fire',   'QLD', 'Queensland Fire Department — Bushfire Warnings', 'geojson', 'https://www.fire.qld.gov.au/Current-Incidents', 'https://publiccontent-gis-psba-qld-gov-au.s3.amazonaws.com/content/Feeds/BushfireCurrentIncidents/bushfireAlert.json', true, 30, 'Confirmed live 2026-08-26 via data.qld.gov.au resource redirect (GeoJSON, properties.WarningLevel = Advice/Watch and Act/Emergency Warning). Updated every 30min per data.qld.gov.au.'),
  ('sa_cfs',     'SA',  'SA Country Fire Service — Fire Incident Information (CAP-AU)', 'atom_cap', 'https://www.cfs.sa.gov.au/warnings-restrictions/warnings/rss-feeds/', 'https://data.eso.sa.gov.au/prod/cfs/criimson/alertsa-fire.xml', true, 15, 'Confirmed live 2026-08-26 (CAP-AU Atom feed, cap:severity/cap:urgency/cap:certainty fields present).'),
  ('act_esa',    'ACT', 'ACT Emergency Services Agency — Current Incidents', 'georss', 'https://esa.act.gov.au/be-emergency-ready/warnings-alerts', 'https://esa.act.gov.au/feeds/currentincidents.xml', true, 5, 'Confirmed live 2026-08-26 (GeoRSS, updated every 60s from CAD per official page; feed carries incidents only, not the separate news-alerts warnings stream).'),
  ('wa_dfes',    'WA',  'DFES — Emergency WA Warnings & Incidents', 'scrape', 'https://www.dfes.wa.gov.au/emergencywa/prepare', null, true, 30, 'No public feed: DFES-055 (public incident points) retired 2024-09-13; replacement DFES-058..070 datasets are access-restricted (apply via gis@dfes.wa.gov.au). Scrape via Firecrawl until/unless access is granted.'),
  ('tas_fire',   'TAS', 'TasALERT — Current Warnings and Incidents', 'scrape', 'https://alert.tas.gov.au/', null, true, 30, 'No public feed URL discoverable live 2026-08-26 (page source has no embedded API/feed reference; likely JS-rendered SPA). Scrape via Firecrawl; revisit if TFS publishes a documented feed.'),
  ('nt_securent', 'NT', 'Secure NT — Alerts and Warnings', 'scrape', 'https://securent.nt.gov.au/alerts-warnings', null, true, 30, 'No public feed URL discoverable live 2026-08-26 (pfes.nt.gov.au/newsroom/rss-feeds is general news RSS, not alerts). Scrape via Firecrawl; revisit if NT Government publishes a documented alerts feed.')
on conflict (source_key) do nothing;

-- Register each source as a domain_registry job so it gets real crawl-health
-- tracking (record_heartbeat/domain_heartbeat_latest, migration 0071) and
-- shows up on the existing Agent/Job dashboard for free — no bespoke health
-- table or UI for this workbench.
insert into domain_registry (domain_key, display_name, category, expected_cadence_minutes, grace_period_minutes, notes) values
  ('emergency_alert_nsw_rfs',    'Emergency Alert Hub — NSW RFS',    'job', 15, 30, 'intelligence/emergency_alerts.py, per-source cadence from alert_sources.fetch_interval_minutes'),
  ('emergency_alert_vic',        'Emergency Alert Hub — VicEmergency', 'job', 15, 30, 'intelligence/emergency_alerts.py'),
  ('emergency_alert_qld',        'Emergency Alert Hub — QLD Fire',   'job', 30, 60, 'intelligence/emergency_alerts.py'),
  ('emergency_alert_sa',         'Emergency Alert Hub — SA CFS',     'job', 15, 30, 'intelligence/emergency_alerts.py'),
  ('emergency_alert_act',        'Emergency Alert Hub — ACT ESA',    'job', 5,  15, 'intelligence/emergency_alerts.py'),
  ('emergency_alert_wa',         'Emergency Alert Hub — WA DFES',    'job', 30, 60, 'intelligence/emergency_alerts.py, scrape-tier (no public feed, see alert_sources.notes)'),
  ('emergency_alert_tas',        'Emergency Alert Hub — TAS Fire',   'job', 30, 60, 'intelligence/emergency_alerts.py, scrape-tier (no public feed, see alert_sources.notes)'),
  ('emergency_alert_nt',         'Emergency Alert Hub — NT SecureNT', 'job', 30, 60, 'intelligence/emergency_alerts.py, scrape-tier (no public feed, see alert_sources.notes)')
on conflict (domain_key) do nothing;
