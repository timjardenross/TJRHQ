-- 0150_capacity_checkins_recovery_integration.sql
--
-- Wires capacity_checkins (0148, MY CAPACITY TODAY) into the recovery-scoring
-- chain that recovery_pulses/recovery_confidence_today used to feed, closing
-- the gap where the Telegram bot switched models but every LCARS Portal /
-- Command Centre reader kept reading the abandoned table.
--
-- Extend, don't replace: analytics_health_daily, recovery_pulses,
-- recovery_confidence_today, recovery_pulse_adherence_7d are all left
-- exactly as-is (historical, read-only) — nothing here drops or rewrites
-- them. compute_recovery_score() gains a capacity_checkins-preferring
-- branch that falls back to its existing analytics_health_daily logic
-- verbatim whenever no check-in exists for the date, so every historical
-- date scores exactly as it did before this migration.

-- ── New view: capacity_checkins_today ────────────────────────────────────────
-- Replaces recovery_confidence_today's role for app code. Deliberately does
-- NOT reproduce its 3-slot morning/midday/evening "confidence %" — that
-- concept has no equivalent under MY CAPACITY TODAY's spec ("allow more than
-- one check-in per day, do not overwrite"), so a raw count + latest reading
-- is the honest replacement, not a fabricated percentage.
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
     order by c2.captured_at desc limit 1) as latest_executive_function
from public.capacity_checkins
where log_date = (now() at time zone 'Australia/Brisbane')::date;

grant select on public.capacity_checkins_today to xo_bot, authenticated;

-- ── compute_recovery_score: prefer a real capacity_checkins row ─────────────
-- When today's (or p_date's) capacity_checkins has a row, its capacity_state
-- IS the signal (per the bot's own capacity_zone_from_checkin() philosophy —
-- no weighted formula, the Captain's own report wins), so it replaces
-- v_capacity_score and v_energy_score's inputs and, since regulation_state is
-- a direct real-time NS reading, v_ns_score's input too. Sleep and
-- life-participation are untouched — capacity_checkins doesn't track them
-- (spec §13, deliberately not built yet) so analytics_health_daily remains
-- the only source for those two components regardless of which capacity
-- source wins. When no capacity_checkins row exists for the date, every
-- branch below falls through to the exact pre-migration logic.
create or replace function public.compute_recovery_score(p_date date default current_date)
returns numeric
language plpgsql
stable
as $function$
declare
  r                analytics_health_daily%rowtype;
  cc               record;
  v_sleep_base     numeric;
  v_sleep_qual     numeric;
  v_cpap_bonus     numeric;
  v_sleep_score    numeric;
  v_ns_score       numeric;
  v_ns_modifier    numeric;
  v_energy_score   numeric;
  v_capacity_score numeric;
  v_lp_score       numeric;
  v_raw_score      numeric;
  v_final_score    numeric;
  v_ns_state       text;
begin
  select * into r from analytics_health_daily where log_date = p_date limit 1;

  select capacity_state, regulation_state, pain_score
    into cc
    from public.capacity_checkins
    where log_date = p_date and checkin_type = 'capacity'
    order by captured_at desc
    limit 1;

  if r.log_date is null and cc.capacity_state is null and cc.regulation_state is null then
    return null;
  end if;

  v_sleep_base := least(coalesce(r.sleep_hours, 0) / 7.5, 1.0) * 60;

  v_sleep_qual := case lower(coalesce(r.sleep_quality, ''))
    when 'good' then 30
    when 'fair' then 15
    else 0
  end;

  v_cpap_bonus := 0;
  if r.cpap_hours is not null and r.sleep_hours is not null and r.sleep_hours > 0 then
    if r.cpap_hours >= r.sleep_hours * 0.9 then
      v_cpap_bonus := 10;
    end if;
  elsif lower(coalesce(r.cpap_status, '')) = 'yes' then
    v_cpap_bonus := 7;
  end if;

  v_sleep_score := least(v_sleep_base + v_sleep_qual + v_cpap_bonus, 100);

  -- NS score: capacity_checkins.regulation_state is a direct real-time
  -- reading (settled/manageable -> calm-equivalent, activated -> activated,
  -- overloaded -> dysregulated) and takes priority over the (likely stale)
  -- analytics_health_daily.nervous_system_state for the same date.
  v_ns_state := case cc.regulation_state
    when 'settled' then 'calm'
    when 'manageable' then 'calm'
    when 'activated' then 'activated'
    when 'overloaded' then 'dysregulated'
    else r.nervous_system_state
  end;

  v_ns_score := case v_ns_state
    when 'calm' then 90
    when 'activated' then 55
    when 'dysregulated' then 20
    else 60
  end;

  v_ns_modifier := case v_ns_state
    when 'dysregulated' then 0.85
    when 'activated' then 0.95
    else 1.00
  end;

  if cc.capacity_state is not null then
    -- No separate "energy" signal exists in the new model — capacity_state
    -- is the closest available proxy for both capacity and energy, same
    -- nominal scale core/health/capacity_score.py's capacity_zone_from_checkin()
    -- already uses (green=90/orange=60/red=25) for the energy side, and the
    -- slightly-higher 85/55/20 already used elsewhere in this function for
    -- the capacity side, kept for continuity with the pre-existing scale.
    v_energy_score := case cc.capacity_state
      when 'green' then 90 when 'orange' then 60 when 'red' then 25 else 55 end;
    v_capacity_score := case cc.capacity_state
      when 'green' then 85 when 'orange' then 55 when 'red' then 20 else 50 end;
  else
    v_energy_score := case initcap(coalesce(r.energy, ''))
      when 'High' then 90
      when 'Moderate' then 60
      when 'Low' then 25
      else 50
    end;

    if r.captain_capacity_rating is not null then
      v_capacity_score := case r.captain_capacity_rating
        when 'Green' then 85
        when 'Amber' then 55
        when 'Red' then 20
        else 50
      end;
    else
      v_capacity_score := case r.pulse_readiness
        when 'high' then 85
        when 'moderate' then 55
        when 'low' then 20
        else 50
      end;
    end if;
  end if;

  v_lp_score := compute_life_participation(
    r.movement_notes,
    r.pleasure_creativity_marker,
    r.what_happened,
    r.sitting_tolerance_minutes,
    r.workload_constraint,
    r.pulse_day_win
  );

  v_raw_score := (v_sleep_score    * 0.25)
               + (v_ns_score       * 0.20)
               + (v_energy_score   * 0.20)
               + (v_capacity_score * 0.20)
               + (v_lp_score       * 0.15);

  -- Pain penalty: capacity_checkins.pain_score is a direct 0-10 report the
  -- pre-migration formula had no equivalent input for (analytics_health_daily
  -- already has its own pain_score, folded in via r elsewhere in the wider
  -- posture chain, not here) — a modest additional modifier, capped so a
  -- single elevated pain reading can't zero the score outright.
  if cc.pain_score is not null then
    v_ns_modifier := greatest(v_ns_modifier - least(cc.pain_score::numeric / 40, 0.15), 0.70);
  end if;

  v_final_score := least(greatest(v_raw_score * v_ns_modifier, 0), 100);

  return round(v_final_score, 2);
end;
$function$;
