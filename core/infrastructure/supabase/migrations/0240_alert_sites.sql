-- 0240_alert_sites.sql
--
-- Emergency Alert Hub: the organisation's own Australian sites (branches,
-- business centres, specialist hubs, cash hubs), so an alert can be answered
-- with "which of OUR sites does this affect?" instead of a national list.
--
-- Loaded from the internal "ANZ Site List for Automation" workbook by
-- tools/emergency_alerts/geocode_sites.py. latitude/longitude come from a
-- one-off geocode; geocode_quality records how precise that was so the
-- matcher (core/platform/site_matching.py, mirrored in
-- lcars-portal/src/lib/siteMatching.ts) never treats a suburb centroid as a
-- rooftop. priority is the workbook's own Tier 1/2/3 and drives ordering.
--
-- Internal data, so authenticated-read only (the 0239 end state) — never
-- the open `using (true)` read the original alert tables shipped with.

create table if not exists alert_sites (
  id               uuid primary key default gen_random_uuid(),
  site_type        text not null check (site_type in (
                     'Branch','Business Centre','Specialist Hub','Business Cash Hub','ANZ Home','Kiosk','Office','Other'
                   )),
  name             text not null,
  classification   text,
  address          text not null,
  suburb           text not null,
  state            text not null check (state in ('NSW','VIC','QLD','WA','SA','TAS','NT','ACT')),
  postcode         text not null check (postcode ~ '^[0-9]{4}$'),
  priority         text not null check (priority in ('Tier 1','Tier 2','Tier 3')),
  latitude         double precision,
  longitude        double precision,
  geocode_quality  text not null default 'none' check (geocode_quality in ('address','street','suburb','postcode','none')),
  geocode_source   text,
  active           boolean not null default true,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

-- (name, address, site_type) is unique in the source workbook (checked
-- 494/494); a branch and a business centre can share an address, so
-- address alone is not a key.
create unique index if not exists idx_alert_sites_identity on alert_sites(name, address, site_type);
create index if not exists idx_alert_sites_state    on alert_sites(state) where active;
create index if not exists idx_alert_sites_postcode on alert_sites(postcode) where active;

comment on table alert_sites is
  'Own-site register for the Emergency Alert Hub. geocode_quality: address > street > suburb > postcode > none. Matching treats suburb/postcode centroids as coarse, never exact.';

alter table alert_sites enable row level security;

drop policy if exists alert_sites_read on alert_sites;
create policy alert_sites_read on alert_sites for select to authenticated using (true);
drop policy if exists alert_sites_service_write on alert_sites;
create policy alert_sites_service_write on alert_sites
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
