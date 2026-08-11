-- Migration 0138 — Recovery Score / Life Participation: Recovery Pulse
-- fallbacks (Captain directive, 2026-08-10)
--
-- compute_recovery_score()'s Capacity subscore (20% weight) and
-- compute_life_participation()'s pleasure/social sub-scores (40% of LP's
-- own 15% weight = ~6% of total) only ever read captains_log_entries
-- columns (captain_capacity_rating, pleasure_creativity_marker,
-- what_happened) with no recovery_pulses fallback — unlike sleep/energy/
-- nervous-system, which already fall back via analytics_health_daily's
-- COALESCE (migration 0082). Today /human-systems-workbench/log (the only
-- writer of captains_log_entries) was disabled — Recovery Pulse is now the
-- sole capture path — so these fields are now permanently null, and were
-- silently defaulting to worst-case (capacity: neutral 50, arguably fine,
-- but see below) or below-neutral (social: 25) rather than genuinely
-- neutral, meaning the Recovery Score can no longer swing as far toward
-- STRONG or REST as it should on real telemetry.
--
-- Fixes:
--   1. Capacity: falls back to recovery_pulses_daily.readiness (already a
--      view column, migration 0082, just never read here) when
--      captain_capacity_rating is null — same low/moderate/high concept as
--      Green/Amber/Red, mapped to the same score tiers.
--   2. Life Participation pleasure: falls back to day_win (evening pulse,
--      migration 0119) when pleasure_creativity_marker is null — partial
--      credit for 'something_did', lesser credit for a check-in with no
--      positive marker, genuinely neutral (not zero) when no evening pulse
--      exists at all.
--   3. Life Participation social: no Recovery Pulse question maps to
--      "social contact" — rather than fabricate a proxy, the missing-data
--      case changes from 25 (below neutral — actively penalising an
--      unanswerable question) to 50 (neutral — honestly "unknown", not
--      "bad"). This is the one sub-score with no real fallback signal;
--      disclosed here, not hidden.

-- ── recovery_pulses_daily: surface day_win (worst-case-wins, matching
-- every other field in this view) ──────────────────────────────────────
CREATE OR REPLACE VIEW recovery_pulses_daily AS
SELECT
    log_date,
    COUNT(*) AS pulse_count,
    MAX(pain_score) AS pain_score,
    CASE MAX(CASE energy WHEN 'low' THEN 3 WHEN 'moderate' THEN 2 WHEN 'high' THEN 1 END)
        WHEN 3 THEN 'low' WHEN 2 THEN 'moderate' WHEN 1 THEN 'high' END AS energy,
    CASE MAX(CASE nervous_system WHEN 'dysregulated' THEN 3 WHEN 'activated' THEN 2 WHEN 'calm' THEN 1 END)
        WHEN 3 THEN 'dysregulated' WHEN 2 THEN 'activated' WHEN 1 THEN 'calm' END AS nervous_system,
    CASE MAX(CASE body_signals WHEN 'significant' THEN 3 WHEN 'present' THEN 2 WHEN 'quiet' THEN 1 END)
        WHEN 3 THEN 'significant' WHEN 2 THEN 'present' WHEN 1 THEN 'quiet' END AS body_signals,
    CASE MAX(CASE mood WHEN 'low' THEN 3 WHEN 'stable' THEN 2 WHEN 'positive' THEN 1 END)
        WHEN 3 THEN 'low' WHEN 2 THEN 'stable' WHEN 1 THEN 'positive' END AS mood,
    CASE MAX(CASE stress WHEN 'high' THEN 3 WHEN 'moderate' THEN 2 WHEN 'low' THEN 1 END)
        WHEN 3 THEN 'high' WHEN 2 THEN 'moderate' WHEN 1 THEN 'low' END AS stress,
    CASE MAX(CASE readiness WHEN 'low' THEN 3 WHEN 'moderate' THEN 2 WHEN 'high' THEN 1 END)
        WHEN 3 THEN 'low' WHEN 2 THEN 'moderate' WHEN 1 THEN 'high' END AS readiness,
    MAX(created_at) AS created_at,
    -- 2026-08-10: worst-case-wins across rough_day > nothing_much > something_did,
    -- same philosophy as every other field above — a bad evening pulse
    -- shouldn't be masked by an earlier better one on the rare day with 2.
    -- Appended at the end — CREATE OR REPLACE VIEW cannot insert a column
    -- before existing trailing columns, only append.
    CASE MAX(CASE day_win WHEN 'rough_day' THEN 3 WHEN 'nothing_much' THEN 2 WHEN 'something_did' THEN 1 END)
        WHEN 3 THEN 'rough_day' WHEN 2 THEN 'nothing_much' WHEN 1 THEN 'something_did' END AS day_win
FROM recovery_pulses
GROUP BY log_date;

COMMENT ON VIEW recovery_pulses_daily IS
'One row per log_date, collapsing recovery_pulses'' multiple daily pulse entries '
'(morning/midday/evening) into worst-case-wins values per field. Feeds '
'analytics_health_daily as a third source alongside captains_log_entries and '
'health_daily_logs. day_win added 2026-08-10 for compute_life_participation()''s '
'pleasure/creativity fallback.';

-- ── analytics_health_daily: surface p.day_win alongside the existing
-- pulse-only columns (unchanged precedence/columns otherwise) ───────────
CREATE OR REPLACE VIEW analytics_health_daily AS
 SELECT COALESCE(c.log_date, d.log_date, p.log_date) AS log_date,
    COALESCE(c.pain_score, d.pain_score, ROUND(p.pain_score)::smallint) AS pain_score,
    COALESCE(c.pain_location, d.pain_location) AS pain_location,
    COALESCE(c.energy, initcap(d.energy), initcap(p.energy)) AS energy,
    COALESCE(c.mood, initcap(d.mood), initcap(p.mood)) AS mood,
    COALESCE(c.sleep_hours, d.sleep_hours) AS sleep_hours,
    COALESCE(c.sleep_quality, initcap(d.sleep_quality)) AS sleep_quality,
    c.cpap_status,
    d.cpap_hours,
    c.physical_capacity,
    c.what_happened,
    c.what_changed,
    c.wins,
    c.blockers,
    c.decisions_made,
    c.tomorrows_priority,
    c.overall_note,
    d.movement_notes,
    d.work_location,
    d.sitting_tolerance_minutes,
    COALESCE(d.workload_constraint, 'unknown'::text) AS workload_constraint,
    d.notes,
    c.health_status,
    c.work_status,
    c.personal_status,
    c.captain_capacity_rating,
        CASE
            WHEN c.log_date IS NOT NULL AND d.log_date IS NOT NULL THEN 'both'::text
            WHEN c.log_date IS NOT NULL THEN 'captains_log'::text
            WHEN d.log_date IS NOT NULL THEN 'health_daily_logs'::text
            ELSE 'recovery_pulses'::text
        END AS data_source,
    COALESCE(c.created_at, d.created_at, p.created_at) AS created_at,
    COALESCE(d.nervous_system_state, p.nervous_system) AS nervous_system_state,
    c.expressive_write_done,
    c.pleasure_creativity_marker,
    p.body_signals AS pulse_body_signals,
    p.stress AS pulse_stress,
    p.readiness AS pulse_readiness,
    p.pulse_count,
    p.day_win AS pulse_day_win
   FROM captains_log_entries c
     FULL JOIN health_daily_logs d ON c.log_date = d.log_date
     FULL JOIN recovery_pulses_daily p ON COALESCE(c.log_date, d.log_date) = p.log_date
  ORDER BY (COALESCE(c.log_date, d.log_date, p.log_date)) DESC;

COMMENT ON VIEW analytics_health_daily IS
'FULL JOIN of captains_log_entries, health_daily_logs, and recovery_pulses_daily '
'(migration 0082, extended 0138) — one row per day across all three logging '
'surfaces.';

-- ── compute_life_participation: pleasure falls back to day_win; social's
-- missing-data default moves from below-neutral (25) to neutral (50) ────
-- Drop the old 5-arg signature first — CREATE OR REPLACE with a different
-- arg list creates a second overload rather than replacing, which makes
-- both future calls and `COMMENT ON FUNCTION` (below) ambiguous. Only one
-- real caller (compute_recovery_score, updated in this same migration).
DROP FUNCTION IF EXISTS compute_life_participation(text, text, text, smallint, text);

CREATE OR REPLACE FUNCTION compute_life_participation(
  p_movement_notes        text,
  p_pleasure_marker       text,
  p_what_happened         text,
  p_sitting_minutes       smallint,
  p_workload_constraint   text,
  p_day_win                text DEFAULT NULL
) RETURNS numeric(5,2)
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
  v_movement   numeric := 0;
  v_pleasure   numeric := 50; -- neutral default when no signal at all (2026-08-10, was 0)
  v_social     numeric := 50; -- neutral default; cannot parse social from text in SQL
  v_sitting    numeric := 50; -- neutral default when unknown
  v_workload   numeric := 50; -- neutral default
  v_score      numeric;
BEGIN
  -- Movement: present = 100, absent = 0
  IF p_movement_notes IS NOT NULL AND trim(p_movement_notes) <> '' THEN
    v_movement := 100;
  END IF;

  -- Pleasure / creativity: explicit captains_log marker = 100 (unchanged).
  -- 2026-08-10: falls back to Recovery Pulse's day_win when no marker
  -- exists — 'something_did' is a real, if softer, positive signal; a
  -- check-in with no positive marker gets less credit than an explicit
  -- note would; genuinely no data (no evening pulse either) is neutral,
  -- not the old hard 0 — absence of a now-disabled capture path isn't
  -- evidence of a bad day.
  IF p_pleasure_marker IS NOT NULL AND trim(p_pleasure_marker) <> '' THEN
    v_pleasure := 100;
  ELSIF p_day_win = 'something_did' THEN
    v_pleasure := 70;
  ELSIF p_day_win IS NOT NULL THEN
    v_pleasure := 40; -- nothing_much / rough_day: checked in, no positive marker
  END IF;
  -- else: stays at the neutral 50 default above.

  -- Social: what_happened present = 50 (neutral credit; text presence
  -- heuristic only, unchanged). 2026-08-10: no Recovery Pulse question
  -- maps to social contact, so absence stays neutral (50, the default
  -- above) rather than the old below-neutral 25 — an unanswerable
  -- question shouldn't be scored as a bad answer.
  IF p_what_happened IS NOT NULL AND trim(p_what_happened) <> '' THEN
    v_social := 50;
  END IF;

  -- Sitting tolerance: vs 120-min Stage 1 default baseline
  IF p_sitting_minutes IS NOT NULL THEN
    v_sitting := LEAST((p_sitting_minutes::numeric / 120.0) * 100, 100);
  END IF;

  -- Workload constraint
  v_workload := CASE lower(coalesce(p_workload_constraint, 'unknown'))
    WHEN 'none'     THEN 100
    WHEN 'light'    THEN 70
    WHEN 'moderate' THEN 40
    WHEN 'severe'   THEN 10
    ELSE 50 -- unknown / null
  END;

  v_score := (v_movement  * 0.25)
           + (v_pleasure  * 0.20)
           + (v_social    * 0.20)
           + (v_sitting   * 0.20)
           + (v_workload  * 0.15);

  RETURN ROUND(v_score, 2);
END;
$$;

COMMENT ON FUNCTION compute_life_participation IS
  'ROS-001 v1.1: Life Participation subscore (0-100). '
  'Primary Stage 1 outcome measure — measures life participation, not productivity. '
  'Weights: movement 25%, pleasure/creativity 20%, social (heuristic) 20%, '
  'sitting tolerance 20%, workload absence 15%. '
  'Hanscom principle: participation in life IS the recovery intervention; '
  'pain reduction is a downstream effect, not a gate. '
  '2026-08-10: pleasure falls back to Recovery Pulse day_win when no captains_log '
  'marker exists; social''s missing-data default is neutral (50), not below-neutral — '
  'no Recovery Pulse question maps to social contact, so absence is honestly unknown.';

-- ── compute_recovery_score: Capacity falls back to recovery_pulses'
-- readiness when captain_capacity_rating is null ────────────────────────
CREATE OR REPLACE FUNCTION compute_recovery_score(p_date date DEFAULT current_date)
RETURNS numeric(5,2)
LANGUAGE plpgsql STABLE AS $$
DECLARE
  r                analytics_health_daily%ROWTYPE;
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
BEGIN
  SELECT * INTO r FROM analytics_health_daily WHERE log_date = p_date LIMIT 1;

  -- No data for this date: return null (not zero — absence ≠ REST)
  IF r.log_date IS NULL THEN
    RETURN NULL;
  END IF;

  -- ── Sleep subscore (weight 25%) ──────────────────────────────
  -- base: proportional to 7.5h target, max 60 points
  v_sleep_base := LEAST(COALESCE(r.sleep_hours, 0) / 7.5, 1.0) * 60;

  -- quality bonus: Good +30, Fair +15, Poor +0
  v_sleep_qual := CASE lower(coalesce(r.sleep_quality, ''))
    WHEN 'good' THEN 30
    WHEN 'fair' THEN 15
    ELSE 0
  END;

  -- CPAP bonus: +10 when cpap_hours >= 90% of sleep_hours
  -- Fallback: +7 when cpap_status = 'Yes' but hours unrecorded
  v_cpap_bonus := 0;
  IF r.cpap_hours IS NOT NULL AND r.sleep_hours IS NOT NULL AND r.sleep_hours > 0 THEN
    IF r.cpap_hours >= r.sleep_hours * 0.9 THEN
      v_cpap_bonus := 10;
    END IF;
  ELSIF lower(coalesce(r.cpap_status, '')) = 'yes' THEN
    v_cpap_bonus := 7; -- partial credit when compliance known but hours not recorded
  END IF;

  v_sleep_score := LEAST(v_sleep_base + v_sleep_qual + v_cpap_bonus, 100);

  -- ── Nervous system subscore (weight 20%) ────────────────────
  v_ns_score := CASE r.nervous_system_state
    WHEN 'calm'         THEN 90
    WHEN 'activated'    THEN 55
    WHEN 'dysregulated' THEN 20
    ELSE 60 -- null / unrecorded → neutral
  END;

  -- Multiplicative modifier applied to weighted total
  v_ns_modifier := CASE r.nervous_system_state
    WHEN 'dysregulated' THEN 0.85
    WHEN 'activated'    THEN 0.95
    ELSE 1.00
  END;

  -- ── Energy subscore (weight 20%) ────────────────────────────
  -- View normalises to Title Case via initcap()
  v_energy_score := CASE initcap(coalesce(r.energy, ''))
    WHEN 'High'     THEN 90
    WHEN 'Moderate' THEN 60
    WHEN 'Low'      THEN 25
    ELSE 50 -- null / unrecorded → neutral
  END;

  -- ── Capacity subscore (weight 20%) ──────────────────────────
  -- captain_capacity_rating stored as Green/Amber/Red (migration 0005).
  -- 2026-08-10: falls back to recovery_pulses' readiness (low/moderate/
  -- high, same 3-tier concept, migration 0115) when the captains_log
  -- field is null — Captain's Log is disabled, Recovery Pulse is the sole
  -- capture path, so without this the Capacity subscore was permanently
  -- stuck at the neutral 50 default below, unable to reflect real
  -- telemetry either way.
  IF r.captain_capacity_rating IS NOT NULL THEN
    v_capacity_score := CASE r.captain_capacity_rating
      WHEN 'Green' THEN 85
      WHEN 'Amber' THEN 55
      WHEN 'Red'   THEN 20
      ELSE 50
    END;
  ELSE
    v_capacity_score := CASE r.pulse_readiness
      WHEN 'high'     THEN 85
      WHEN 'moderate' THEN 55
      WHEN 'low'      THEN 20
      ELSE 50 -- neither source recorded → neutral estimate
    END;
  END IF;

  -- ── Life Participation subscore (weight 15%) ────────────────
  v_lp_score := compute_life_participation(
    r.movement_notes,
    r.pleasure_creativity_marker,
    r.what_happened,
    r.sitting_tolerance_minutes,
    r.workload_constraint,
    r.pulse_day_win
  );

  -- ── Weighted sum ─────────────────────────────────────────────
  v_raw_score := (v_sleep_score    * 0.25)
               + (v_ns_score       * 0.20)
               + (v_energy_score   * 0.20)
               + (v_capacity_score * 0.20)
               + (v_lp_score       * 0.15);

  -- ── Apply nervous system modifier ───────────────────────────
  v_final_score := LEAST(GREATEST(v_raw_score * v_ns_modifier, 0), 100);

  RETURN ROUND(v_final_score, 2);
END;
$$;

COMMENT ON FUNCTION compute_recovery_score IS
  'ROS-001 v1.1: Daily Recovery Score (0-100). '
  'For Medical Officer clinical use and load management computation only. '
  'NOT displayed as a daily metric to the Captain — use get_recovery_posture() for dashboard output. '
  'Formula: Sleep(25%) + NervousSystem(20%) + Energy(20%) + Capacity(20%) + '
  'LifeParticipation(15%), then × NervousSystemModifier(0.85/0.95/1.0). '
  'Pain (body context) intentionally excluded from formula weight per Hanscom alignment '
  '(ROS-001 v1.1 WP Scoring Framework): pain is a lagging indicator, not a recovery target. '
  '2026-08-10: Capacity falls back to recovery_pulses.readiness when captain_capacity_rating '
  'is null (Captain''s Log disabled, Recovery Pulse is the sole capture path).';
