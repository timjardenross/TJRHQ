-- ── Recovery Pulses — multi-pulse daily telemetry (D-055 WP-2) ─────────────────
-- Four recovery pulses per day replacing the single morning snapshot model.
-- One of each pulse_type allowed per day (UNIQUE on log_date, pulse_type).

CREATE TABLE IF NOT EXISTS public.recovery_pulses (
  id               uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
  log_date         date         NOT NULL DEFAULT CURRENT_DATE,
  pulse_type       text         NOT NULL CHECK (pulse_type IN ('morning','midday','end_of_day','evening')),
  captured_at      timestamptz  NOT NULL DEFAULT now(),

  pain_score       numeric(4,1) CHECK (pain_score BETWEEN 0 AND 10),
  energy           text         CHECK (energy IN ('low','moderate','high')),
  mood             text         CHECK (mood IN ('low','stable','positive')),
  stress           text         CHECK (stress IN ('low','moderate','high')),
  readiness        text         CHECK (readiness IN ('low','moderate','high')),
  notes            text,

  confidence_score integer      CHECK (confidence_score BETWEEN 0 AND 100),
  source           text         NOT NULL DEFAULT 'manual'
                                CHECK (source IN ('manual','telegram','slack','import')),

  created_at       timestamptz  NOT NULL DEFAULT now(),
  updated_at       timestamptz  NOT NULL DEFAULT now(),

  UNIQUE (log_date, pulse_type)
);

COMMENT ON TABLE public.recovery_pulses IS
  'Multi-pulse recovery telemetry (D-055 WP-2). Four pulses per day: morning, midday, end_of_day, evening. Replaces single-snapshot dependence.';

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS recovery_pulses_updated_at ON public.recovery_pulses;
CREATE TRIGGER recovery_pulses_updated_at
  BEFORE UPDATE ON public.recovery_pulses
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE OR REPLACE VIEW public.recovery_confidence_today AS
SELECT
  CURRENT_DATE                         AS assessment_date,
  COUNT(*)::integer                    AS pulses_completed,
  (4 - COUNT(*)::integer)              AS pulses_missing,
  CASE COUNT(*) WHEN 4 THEN 100 WHEN 3 THEN 75 WHEN 2 THEN 50 WHEN 1 THEN 25 ELSE 0 END AS recovery_confidence,
  CASE COUNT(*) WHEN 4 THEN 'Full telemetry' WHEN 3 THEN 'One pulse missing' WHEN 2 THEN 'Multiple pulses missing' WHEN 1 THEN 'Minimal telemetry' ELSE 'No telemetry today' END AS confidence_label,
  bool_or(pulse_type = 'morning')      AS morning_done,
  bool_or(pulse_type = 'midday')       AS midday_done,
  bool_or(pulse_type = 'end_of_day')   AS end_of_day_done,
  bool_or(pulse_type = 'evening')      AS evening_done,
  MAX(captured_at)                     AS last_pulse_at,
  (SELECT p2.energy     FROM public.recovery_pulses p2 WHERE p2.log_date = CURRENT_DATE AND p2.energy    IS NOT NULL ORDER BY p2.captured_at DESC LIMIT 1) AS latest_energy,
  (SELECT p2.mood       FROM public.recovery_pulses p2 WHERE p2.log_date = CURRENT_DATE AND p2.mood      IS NOT NULL ORDER BY p2.captured_at DESC LIMIT 1) AS latest_mood,
  (SELECT p2.stress     FROM public.recovery_pulses p2 WHERE p2.log_date = CURRENT_DATE AND p2.stress    IS NOT NULL ORDER BY p2.captured_at DESC LIMIT 1) AS latest_stress,
  (SELECT p2.readiness  FROM public.recovery_pulses p2 WHERE p2.log_date = CURRENT_DATE AND p2.readiness IS NOT NULL ORDER BY p2.captured_at DESC LIMIT 1) AS latest_readiness,
  (SELECT p2.pain_score FROM public.recovery_pulses p2 WHERE p2.log_date = CURRENT_DATE AND p2.pain_score IS NOT NULL ORDER BY p2.captured_at DESC LIMIT 1) AS latest_pain_score
FROM public.recovery_pulses
WHERE log_date = CURRENT_DATE;

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
WHERE log_date >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY log_date
ORDER BY log_date DESC;
