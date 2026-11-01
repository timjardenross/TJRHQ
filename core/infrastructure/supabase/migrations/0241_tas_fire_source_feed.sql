-- 0241_tas_fire_source_feed.sql
--
-- TasALERT now has a real structured source (found live 2026-11-01): the
-- Tasmanian Government LIST ArcGIS "TasAlert Warnings" layer, read by
-- intelligence/ingestion/emergency_alert_adapters/tas_fire.py. The seed row
-- in 0174 said "no public feed — scrape via Firecrawl"; update it so the
-- alert_sources record matches what actually runs. Metadata only — no
-- schema change, and it never touches the 1,000/month Firecrawl budget.

update alert_sources
set source_type = 'json',
    feed_url = 'https://services.thelist.tas.gov.au/arcgis/rest/services/Public/EmergencyManagementPublic/MapServer/72/query?where=1%3D1&outFields=*&outSR=4326&f=json',
    notes = 'Found live 2026-11-01: Tasmanian Government LIST ArcGIS "TasAlert Warnings" layer (CC-BY) — point geometry, effective/expiry dates, stable IDENTIFIER. Severity mapped only where ALERT_TYPE/EVENT states an AWS tier; otherwise unknown. Planned burns dropped at source. Only a Smoke Alert was live at the time, so the full ALERT_TYPE vocabulary is unconfirmed.',
    updated_at = now()
where source_key = 'tas_fire';
