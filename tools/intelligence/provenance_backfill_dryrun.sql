-- provenance_backfill_dryrun.sql -- SELECT-ONLY. Safe to run on production at any time; changes nothing.
-- Shows what provenance_backfill_ACTIVATION.sql would label each existing intelligence_events row, and what
-- freshness state the reader (intelligence/event_detection.py report_freshness) would then assign.
--
-- The labelling CASE below is IDENTICAL to the one in the activation backfill (keep them in sync; a test asserts it).
-- It runs with or without the migration applied (it reads only pre-migration columns).
--
-- Q1: rows per (label, basis, confidence)            Q2: freshness state per label as of now (all rows)
-- Q3: freshness state per label, rows collected in the last 24h (what a brief would actually see)
-- Q4: 30-row audit sample (stratified, deterministic)   Q5: safety checks
--
-- Run each query by prefixing the shared CTE. Query text is kept in one file so reviewers see one rule set.

-- ---------------------------------------------------------------------------------------------------------
-- Q1  rows per assigned label
-- ---------------------------------------------------------------------------------------------------------
WITH l AS (
  SELECT e.event_id, e.published_at, e.collected_at, r.source_name,
    CASE
      WHEN e.published_at IS NULL                                                      THEN 'R1_no_published_at'
      WHEN e.published_at = e.collected_at                                             THEN 'R2_equals_collected'
      WHEN r.source_name ILIKE 'Google News%' OR e.canonical_url ILIKE '%news.google.com%' THEN 'R3_google_news'
      WHEN r.source_name = 'CISA Known Exploited Vulnerabilities'
           AND e.published_at = date_trunc('day', e.published_at AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' THEN 'R4_kev_dateadded'
      WHEN r.source_name IN ('AEMO Market Notices','AEMO NEMweb Market Notices')
           AND e.published_at = date_trunc('day', e.published_at AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' THEN 'R5_aemo_date_only'
      WHEN e.published_at > e.collected_at + interval '1 hour'                         THEN 'R6_future_event_time'
      ELSE 'R7_feed'
    END AS rule
  FROM intelligence_events e JOIN intelligence_source_registry r USING (source_id)
)
SELECT rule,
  CASE rule WHEN 'R1_no_published_at' THEN 'collected_fallback' WHEN 'R2_equals_collected' THEN 'collected_fallback'
            WHEN 'R3_google_news' THEN 'aggregator_claimed' WHEN 'R4_kev_dateadded' THEN 'date_only' WHEN 'R5_aemo_date_only' THEN 'date_only'
            WHEN 'R6_future_event_time' THEN 'unknown' ELSE 'feed' END AS basis,
  CASE rule WHEN 'R1_no_published_at' THEN 'unknown' WHEN 'R2_equals_collected' THEN 'unknown'
            WHEN 'R3_google_news' THEN 'claimed' WHEN 'R4_kev_dateadded' THEN 'claimed' WHEN 'R5_aemo_date_only' THEN 'claimed'
            WHEN 'R6_future_event_time' THEN 'unknown' ELSE 'feed' END AS confidence,
  CASE rule WHEN 'R4_kev_dateadded' THEN 'catalogue_addition' WHEN 'R5_aemo_date_only' THEN 'publication'
            WHEN 'R6_future_event_time' THEN 'event' ELSE NULL END AS label,
  count(*) AS rows
FROM l GROUP BY 1,2,3,4 ORDER BY 1;

-- ---------------------------------------------------------------------------------------------------------
-- Q2/Q3  freshness the READER would assign after backfill (replace the final WHERE for Q3: AND collected_at > now() - interval '24 hours')
-- Mirrors event_detection._pub_not_credible/_time_verified/_time_trusted/report_freshness.
-- ---------------------------------------------------------------------------------------------------------
WITH l AS (
  SELECT e.event_id, e.published_at, e.collected_at,
    CASE
      WHEN e.published_at IS NULL THEN 'R1' WHEN e.published_at = e.collected_at THEN 'R2'
      WHEN r.source_name ILIKE 'Google News%' OR e.canonical_url ILIKE '%news.google.com%' THEN 'R3'
      WHEN r.source_name = 'CISA Known Exploited Vulnerabilities' AND e.published_at = date_trunc('day', e.published_at AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' THEN 'R4'
      WHEN r.source_name IN ('AEMO Market Notices','AEMO NEMweb Market Notices') AND e.published_at = date_trunc('day', e.published_at AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' THEN 'R5'
      WHEN e.published_at > e.collected_at + interval '1 hour' THEN 'R6' ELSE 'R7' END AS rule
  FROM intelligence_events e JOIN intelligence_source_registry r USING (source_id)
), f AS (
  SELECT *,
    rule IN ('R1','R2','R6') AS pub_not_credible,                      -- basis unknown / collected_fallback: published_at ignored
    rule IN ('R4','R5') AS day_prec,
    rule IN ('R3','R4','R5') AS untrusted_time                          -- aggregator claim / date-only: parseable but only CLAIMED
  FROM l
), g AS (
  SELECT *, (NOT pub_not_credible AND published_at IS NOT NULL AND published_at <= collected_at + interval '1 hour') AS time_ok,
         CASE WHEN NOT pub_not_credible AND published_at IS NOT NULL AND published_at <= collected_at + interval '1 hour'
              THEN published_at ELSE collected_at END AS best_time
  FROM f
)
SELECT rule,
  CASE WHEN now() - best_time > interval '24 hours' + CASE WHEN day_prec AND time_ok THEN interval '24 hours' ELSE interval '0' END THEN 'KNOWN STALE'
       WHEN time_ok AND NOT untrusted_time THEN 'VERIFIED'
       WHEN time_ok AND untrusted_time THEN 'CLAIMED'
       ELSE 'UNKNOWN' END AS freshness,
  count(*) AS rows
FROM g
WHERE TRUE   -- Q3: AND collected_at > now() - interval '24 hours'
GROUP BY 1,2 ORDER BY 1,2;

-- ---------------------------------------------------------------------------------------------------------
-- Q4  audit sample: first 5 rows per rule by md5(event_id) (deterministic), with the proposed label.  Read these by eye.
-- ---------------------------------------------------------------------------------------------------------
-- (run Q1's CTE with: SELECT * FROM (SELECT rule, source_name, left(raw_title,90), published_at, collected_at,
--   row_number() OVER (PARTITION BY rule ORDER BY md5(event_id::text)) rn FROM ...) WHERE rn <= 5)

-- ---------------------------------------------------------------------------------------------------------
-- Q5  safety checks
-- ---------------------------------------------------------------------------------------------------------
-- unique index on dedup_hash present:   SELECT indexname FROM pg_indexes WHERE tablename='intelligence_events' AND indexdef ILIKE '%UNIQUE%dedup_hash%';
-- no column-name conflicts:             SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='intelligence_events'
--                                          AND column_name IN ('publisher_domain','publisher_family','published_at_basis','published_at_precision','published_at_confidence','published_at_label','event_window_start','event_window_end');  -- expect 0 rows pre-migration
