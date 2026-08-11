-- Recovery Pulse: reduce from 4 pulses/day to 3 (Captain directive, 2026-08-10).
--
-- Full reasoning lives in telegram-bots/xo/pulse_time.py's module docstring
-- and .claude/skills/bot-reviews/fixes-2026-08-09/recovery-pulse-3x-implementation.md
-- (short version: `end_of_day` was the dropped bucket — least conceptually
-- distinct from `midday`, confirmed by live usage data being the 2nd-least-
-- logged pulse_type, and a retired Slack scheduler already independently
-- assumed a 3-window day). pulse_time.py's canonical bucketing (the only
-- thing the live Telegram flow and voice-capture promotion write through)
-- now only ever produces morning/midday/evening.
--
-- This migration rebuilds recovery_confidence_today and
-- recovery_pulse_adherence_7d so their scoring math targets 3 pulses instead
-- of 4, WITHOUT touching the recovery_pulses table itself:
--   - pulse_type CHECK constraint keeps 'end_of_day' as a legal value. It is
--     out of this change's authorized scope to touch the LCARS Portal Medical
--     Bay pulse page (human-systems-workbench/medical/pulse/page.tsx) or the
--     retired Slack /recovery-pulse modal (platform-runtime/commands/
--     recovery_pulse.py), both of which still offer a 4-way end_of_day
--     option and write it verbatim if used. Disclosed as a known follow-up,
--     not fixed here.
--   - pulses_completed / pulses_missing / recovery_confidence are computed
--     from COUNT(*) FILTER (WHERE pulse_type IN ('morning','midday','evening'))
--     rather than a bare COUNT(*) — this is deliberately defensive: if the
--     Portal or Slack path ever writes a legacy end_of_day row on a day that
--     already has all 3 canonical pulses, a naive COUNT(*) would hit 4, which
--     wouldn't match any WHEN branch in the old CASE-based scoring and would
--     silently fall through to 0% ("no telemetry") despite full telemetry
--     being logged. Filtering + LEAST/GREATEST avoids that trap entirely.
--   - end_of_day_done is kept as a column (still bool_or(pulse_type =
--     'end_of_day')) so the LCARS Portal / command-centre backend, which
--     read it by name (lcars-portal/src/lib/useRecoveryConfidence.ts,
--     lcars-portal/src/components/RecoveryConfidencePanel.tsx, core/
--     command-centre/backend/api/personal-health.js), don't see the column
--     vanish out from under them. It will simply read false on every day the
--     Telegram flow is the only surface used, which is the live norm.
--
-- Idempotent (CREATE OR REPLACE VIEW).

CREATE OR REPLACE VIEW public.recovery_confidence_today AS
SELECT
  (CURRENT_TIMESTAMP AT TIME ZONE 'Australia/Brisbane')::date AS assessment_date,
  COUNT(*) FILTER (WHERE pulse_type IN ('morning','midday','evening'))::integer
    AS pulses_completed,
  GREATEST(0, 3 - COUNT(*) FILTER (WHERE pulse_type IN ('morning','midday','evening')))::integer
    AS pulses_missing,
  LEAST(100, ROUND(100.0 * COUNT(*) FILTER (WHERE pulse_type IN ('morning','midday','evening')) / 3))::integer
    AS recovery_confidence,
  CASE COUNT(*) FILTER (WHERE pulse_type IN ('morning','midday','evening'))
    WHEN 0 THEN 'No telemetry today'
    WHEN 1 THEN 'Multiple pulses missing'
    WHEN 2 THEN 'One pulse missing'
    ELSE 'Full telemetry'
  END AS confidence_label,
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

CREATE OR REPLACE VIEW public.recovery_pulse_adherence_7d AS
SELECT
  log_date,
  COUNT(*) FILTER (WHERE pulse_type IN ('morning','midday','evening'))::integer
    AS pulses_completed,
  LEAST(100, ROUND(100.0 * COUNT(*) FILTER (WHERE pulse_type IN ('morning','midday','evening')) / 3))::integer
    AS daily_confidence,
  bool_or(pulse_type = 'morning')      AS morning_done,
  bool_or(pulse_type = 'midday')       AS midday_done,
  bool_or(pulse_type = 'end_of_day')   AS end_of_day_done,
  bool_or(pulse_type = 'evening')      AS evening_done,
  AVG(confidence_score)::numeric(5,1)  AS avg_self_confidence
FROM public.recovery_pulses
WHERE log_date >= (CURRENT_TIMESTAMP AT TIME ZONE 'Australia/Brisbane')::date - INTERVAL '7 days'
GROUP BY log_date
ORDER BY log_date DESC;
