-- ============================================================
-- Migration 0018 — Recovery Score Functions
-- ROS-001 v1.1 — Stage 1 Recovery Operating System
-- Date: 2026-06-19
--
-- Creates two functions:
--
--   compute_recovery_score(date) → numeric(5,2)
--     Raw 0-100 Recovery Score for Medical Officer clinical use
--     and load management computation.
--     NOT displayed as a daily number to the Captain.
--
--   get_recovery_posture(date) → TABLE(...)
--     Operational output: posture band, capacity guidance,
--     and mission guidance. This is what surfaces in dashboards
--     and the Recovery Brief.
--
-- Also creates helper:
--   compute_life_participation(...) → numeric(5,2)
--     Life Participation subscore (0-100). Primary Stage 1
--     outcome measure — measures life, not productivity.
--
-- FORMULA (ROS-001 v1.1, WP Scoring Framework):
--   RecoveryScore =
--     (SleepScore           × 0.25)
--     + (NervousSystemScore × 0.20)
--     + (EnergyScore        × 0.20)
--     + (CapacityScore      × 0.20)
--     + (LifeParticipation  × 0.15)
--     × NervousSystemModifier
--
--   Pain (body context): weight 0. Contextual/lagging indicator
--   for Medical Officer interpretation only. Excluded from formula
--   weight per Hanscom alignment — pain is not a recovery target.
--
-- APPLIED: 2026-06-19 via Supabase MCP
-- ============================================================


-- ── Helper: Life Participation subscore ─────────────────────────
-- Weights: movement 25%, pleasure/creativity 20%, social 20%,
--          sitting_tolerance 20%, workload_unconstrained 15%.
-- Social signal uses what_happened presence as a heuristic (cannot
-- determine social engagement from text content in SQL).
-- Sitting baseline: 120 minutes (conservative Stage 1 default;
-- personal baseline field to be added in a future migration).

CREATE OR REPLACE FUNCTION compute_life_participation(
  p_movement_notes        text,
  p_pleasure_marker       text,
  p_what_happened         text,
  p_sitting_minutes       smallint,
  p_workload_constraint   text
) RETURNS numeric(5,2)
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
  v_movement   numeric := 0;
  v_pleasure   numeric := 0;
  v_social     numeric := 50; -- neutral default; cannot parse social from text in SQL
  v_sitting    numeric := 50; -- neutral default when unknown
  v_workload   numeric := 50; -- neutral default
  v_score      numeric;
BEGIN
  -- Movement: present = 100, absent = 0
  IF p_movement_notes IS NOT NULL AND trim(p_movement_notes) <> '' THEN
    v_movement := 100;
  END IF;

  -- Pleasure / creativity: present = 100, absent = 0
  IF p_pleasure_marker IS NOT NULL AND trim(p_pleasure_marker) <> '' THEN
    v_pleasure := 100;
  END IF;

  -- Social: what_happened present = 50 (neutral credit; text presence heuristic only)
  IF p_what_happened IS NOT NULL AND trim(p_what_happened) <> '' THEN
    v_social := 50;
  ELSE
    v_social := 25; -- less credit when no reflection recorded
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
  'pain reduction is a downstream effect, not a gate.';


-- ── Main: Recovery Score ─────────────────────────────────────────

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
  -- captain_capacity_rating stored as Green/Amber/Red (migration 0005)
  v_capacity_score := CASE r.captain_capacity_rating
    WHEN 'Green' THEN 85
    WHEN 'Amber' THEN 55
    WHEN 'Red'   THEN 20
    ELSE 50 -- null → neutral estimate
  END;

  -- ── Life Participation subscore (weight 15%) ────────────────
  v_lp_score := compute_life_participation(
    r.movement_notes,
    r.pleasure_creativity_marker,
    r.what_happened,
    r.sitting_tolerance_minutes,
    r.workload_constraint
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
  '(ROS-001 v1.1 WP Scoring Framework): pain is a lagging indicator, not a recovery target.';


-- ── Operational: Recovery Posture ───────────────────────────────
-- Surfaces posture band, capacity guidance, and mission guidance.
-- Language follows the Standing Tone Instruction: non-judgemental,
-- non-comparative, guidance-oriented. Not directive.
-- Raw score is included for Medical Officer / analytics use only.

CREATE OR REPLACE FUNCTION get_recovery_posture(p_date date DEFAULT current_date)
RETURNS TABLE (
  posture           text,
  posture_message   text,
  capacity_band     text,
  capacity_message  text,
  mission_guidance  text,
  score             numeric(5,2),  -- Medical Officer / analytics only; not for daily display
  data_available    boolean
)
LANGUAGE plpgsql STABLE AS $$
DECLARE
  v_score numeric(5,2);
BEGIN
  v_score := compute_recovery_score(p_date);

  IF v_score IS NULL THEN
    RETURN QUERY SELECT
      'UNKNOWN'::text,
      'No health data recorded for this date.'::text,
      'UNKNOWN'::text,
      'Record a health check-in to receive capacity guidance.'::text,
      'No capacity data available — proceed with care.'::text,
      NULL::numeric(5,2),
      false;
    RETURN;
  END IF;

  RETURN QUERY SELECT
    -- Posture band
    CASE
      WHEN v_score >= 80 THEN 'STRONG'
      WHEN v_score >= 65 THEN 'STABLE'
      WHEN v_score >= 50 THEN 'FRAGILE'
      ELSE                    'REST'
    END,

    -- Posture message: non-judgemental; Standing Tone Instruction
    CASE
      WHEN v_score >= 80 THEN 'The system is settled and capacity is available. A good day to engage.'
      WHEN v_score >= 65 THEN 'The system is settled. Continue present pattern.'
      WHEN v_score >= 50 THEN 'The system needs protection today. Lighter load recommended.'
      ELSE                    'The nervous system needs rest today. No operational load recommended.'
    END,

    -- Capacity band
    CASE
      WHEN v_score >= 80 THEN 'GOOD'
      WHEN v_score >= 65 THEN 'MODERATE'
      WHEN v_score >= 50 THEN 'LIMITED'
      ELSE                    'REST'
    END,

    -- Capacity message
    CASE
      WHEN v_score >= 80 THEN 'Capacity available. Estimated window: 4–5 hours.'
      WHEN v_score >= 65 THEN 'Moderate capacity available. Estimated window: 3–4 hours.'
      WHEN v_score >= 50 THEN 'Limited capacity today. Estimated window: 1–2 hours. Protect afternoon.'
      ELSE                    'Rest is the priority today. Minimal operational engagement.'
    END,

    -- Mission guidance: guidance language; not directive
    CASE
      WHEN v_score >= 80 THEN 'Up to 2 active missions appropriate today. New starts possible.'
      WHEN v_score >= 65 THEN '1 active mission appropriate today. New starts not recommended.'
      WHEN v_score >= 50 THEN 'Admin only today. No new mission starts. Continue in-progress cautiously.'
      ELSE                    'No operational load today. Mission work not recommended.'
    END,

    v_score,
    true;
END;
$$;

COMMENT ON FUNCTION get_recovery_posture IS
  'ROS-001 v1.1: Operational recovery posture for dashboard and Recovery Brief. '
  'Returns posture band (STRONG/STABLE/FRAGILE/REST), capacity guidance, and mission '
  'guidance derived from compute_recovery_score(). '
  'Language follows the Standing Tone Instruction: non-judgemental, non-comparative, '
  'guidance-oriented — not directive. '
  'Raw score is included for Medical Officer use only; '
  'must not be displayed as a daily performance metric to the Captain.';
