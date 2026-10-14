-- 0234_recovery_score_pain_state.sql
-- TJR HQ / Telegram R2 alignment — Phase 2 step 3 (PO-approved rule).
-- STATUS: APPLIED to the live USSTJR project on 2026-10-14 after the PO said go
-- (Supabase migration history name: recovery_score_pain_state; the function
-- text applied is identical to the body below, comments included).
-- Backup/rollback: the exact pre-change definition is saved at
-- core/infrastructure/supabase/rollbacks/0234_recovery_score_pain_state.rollback.sql.
-- Aggregate-only before/after on the 25 days that have a capacity check-in:
--   avg score 33.14 -> 36.09 (+2.95, matches the pre-apply comparison);
--   bands STRONG/STABLE/FRAGILE/REST  0/0/12/13 -> 0/4/9/12
--   (4 FRAGILE->STABLE, 1 REST->FRAGILE, as predicted);
--   capacity_checkins rows 56 / with number 29 / with state 30: unchanged;
--   post-apply function md5 = 313635a5f58ab3f6fe8f48768666c8ec; one overload;
--   get_recovery_posture(date) still returns its row.
--
-- Replaces public.compute_recovery_score(date) so the pain penalty reads
-- capacity_checkins.pain_state (low / baseline / elevated / high) instead of
-- the retired 0-10 pain_score:
--   lower or around usual  = 0
--   higher than usual      = half the 15% weight
--   much higher than usual = the full 15% weight
-- Everything else in the function is byte-for-byte the live definition
-- (sleep, nervous system, energy, capacity, life participation, 0.70 floor).
-- Same signature, same return type; the only caller (get_recovery_posture)
-- is unaffected.
--
-- Missing pain_state: no adjustment (unknown, NOT zero-pain evidence) — the
-- same behaviour the old formula had for a missing pain_score.
--
-- Additive/reversible: CREATE OR REPLACE FUNCTION only. No table, column,
-- index, view or row is created, altered or deleted; pain_score and all
-- history stay as they are (read-only history). Past dates are recomputed on
-- read with the new rule (the function is STABLE and nothing is stored).
--
-- Known, accepted effect (PO, 2026-10-14; aggregate comparison on the 25 days
-- that have a capacity check-in): the new rule scores "around usual" and
-- "lower than usual" days higher than the old formula did, and "higher than
-- usual" days about 2 points higher on average, by design; "much higher than
-- usual" days are unchanged (0.00). Re-run the comparison after about a month
-- of real pain-state data (review point, not a gate).
--
-- Pre-change fingerprint (live, 2026-10-14):
--   md5(pg_get_functiondef('public.compute_recovery_score(date)'::regprocedure))
--     = 2c933143423e51f0d8250eb2198a5121
--
-- ROLLBACK (restores the exact pre-change definition saved from live):
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--     -f core/infrastructure/supabase/rollbacks/0234_recovery_score_pain_state.rollback.sql
--   then verify: the md5 above is returned again.

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

  select capacity_state, regulation_state, pain_state
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

  -- Pain penalty (ROS-001 v1.1, 15% weight) applied to the pain STATE
  -- ("pain compared with your usual baseline"), not a 0-10 number:
  --   low / baseline (lower / around usual) = 0
  --   elevated       (higher than usual)    = half the weight  (0.075)
  --   high           (much higher)          = full weight      (0.15)
  -- A missing pain_state applies NO adjustment: it is "unknown", not "no pain"
  -- and not zero-pain evidence (same behaviour as the old formula for a
  -- missing pain_score). Floor of 0.70 on the modifier is unchanged.
  if cc.pain_state is not null then
    v_ns_modifier := greatest(
      v_ns_modifier - 0.15 * case cc.pain_state
                               when 'elevated' then 0.5
                               when 'high'     then 1.0
                               else 0.0
                             end,
      0.70);
  end if;

  v_final_score := least(greatest(v_raw_score * v_ns_modifier, 0), 100);

  return round(v_final_score, 2);
end;
$function$;
