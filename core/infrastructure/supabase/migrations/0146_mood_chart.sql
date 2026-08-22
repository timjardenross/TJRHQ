-- Migration 0146 — Mood Chart (reactivated, Captain directive 2026-08-12)
--
-- Restores the mood_chart table + Telegram flow that migration 0140 removed
-- on 2026-08-11 in favour of folding a mood_score into Recovery Pulse. That
-- removal was itself a reversal of migration 0139 (never applied to this
-- database — CREATE TABLE mood_chart never ran there either). Captain's
-- call this time: keep BOTH — Recovery Pulse's own optional mood_score tap
-- stays as-is (recovery_pulses.mood_score, migration 0140), and mood_chart
-- comes back as its own separate, independently-scheduled flow. This
-- reintroduces the duplicate-manual-capture-surface pattern that 2026-08-10's
-- "Recovery Pulse is the sole manual health-capture path" decision was
-- written to prevent — done deliberately and knowingly, not by oversight.
-- See [[recovery-pulse-sole-capture-2026-08-10]].
--
-- Table/view shape is carried over unchanged from migration 0139's original
-- design (git show d5e9d088^:core/infrastructure/supabase/migrations/
-- 0139_mood_chart.sql). RLS is NOT carried over unchanged: 0139 granted
-- read/write to "all users" (effectively PUBLIC/anon) — the exact insecure
-- default this platform has repeatedly had to retrofit-fix elsewhere (see
-- migration 0110's tightening of recovery_pulses/activity_logs RLS, and
-- migration 0135's xo_bot least-privilege role). This migration scopes
-- mood_chart access to the xo_bot role from day one instead of shipping an
-- open table and fixing it later.

CREATE TABLE IF NOT EXISTS public.mood_chart (
  id               uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
  log_date         date         NOT NULL DEFAULT CURRENT_DATE,
  time_of_day      text         NOT NULL CHECK (time_of_day IN ('morning','afternoon','evening')),
  mood_score       integer      NOT NULL CHECK (mood_score BETWEEN 1 AND 10),
  captured_at      timestamptz  NOT NULL DEFAULT now(),

  -- Contextual annotations (optional)
  sleep_hours      numeric(4,2),
  sleep_quality    text         CHECK (sleep_quality IN ('poor','fair','good','excellent')),
  pain_level       integer      CHECK (pain_level BETWEEN 0 AND 10),
  anxiety_level    integer      CHECK (anxiety_level BETWEEN 0 AND 10),
  stress_level     integer      CHECK (stress_level BETWEEN 0 AND 10),
  alcohol_use      boolean,
  substance_use    boolean,
  notes            text,

  source           text         NOT NULL DEFAULT 'telegram'
                                CHECK (source IN ('telegram','slack','manual','import')),

  created_at       timestamptz  NOT NULL DEFAULT now(),
  updated_at       timestamptz  NOT NULL DEFAULT now(),

  UNIQUE (log_date, time_of_day)
);

COMMENT ON TABLE public.mood_chart IS
  'Simple daily mood tracking (1-10 scale) at key times with optional contextual notes.
   Complements recovery_pulses (which also has its own optional mood_score field,
   migration 0140) with a dedicated, independently-scheduled mood assessment plus
   sleep, pain, anxiety, substance tracking. Reactivated 2026-08-12, migration 0146.';

CREATE OR REPLACE FUNCTION public.set_mood_chart_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS mood_chart_updated_at ON public.mood_chart;
CREATE TRIGGER mood_chart_updated_at
  BEFORE UPDATE ON public.mood_chart
  FOR EACH ROW EXECUTE FUNCTION public.set_mood_chart_updated_at();

-- ── Daily mood summary view (today's mood entries) ──────────────────────────
CREATE OR REPLACE VIEW public.mood_chart_today AS
SELECT
  CURRENT_DATE                         AS assessment_date,
  COUNT(*)::integer                    AS entries_today,
  AVG(mood_score)::numeric(3,1)        AS avg_mood_score,
  MIN(mood_score)::integer             AS low_mood_score,
  MAX(mood_score)::integer             AS high_mood_score,
  bool_or(time_of_day = 'morning')     AS morning_done,
  bool_or(time_of_day = 'afternoon')   AS afternoon_done,
  bool_or(time_of_day = 'evening')     AS evening_done,
  MAX(captured_at)                     AS last_entry_at,
  (SELECT mood_score FROM public.mood_chart WHERE log_date = CURRENT_DATE AND time_of_day = 'morning' LIMIT 1) AS morning_score,
  (SELECT mood_score FROM public.mood_chart WHERE log_date = CURRENT_DATE AND time_of_day = 'afternoon' LIMIT 1) AS afternoon_score,
  (SELECT mood_score FROM public.mood_chart WHERE log_date = CURRENT_DATE AND time_of_day = 'evening' LIMIT 1) AS evening_score,
  (SELECT AVG(sleep_hours) FROM public.mood_chart WHERE log_date = CURRENT_DATE) AS avg_sleep_hours,
  (SELECT bool_or(anxiety_level > 5) FROM public.mood_chart WHERE log_date = CURRENT_DATE) AS elevated_anxiety
FROM public.mood_chart
WHERE log_date = CURRENT_DATE;

-- ── 7-day mood trend ─────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW public.mood_chart_7d AS
SELECT
  log_date,
  COUNT(*)::integer                    AS entries,
  AVG(mood_score)::numeric(3,1)        AS avg_mood,
  MIN(mood_score)::integer             AS low_mood,
  MAX(mood_score)::integer             AS high_mood,
  AVG(sleep_hours)::numeric(4,2)       AS avg_sleep,
  AVG(anxiety_level)::numeric(4,1)     AS avg_anxiety,
  AVG(pain_level)::numeric(4,1)        AS avg_pain,
  bool_or(alcohol_use)                 AS any_alcohol,
  bool_or(substance_use)               AS any_substances
FROM public.mood_chart
WHERE log_date >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY log_date
ORDER BY log_date DESC;

-- ── RLS: scoped to xo_bot only (migration 0135's least-privilege role),
-- not PUBLIC/anon. No policy for the `authenticated` or `anon` roles is
-- created here — only xo_bot, the sole live writer/reader of this table.
ALTER TABLE public.mood_chart ENABLE ROW LEVEL SECURITY;

GRANT SELECT, INSERT, UPDATE ON public.mood_chart TO xo_bot;
GRANT SELECT ON public.mood_chart_today TO xo_bot;
GRANT SELECT ON public.mood_chart_7d TO xo_bot;

DROP POLICY IF EXISTS xo_bot_select ON public.mood_chart;
CREATE POLICY xo_bot_select ON public.mood_chart FOR SELECT TO xo_bot USING (true);

DROP POLICY IF EXISTS xo_bot_insert ON public.mood_chart;
CREATE POLICY xo_bot_insert ON public.mood_chart FOR INSERT TO xo_bot WITH CHECK (true);

DROP POLICY IF EXISTS xo_bot_update ON public.mood_chart;
CREATE POLICY xo_bot_update ON public.mood_chart FOR UPDATE TO xo_bot USING (true) WITH CHECK (true);

COMMENT ON VIEW public.mood_chart_today IS
  'Today''s mood entries summary: average mood, trends, contextual signals.';

COMMENT ON VIEW public.mood_chart_7d IS
  '7-day mood trend: rolling averages, patterns in sleep, anxiety, pain, substances.';
