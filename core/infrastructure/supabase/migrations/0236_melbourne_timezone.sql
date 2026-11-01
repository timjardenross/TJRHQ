-- 0236: move the capacity "today" boundary from Brisbane to Melbourne time.
--
-- STATUS: NOT APPLIED. Written on branch claude/melbourne-timezone; apply only
-- after the matching code change is merged and deployed (see "Cutover" below).
--
-- Why: the platform's local time zone is now Australia/Melbourne (owner decision,
-- 2026-10-18). Brisbane has no daylight saving; Melbourne does (AEDT, UTC+11, from
-- 2026-10-04 to 2027-04-04). Until this migration is applied, the database
-- default for log_date and the capacity_checkins_today view still roll the day
-- over at 23:00 Melbourne time during daylight saving.
--
-- What changes (new rows / live views only):
--   * capacity_checkins.log_date default       -> Melbourne calendar date
--   * view capacity_checkins_today             -> "today" is the Melbourne date
--     (same columns, same order, same grants as migration 0169; only the zone differs)
--
-- What does NOT change:
--   * debrief_logs.log_date. Migration 0206 says its default is Brisbane, but the
--     live default is CURRENT_DATE (checked read-only against the live catalog on
--     2026-10-18). Left as is; the repo and the live database disagree there.
--   * Existing rows. Historical log_date values were computed in Brisbane time and
--     are left as recorded. Rows captured between 00:00 and 01:00 Melbourne time
--     during daylight saving may carry the previous calendar date.
--   * recovery_pulses and its views (recovery_confidence_today,
--     recovery_pulse_adherence_7d). That domain was retired in 0181; nothing writes
--     to it. Their remaining readers are tracked in the pain-consolidation plan.
--
-- Checked against the live catalog (2026-10-18, schema only): the live
-- capacity_checkins_today view has 7 Brisbane references and the same 12 columns
-- in the same order as migration 0169, and capacity_checkins.log_date defaults to
-- the Brisbane date, so this replaces exactly what 0169 and 0148 created.
--
-- Cutover: deploy the code first, then apply this. Between the two, bots that set
-- log_date explicitly already use Melbourne; only rows that rely on the database
-- default (and the view) lag by up to one hour each night.
--
-- Rollback: re-run with 'Australia/Brisbane' in place of 'Australia/Melbourne'.
-- Idempotent: ALTER ... SET DEFAULT and CREATE OR REPLACE VIEW.

alter table public.capacity_checkins
  alter column log_date set default (now() at time zone 'Australia/Melbourne')::date;

create or replace view public.capacity_checkins_today as
select
  (now() at time zone 'Australia/Melbourne')::date as assessment_date,
  count(*) filter (where checkin_type = 'capacity')::integer as checkins_today,
  (count(*) filter (where checkin_type = 'capacity') > 0) as has_checked_in,
  case count(*) filter (where checkin_type = 'capacity')
    when 0 then 'No check-in today'
    when 1 then '1 check-in today'
    else count(*) filter (where checkin_type = 'capacity') || ' check-ins today'
  end as checkin_label,
  max(captured_at) filter (where checkin_type = 'capacity') as last_checkin_at,
  (select c2.capacity_state from public.capacity_checkins c2
     where c2.log_date = (now() at time zone 'Australia/Melbourne')::date
       and c2.checkin_type = 'capacity' and c2.capacity_state is not null
     order by c2.captured_at desc limit 1) as latest_capacity_state,
  (select c2.regulation_state from public.capacity_checkins c2
     where c2.log_date = (now() at time zone 'Australia/Melbourne')::date
       and c2.checkin_type = 'capacity' and c2.regulation_state is not null
     order by c2.captured_at desc limit 1) as latest_regulation_state,
  (select c2.pain_score from public.capacity_checkins c2
     where c2.log_date = (now() at time zone 'Australia/Melbourne')::date
       and c2.checkin_type = 'capacity' and c2.pain_score is not null
     order by c2.captured_at desc limit 1) as latest_pain_score,
  (select c2.executive_function from public.capacity_checkins c2
     where c2.log_date = (now() at time zone 'Australia/Melbourne')::date
       and c2.checkin_type = 'capacity' and c2.executive_function is not null
     order by c2.captured_at desc limit 1) as latest_executive_function,
  (count(*) filter (where checkin_type = 'midday') > 0) as has_midday_checkin,
  max(captured_at) filter (where checkin_type = 'midday') as last_midday_checkin_at,
  (select c2.capacity_state from public.capacity_checkins c2
     where c2.log_date = (now() at time zone 'Australia/Melbourne')::date
       and c2.checkin_type = 'midday' and c2.capacity_state is not null
     order by c2.captured_at desc limit 1) as latest_midday_capacity_state
from public.capacity_checkins
where log_date = (now() at time zone 'Australia/Melbourne')::date;

grant select on public.capacity_checkins_today to xo_bot, authenticated;
