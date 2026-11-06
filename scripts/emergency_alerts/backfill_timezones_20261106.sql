-- backfill_timezones_20261106.sql  --  RECORD of a one-off production data fix (already run 2026-11-06).
-- Not a migration: it changes rows, not schema. Kept so the correction is reviewable and reversible.
--
-- Why: until PR #591 deployed (~09:35 UTC on 2026-11-06), act_esa and vic_emergency incidents and tas_fire stored
-- LOCAL time as if it were UTC (about +11 h; measured: stored time ahead of the time we first saw the row).
-- Active rows self-corrected on their next run; rows already expired kept the wrong values. NSW is genuinely UTC
-- and vic_emergency warnings carry offsets, so neither was touched.
--
-- Safety: every row changed was first copied into alerts_tz_backfill_backup_20261106 (4,028 rows), so the old
-- values can be restored. The table is safe to drop once the correction is accepted.
-- Reverse for one source, e.g.:
--   update alerts a set issued_at=b.issued_at, updated_at_src=b.updated_at_src, expiry=b.expiry
--   from alerts_tz_backfill_backup_20261106 b where a.id=b.id and a.source_key='act_esa';
--
-- Verified after: VIC incidents 0 of 3,485 rows issued after last seen (was 3,477), average issued-minus-first-seen
-- -0.31 h (was +10.9 h); ACT 0 of 527 ahead; TAS 0 of 1 ahead.

begin;
create table if not exists alerts_tz_backfill_backup_20261106 (like alerts including defaults);
alter table alerts_tz_backfill_backup_20261106 enable row level security;

insert into alerts_tz_backfill_backup_20261106
select * from alerts
where last_seen_at < '2026-11-06 09:35:00+00'
  and ((source_key='vic_emergency' and event_key not like 'warning-%') or source_key in ('act_esa','tas_fire'));

-- Reading the stored digits as local wall-clock time, then converting to the true instant. The zone database
-- applies the right offset for each row's own date (AEST before 2026-10-04, AEDT after).
update alerts set
  issued_at = (issued_at at time zone 'UTC') at time zone 'Australia/Melbourne',
  updated_at_src = (updated_at_src at time zone 'UTC') at time zone 'Australia/Melbourne',
  expiry = (expiry at time zone 'UTC') at time zone 'Australia/Melbourne'
where source_key='vic_emergency' and event_key not like 'warning-%' and last_seen_at < '2026-11-06 09:35:00+00';

update alerts set
  issued_at = (issued_at at time zone 'UTC') at time zone 'Australia/Sydney',
  updated_at_src = (updated_at_src at time zone 'UTC') at time zone 'Australia/Sydney',
  expiry = (expiry at time zone 'UTC') at time zone 'Australia/Sydney'
where source_key='act_esa' and last_seen_at < '2026-11-06 09:35:00+00';

update alerts set
  issued_at = (issued_at at time zone 'UTC') at time zone 'Australia/Hobart',
  updated_at_src = (updated_at_src at time zone 'UTC') at time zone 'Australia/Hobart',
  expiry = (expiry at time zone 'UTC') at time zone 'Australia/Hobart'
where source_key='tas_fire' and last_seen_at < '2026-11-06 09:35:00+00';
commit;

-- BOM rows (15) whose "Issued at H:MM am/pm Day, D Month YYYY." line had no timezone (NSW/ACT/VIC/SA/TAS), left NULL
-- by the old adapter. Read as the state's local time; each result was checked against the row's RSS pubDate
-- (updated_at_src) and only kept if within 30 minutes (all 15 were 0-1 minute before it, in both DST seasons).
begin;
create temp table _bom_fix on commit drop as
with parsed as (
  select id, updated_at_src,
    case source_key when 'bom_act' then 'Australia/Sydney' when 'bom_nsw' then 'Australia/Sydney'
      when 'bom_vic' then 'Australia/Melbourne' when 'bom_sa' then 'Australia/Adelaide' when 'bom_tas' then 'Australia/Hobart' end tz,
    regexp_match(raw_text, 'Issued at (\d{1,2}:\d{2} [ap]m) \w+, (\d{1,2} \w+ \d{4})') m
  from alerts where source_key in ('bom_act','bom_nsw','bom_vic','bom_sa','bom_tas') and issued_at is null
)
select id, ((to_timestamp(m[2] || ' ' || m[1], 'FMDD FMMonth YYYY FMHH12:MI am')::timestamp) at time zone tz) as issued_calc, updated_at_src
from parsed where m is not null;
delete from _bom_fix where abs(extract(epoch from (updated_at_src - issued_calc))) > 1800;
insert into alerts_tz_backfill_backup_20261106 select a.* from alerts a join _bom_fix f on f.id = a.id;
update alerts a set issued_at = f.issued_calc from _bom_fix f where a.id = f.id and a.issued_at is null;
commit;
-- The 18 remaining BOM rows with a NULL issued_at have no "Issued at" line at all (cyclone advices, flood watches, track maps): nothing to derive.
