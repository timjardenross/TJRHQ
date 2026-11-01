-- 0242_sa_cfs_feed_url.sql
--
-- The CFS CAP-AU feed moved. The URL seeded in 0174
-- (data.eso.sa.gov.au/prod/cfs/criimson/alertsa-fire.xml) now serves only a
-- "Feed Retirement Notice" and no incidents; the official CFS feeds page
-- (https://www.cfs.sa.gov.au/warnings-restrictions/warnings/rss-feeds/) lists
-- https://data.eso.sa.gov.au/feeds/prod/cap-au.xml. Same CAP-AU schema. The
-- adapter (sa_cfs.py) has its own copy of the URL, so this only keeps the
-- alert_sources record truthful. Metadata only — no schema change.

update alert_sources
set feed_url = 'https://data.eso.sa.gov.au/feeds/prod/cap-au.xml',
    notes = 'Feed moved 2026-11: old criimson/alertsa-fire.xml URL retired (serves only a Feed Retirement Notice). Official CFS CAP-AU feed per cfs.sa.gov.au RSS feeds page; same CAP-AU schema (WarningLevel parameter). adapter raises if a retirement notice is returned.',
    updated_at = now()
where source_key = 'sa_cfs';
