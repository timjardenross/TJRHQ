-- 0188_domain_registry_intraday_media_collection.sql
-- Same FK-409 class as migration 0171 — a new scheduler job
-- (intraday_media_collection, added 2026-09-06 as part of the OSINT
-- Ingestion Quality & Relevance Mission's gap-closure for ABC News's
-- 25-item RSS feed window scrolling off between the once-daily 06:00
-- sweep) writes heartbeats against a domain_key not yet in
-- domain_registry, which 409s on the FK (migration 0071) every time.

insert into domain_registry (domain_key, display_name, category, expected_cadence_minutes, grace_period_minutes, notes) values
  ('intraday_media_collection', 'Intraday Media Collection', 'job', 90, 30, 'intelligence/scheduler.py, interval INTRADAY_MEDIA_INTERVAL_MINUTES (default 90min) — added 2026-09-06 to close a real coverage gap (ABC News general RSS feed only carries ~25 items/fetch, once-daily 06:00 sweep alone missed stories that scrolled off between fetches)')
on conflict (domain_key) do nothing;
