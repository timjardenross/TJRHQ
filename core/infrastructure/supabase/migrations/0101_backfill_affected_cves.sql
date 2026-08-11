-- Migration 0101: backfill affected_cves from existing title/summary text
--
-- affected_cves (added by TECHNICAL_OSINT_WORKBENCH.md's schema section,
-- migration 0095) was schema-only — no extraction pipeline populated it.
-- classifier.py now extracts real CVE IDs going forward (extract_cves());
-- this backfills the 829 pre-existing events that already mention one.
--
-- Note: m[1], not m[0] — Postgres arrays are 1-indexed. An earlier attempt
-- at this backfill used m[0] and silently wrote arrays of NULL; caught by
-- checking the result before considering this done, not by trusting the
-- UPDATE's success alone.

UPDATE intelligence_events ie
SET affected_cves = sub.cves
FROM (
  SELECT event_id,
    array(
      SELECT DISTINCT upper(m[1])
      FROM regexp_matches(raw_title || ' ' || coalesce(raw_summary, ''), 'CVE-\d{4}-\d{4,7}', 'gi') AS m
    ) AS cves
  FROM intelligence_events
  WHERE raw_title ~* 'CVE-\d{4}-\d{4,7}' OR raw_summary ~* 'CVE-\d{4}-\d{4,7}'
) sub
WHERE ie.event_id = sub.event_id AND array_length(sub.cves, 1) > 0;

-- Verify: SELECT count(*), avg(array_length(affected_cves,1)) FROM intelligence_events WHERE affected_cves IS NOT NULL;
-- Expected as of 2026-08-08: 829 events, avg ~1.07 CVEs/event, max 14.
