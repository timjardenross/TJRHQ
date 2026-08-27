-- 0176_bom_warnings.sql
--
-- Add BOM (Bureau of Meteorology) state/territory warnings as an
-- Emergency Alert Hub source — Captain asked for the national warnings
-- surface at bom.gov.au/weather-and-climate/warnings-and-alerts.
--
-- Real, confirmed live 2026-08-27: BOM publishes one plain public RSS feed
-- per state/territory at bom.gov.au/rss/, exactly matching our 8
-- jurisdictions (IDZ00054-60, IDZ00085 for ACT). This is BOM's
-- flood/severe-weather/cyclone coverage — complements the fire-agency
-- feeds already wired (RFS/CFS/DFES/etc), not a duplicate of them.
--
-- Widening alert_type: BOM's own feed description text lists categories
-- this hub doesn't have an enum value for yet (tsunami, severe weather/
-- severe thunderstorm) — added rather than folding them into an existing
-- value that would misrepresent them.

alter table alerts drop constraint if exists alerts_alert_type_check;
alter table alerts add constraint alerts_alert_type_check check (alert_type in (
  'bushfire','flood','storm','cyclone','heatwave','hazard_reduction',
  'structure_fire','severe_weather','tsunami','other'
));

insert into alert_sources (source_key, jurisdiction, source_name, source_type, base_url, feed_url, active, fetch_interval_minutes, notes) values
  ('bom_nsw', 'NSW', 'Bureau of Meteorology — NSW/ACT Warnings', 'georss', 'https://www.bom.gov.au/nsw/warnings/index.shtml', 'https://www.bom.gov.au/fwo/IDZ00054.warnings_nsw.xml', true, 15, 'Confirmed live 2026-08-27. No severity/lat-lon fields in this feed — title/link/pubDate/guid only; severity stays unknown by design, see bom_warnings.py.'),
  ('bom_nt',  'NT',  'Bureau of Meteorology — NT Warnings',     'georss', 'https://www.bom.gov.au/nt/warnings/index.shtml',  'https://www.bom.gov.au/fwo/IDZ00055.warnings_nt.xml',  true, 15, 'Confirmed live 2026-08-27, same shape as bom_nsw.'),
  ('bom_qld', 'QLD', 'Bureau of Meteorology — QLD Warnings',    'georss', 'https://www.bom.gov.au/qld/warnings/index.shtml', 'https://www.bom.gov.au/fwo/IDZ00056.warnings_qld.xml', true, 15, 'Confirmed live 2026-08-27, same shape as bom_nsw.'),
  ('bom_sa',  'SA',  'Bureau of Meteorology — SA Warnings',     'georss', 'https://www.bom.gov.au/sa/warnings/index.shtml',  'https://www.bom.gov.au/fwo/IDZ00057.warnings_sa.xml',  true, 15, 'Confirmed live 2026-08-27, same shape as bom_nsw.'),
  ('bom_tas', 'TAS', 'Bureau of Meteorology — TAS Warnings',    'georss', 'https://www.bom.gov.au/tas/warnings/index.shtml', 'https://www.bom.gov.au/fwo/IDZ00058.warnings_tas.xml', true, 15, 'Confirmed live 2026-08-27, same shape as bom_nsw.'),
  ('bom_vic', 'VIC', 'Bureau of Meteorology — VIC Warnings',    'georss', 'https://www.bom.gov.au/vic/warnings/index.shtml', 'https://www.bom.gov.au/fwo/IDZ00059.warnings_vic.xml', true, 15, 'Confirmed live 2026-08-27, same shape as bom_nsw.'),
  ('bom_wa',  'WA',  'Bureau of Meteorology — WA Warnings',     'georss', 'https://www.bom.gov.au/wa/warnings/index.shtml',  'https://www.bom.gov.au/fwo/IDZ00060.warnings_wa.xml',  true, 15, 'Confirmed live 2026-08-27, same shape as bom_nsw.'),
  ('bom_act', 'ACT', 'Bureau of Meteorology — ACT Warnings',    'georss', 'https://www.bom.gov.au/act/warnings/index.shtml', 'https://www.bom.gov.au/fwo/IDZ00085.warnings_act.xml', true, 15, 'Confirmed live 2026-08-27, same shape as bom_nsw.')
on conflict (source_key) do nothing;

insert into domain_registry (domain_key, display_name, category, expected_cadence_minutes, grace_period_minutes, notes) values
  ('emergency_alert_bom_nsw', 'Emergency Alert Hub — BOM NSW/ACT', 'job', 15, 30, 'intelligence/emergency_alerts.py'),
  ('emergency_alert_bom_nt',  'Emergency Alert Hub — BOM NT',      'job', 15, 30, 'intelligence/emergency_alerts.py'),
  ('emergency_alert_bom_qld', 'Emergency Alert Hub — BOM QLD',     'job', 15, 30, 'intelligence/emergency_alerts.py'),
  ('emergency_alert_bom_sa',  'Emergency Alert Hub — BOM SA',      'job', 15, 30, 'intelligence/emergency_alerts.py'),
  ('emergency_alert_bom_tas', 'Emergency Alert Hub — BOM TAS',     'job', 15, 30, 'intelligence/emergency_alerts.py'),
  ('emergency_alert_bom_vic', 'Emergency Alert Hub — BOM VIC',     'job', 15, 30, 'intelligence/emergency_alerts.py'),
  ('emergency_alert_bom_wa',  'Emergency Alert Hub — BOM WA',      'job', 15, 30, 'intelligence/emergency_alerts.py'),
  ('emergency_alert_bom_act', 'Emergency Alert Hub — BOM ACT',     'job', 15, 30, 'intelligence/emergency_alerts.py')
on conflict (domain_key) do nothing;
