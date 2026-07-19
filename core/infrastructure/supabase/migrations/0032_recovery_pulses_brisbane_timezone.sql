-- ── Recovery Pulses — Brisbane timezone fix ──────────────────────────────────
-- The recovery_confidence_today view and recovery_pulses.log_date default both
-- used UTC CURRENT_DATE. Captain is in Brisbane (UTC+10), so pulses logged
-- before 10:00 AEST were stored as the previous UTC date, and the view would
-- show 0 pulses from midnight UTC (= 10:00 AEST) onward — triggering a false
-- critical alert every morning.
--
-- Fix: anchor log_date and all view comparisons to Australia/Brisbane local date.
--
-- NOTE: As of 2026-06-26 the live DB already has this fix applied. This migration
-- documents the intended final state; it was applied out-of-band before being
-- recorded here. The live recovery_pulses table uses nervous_system + body_signals
-- columns (not mood/stress), and the view already references Brisbane timezone.

-- 1. Fix the table default so new pulses land on the Brisbane-local date
ALTER TABLE public.recovery_pulses
  ALTER COLUMN log_date
  SET DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Australia/Brisbane')::date;

-- 2. Rebuild recovery_confidence_today using Brisbane-local date throughout
CREATE OR REPLACE VIEW public.recovery_confidence_today AS
SELECT
  (CURRENT_TIMESTAMP AT TIME ZONE 'Australia/Brisbane')::date  AS assessment_date,
  COUNT(*)::integer                    AS pulses_completed,
  (4 - COUNT(*)::integer)              AS pulses_missing,
  CASE COUNT(*) WHEN 4 THEN 100 WHEN 3 THEN 75 WHEN 2 THEN 50 WHEN 1 THEN 25 ELSE 0 END AS recovery_confidence,
  CASE COUNT(*) WHEN 4 THEN 'Full telemetry' WHEN 3 THEN 'One pulse missing' WHEN 2 THEN 'Multiple pulses missing' WHEN 1 THEN 'Minimal telemetry' ELSE 'No telemetry today' END AS confidence_label,
  bool_or(pulse_type = 'morning')      AS morning_done,
  bool_or(pulse_type = 'midday')       AS midday_done,
  bool_or(pulse_type = 'end_of_day')   AS end_of_day_done,
  bool_or(pulse_type = 'evening')      AS evening_done,
  MAX(captured_at)                     AS last_pulse_at,
  (SELECT p2.energy          FROM public.recovery_pulses p2
   WHERE p2.log_date = (CURRENT_TIMESTAMP AT TIME ZONE 'Australia/Brisbane')::date
     AND p2.energy          IS NOT NULL ORDER BY p2.captured_at DESC LIMIT 1) AS latest_energy,
  (SELECT p2.nervous_system  FROM public.recovery_pulses p2
   WHERE p2.log_date = (CURRENT_TIMESTAMP AT TIME ZONE 'Australia/Brisbane')::date
     AND p2.nervous_system  IS NOT NULL ORDER BY p2.captured_at DESC LIMIT 1) AS latest_nervous_system,
  (SELECT p2.body_signals    FROM public.recovery_pulses p2
   WHERE p2.log_date = (CURRENT_TIMESTAMP AT TIME ZONE 'Australia/Brisbane')::date
     AND p2.body_signals    IS NOT NULL ORDER BY p2.captured_at DESC LIMIT 1) AS latest_body_signals,
  (SELECT p2.readiness       FROM public.recovery_pulses p2
   WHERE p2.log_date = (CURRENT_TIMESTAMP AT TIME ZONE 'Australia/Brisbane')::date
     AND p2.readiness       IS NOT NULL ORDER BY p2.captured_at DESC LIMIT 1) AS latest_readiness,
  (SELECT p2.pain_score      FROM public.recovery_pulses p2
   WHERE p2.log_date = (CURRENT_TIMESTAMP AT TIME ZONE 'Australia/Brisbane')::date
     AND p2.pain_score      IS NOT NULL ORDER BY p2.captured_at DESC LIMIT 1) AS latest_pain_score
FROM public.recovery_pulses
WHERE log_date = (CURRENT_TIMESTAMP AT TIME ZONE 'Australia/Brisbane')::date;

-- 3. Rebuild the 7-day adherence view with Brisbane-local date too
CREATE OR REPLACE VIEW public.recovery_pulse_adherence_7d AS
SELECT
  log_date,
  COUNT(*)::integer                    AS pulses_completed,
  CASE COUNT(*) WHEN 4 THEN 100 WHEN 3 THEN 75 WHEN 2 THEN 50 WHEN 1 THEN 25 ELSE 0 END AS daily_confidence,
  bool_or(pulse_type = 'morning')      AS morning_done,
  bool_or(pulse_type = 'midday')       AS midday_done,
  bool_or(pulse_type = 'end_of_day')   AS end_of_day_done,
  bool_or(pulse_type = 'evening')      AS evening_done,
  AVG(confidence_score)::numeric(5,1)  AS avg_self_confidence
FROM public.recovery_pulses
WHERE log_date >= (CURRENT_TIMESTAMP AT TIME ZONE 'Australia/Brisbane')::date - INTERVAL '7 days'
GROUP BY log_date
ORDER BY log_date DESC;
