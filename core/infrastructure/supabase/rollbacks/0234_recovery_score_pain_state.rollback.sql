-- ROLLBACK for migration 0234_recovery_score_pain_state.sql
--
-- This is the EXACT live definition of public.compute_recovery_score(date) as
-- read from the live USSTJR project (pg_get_functiondef) immediately before
-- 0234 was prepared (2026-10-14). Applying this file restores the pre-0234
-- numeric-pain behaviour. No table, column or row is touched either way.
--
-- Exact rollback command (any of):
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f core/infrastructure/supabase/rollbacks/0234_recovery_score_pain_state.rollback.sql
--   or the Supabase SQL editor / apply_migration with this file's contents.
-- Verify afterwards:
--   select md5(pg_get_functiondef('public.compute_recovery_score(date)'::regprocedure));
--   -- must equal the md5 recorded in 0234's header comment (pre-change md5).

CREATE OR REPLACE FUNCTION public.compute_recovery_score(p_date date DEFAULT CURRENT_DATE)
 RETURNS numeric
 LANGUAGE plpgsql
 STABLE
 SET search_path TO 'public'
AS $function$
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

  if cc.pain_score is not null then
    v_ns_modifier := greatest(v_ns_modifier - least(cc.pain_score::numeric / 40, 0.15), 0.70);
  end if;

  v_final_score := least(greatest(v_raw_score * v_ns_modifier, 0), 100);

  return round(v_final_score, 2);
end;
$function$;
