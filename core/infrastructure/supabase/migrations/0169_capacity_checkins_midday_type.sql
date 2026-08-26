-- 0169_capacity_checkins_midday_type.sql
--
-- MY CAPACITY TODAY gains a proactive 08:00/13:00/20:00 cadence
-- (telegram-bots/capacitybot/app.py) replacing the previous 100%
-- command-driven bot. The 13:00 push is a deliberately lighter 2-tap
-- midday micro check-in (capacity_state + unexpected_change only) rather
-- than the full 9-question flow — a new checkin_type is the honest way to
-- keep it structurally distinct from a real morning/anytime capacity
-- reading, so downstream "latest capacity_state" readers (capacity_score.py,
-- daily_ops_cycle.py, follow_through_engine.py, compute_recovery_score(),
-- capacity_checkins_today) are NOT touched here — they all filter on
-- checkin_type='capacity' explicitly (0148/0150), so a 'midday' row is
-- invisible to them by construction, not by omission.

alter table public.capacity_checkins
  drop constraint if exists capacity_checkins_checkin_type_check;

alter table public.capacity_checkins
  add constraint capacity_checkins_checkin_type_check
  check (checkin_type in ('capacity', 'evening', 'midday'));

-- capacity_checkins_today view: surface the midday pulse alongside the
-- existing capacity/evening counts so the LCARS workbench can show
-- "midday check-in done" without a second query. Deliberately not folded
-- into checkins_today/has_checked_in/checkin_label above (0150) — those
-- three remain the "did today's REAL capacity check-in happen" signal;
-- midday is informational, not a substitute for it.
-- Postgres CREATE OR REPLACE VIEW cannot reorder or insert columns among
-- existing ones (only append) — new midday_* columns go at the end.
create or replace view public.capacity_checkins_today as
select
  (now() at time zone 'Australia/Brisbane')::date as assessment_date,
  count(*) filter (where checkin_type = 'capacity')::integer as checkins_today,
  (count(*) filter (where checkin_type = 'capacity') > 0) as has_checked_in,
  case count(*) filter (where checkin_type = 'capacity')
    when 0 then 'No check-in today'
    when 1 then '1 check-in today'
    else count(*) filter (where checkin_type = 'capacity') || ' check-ins today'
  end as checkin_label,
  max(captured_at) filter (where checkin_type = 'capacity') as last_checkin_at,
  (select c2.capacity_state from public.capacity_checkins c2
     where c2.log_date = (now() at time zone 'Australia/Brisbane')::date
       and c2.checkin_type = 'capacity' and c2.capacity_state is not null
     order by c2.captured_at desc limit 1) as latest_capacity_state,
  (select c2.regulation_state from public.capacity_checkins c2
     where c2.log_date = (now() at time zone 'Australia/Brisbane')::date
       and c2.checkin_type = 'capacity' and c2.regulation_state is not null
     order by c2.captured_at desc limit 1) as latest_regulation_state,
  (select c2.pain_score from public.capacity_checkins c2
     where c2.log_date = (now() at time zone 'Australia/Brisbane')::date
       and c2.checkin_type = 'capacity' and c2.pain_score is not null
     order by c2.captured_at desc limit 1) as latest_pain_score,
  (select c2.executive_function from public.capacity_checkins c2
     where c2.log_date = (now() at time zone 'Australia/Brisbane')::date
       and c2.checkin_type = 'capacity' and c2.executive_function is not null
     order by c2.captured_at desc limit 1) as latest_executive_function,
  (count(*) filter (where checkin_type = 'midday') > 0) as has_midday_checkin,
  max(captured_at) filter (where checkin_type = 'midday') as last_midday_checkin_at,
  (select c2.capacity_state from public.capacity_checkins c2
     where c2.log_date = (now() at time zone 'Australia/Brisbane')::date
       and c2.checkin_type = 'midday' and c2.capacity_state is not null
     order by c2.captured_at desc limit 1) as latest_midday_capacity_state
from public.capacity_checkins
where log_date = (now() at time zone 'Australia/Brisbane')::date;

grant select on public.capacity_checkins_today to xo_bot, authenticated;
