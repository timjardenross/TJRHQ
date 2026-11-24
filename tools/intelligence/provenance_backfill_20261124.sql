-- provenance_backfill_20261124.sql -- STEP 4 of the provenance activation. *** NOT EXECUTED. Needs owner approval. ***
-- Run only AFTER: migration applied, flag on for the writer, new rows verified to carry provenance (runbook steps 1-3).
-- Pattern follows scripts/emergency_alerts/backfill_timezones_20261106.sql: backup table first, one transaction, in-transaction gate,
-- documented reverse.
--
-- What it does: for every row whose published_at_basis IS NULL (i.e. written before the flag), assign the LEAST-trusting honest label.
-- Nothing is promoted to 'verified'. published_at itself is never modified. Rules (first match wins) are identical to
-- provenance_backfill_dryrun.sql, whose counts on 2026-11-24 (45,427 rows) were:
--   R1 no published_at                        1,764 -> collected_fallback / unknown / unknown
--   R2 published_at = collected_at (exact)      294 -> collected_fallback / unknown / unknown   (Twilio 240, AEMO 54: adapter used collection time)
--   R3 Google News                              826 -> aggregator_claimed / second / claimed
--   R4 CISA KEV dateAdded (midnight UTC)        148 -> date_only / day / claimed / label catalogue_addition
--   R5 AEMO notice date-only (midnight UTC)     415 -> date_only / day / claimed / label publication
--   R6 published_at > collected_at + 1h         120 -> unknown / unknown / unknown / label event; event_window_start := published_at
--                                                      (scheduled maintenance start, e.g. Cloudflare/Zoom/Twilio; never a publication time)
--   R7 everything else                       41,860 -> feed / unknown / feed
-- Counts drift as rows arrive; the gate below compares updated rows to backed-up rows, not to these numbers.
--
-- Backfill is intentionally NOT verified: KEV dateAdded is 'claimed' here although the new writer stores 'verified' (same evidence); the
-- owner may choose to promote R4 to 'verified' (one-word change). Day-precision + verified or claimed behaves identically in the reader
-- (never hour-level evidence), so this is a labelling choice, not a behaviour one.
--
-- Reader effect on old rows (see runbook): R3 rows move VERIFIED->CLAIMED; R1/R2/R6 rows are timed by collection (UNKNOWN within 24h);
-- R4/R5 are day-precision CLAIMED. R7 unchanged (VERIFIED within 24h). Rows older than 24h are KNOWN STALE in every case.
-- ============================================================================================================

begin;
set local lock_timeout = '5s';
set local statement_timeout = '300s';

create table if not exists intelligence_events_provenance_bak_20261124 (
  event_id uuid primary key,
  rule text not null,
  backed_up_at timestamptz not null default now()
);
alter table intelligence_events_provenance_bak_20261124 enable row level security;

-- Backup + classification in one place: the table records exactly which rows this run touches and under which rule.
insert into intelligence_events_provenance_bak_20261124 (event_id, rule)
select e.event_id,
  case
    when e.published_at is null then 'R1'
    when e.published_at = e.collected_at then 'R2'
    when r.source_name ilike 'Google News%' or e.canonical_url ilike '%news.google.com%' then 'R3'
    when r.source_name = 'CISA Known Exploited Vulnerabilities'
         and e.published_at = date_trunc('day', e.published_at at time zone 'UTC') at time zone 'UTC' then 'R4'
    when r.source_name in ('AEMO Market Notices','AEMO NEMweb Market Notices')
         and e.published_at = date_trunc('day', e.published_at at time zone 'UTC') at time zone 'UTC' then 'R5'
    when e.published_at > e.collected_at + interval '1 hour' then 'R6'
    else 'R7' end
from intelligence_events e join intelligence_source_registry r using (source_id)
where e.published_at_basis is null
on conflict (event_id) do nothing;

update intelligence_events e set
  published_at_basis      = case b.rule when 'R1' then 'collected_fallback' when 'R2' then 'collected_fallback' when 'R3' then 'aggregator_claimed'
                              when 'R4' then 'date_only' when 'R5' then 'date_only' when 'R6' then 'unknown' else 'feed' end,
  published_at_precision  = case b.rule when 'R3' then 'second' when 'R4' then 'day' when 'R5' then 'day' else 'unknown' end,
  published_at_confidence = case b.rule when 'R3' then 'claimed' when 'R4' then 'claimed' when 'R5' then 'claimed' when 'R7' then 'feed' else 'unknown' end,
  published_at_label      = case b.rule when 'R4' then 'catalogue_addition' when 'R5' then 'publication' when 'R6' then 'event' else null end,
  event_window_start      = case when b.rule = 'R6' then e.published_at else e.event_window_start end
from intelligence_events_provenance_bak_20261124 b
where e.event_id = b.event_id and e.published_at_basis is null;

-- Gate: abort (rolls the whole transaction back) unless every backed-up row was labelled and nothing outside the backup was touched.
do $$
declare n_bak bigint; n_lab bigint; n_unlab_bak bigint;
begin
  select count(*) into n_bak from intelligence_events_provenance_bak_20261124;
  select count(*) into n_lab from intelligence_events e join intelligence_events_provenance_bak_20261124 b using (event_id) where e.published_at_basis is not null;
  select count(*) into n_unlab_bak from intelligence_events e join intelligence_events_provenance_bak_20261124 b using (event_id) where e.published_at_basis is null;
  if n_bak = 0 or n_lab <> n_bak or n_unlab_bak <> 0 then
    raise exception 'provenance backfill gate failed: backup=%, labelled=%, still_null=%', n_bak, n_lab, n_unlab_bak;
  end if;
  raise notice 'provenance backfill ok: % rows labelled', n_bak;
end $$;
commit;

-- Validate the constraints (scans the table once; takes SHARE UPDATE EXCLUSIVE, does not block reads/writes). Run after the commit above:
-- alter table intelligence_events validate constraint intelligence_events_pub_basis_chk;
-- alter table intelligence_events validate constraint intelligence_events_pub_precision_chk;
-- alter table intelligence_events validate constraint intelligence_events_pub_confidence_chk;
-- alter table intelligence_events validate constraint intelligence_events_pub_label_chk;

-- REVERSE (backfill only; keeps columns and any provenance the live writer stored on rows that are NOT in the backup):
--   begin;
--   update intelligence_events e set published_at_basis=null, published_at_precision=null, published_at_confidence=null, published_at_label=null,
--          event_window_start = case when b.rule='R6' then null else e.event_window_start end
--   from intelligence_events_provenance_bak_20261124 b where e.event_id=b.event_id;
--   commit;
-- The backup table is safe to drop once the backfill is accepted.
