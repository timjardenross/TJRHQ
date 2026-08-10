-- Migration 0140 — Recovery Pulse: mood_score (Captain directive, 2026-08-11)
--
-- A separate 'mood_chart' feature (migration 0139, telegram-bots/xo/
-- mood_chart.py, a /mood_chart command) was merged to main independently
-- and asked to be scheduled 3x/day — a second, independent manual-capture
-- flow with its own table, running in parallel with Recovery Pulse. That
-- directly contradicts 2026-08-10's "Recovery Pulse is the sole manual
-- health-capture path" decision (see [[recovery-pulse-sole-capture-2026-08-10]]
-- memory / commit 2b87954a and follow-ons). Captain's call: fold a
-- mood_score into the EXISTING Recovery Pulse flow instead — one prompt,
-- one flow, richer data — rather than deploy the second flow. Migration
-- 0139 is removed (never applied to this database — CREATE TABLE
-- mood_chart never ran, nothing depends on it) alongside this one; see
-- that commit's message for the full reasoning.
--
-- mood_score is a NEW numeric (1-10) column, distinct from the existing
-- legacy `mood` text column (categorical low/stable/positive, unused
-- since the 2026-06-26 telemetry redesign per recovery_pulses_daily's own
-- comments) — not reused, not renamed, to avoid conflating an old
-- deprecated field with a new one under the same name.

ALTER TABLE public.recovery_pulses
  ADD COLUMN IF NOT EXISTS mood_score smallint CHECK (mood_score BETWEEN 1 AND 10);

COMMENT ON COLUMN public.recovery_pulses.mood_score IS
  '1 (worst) - 10 (best) holistic mood rating, optional, captured via the '
  'existing Telegram Recovery Pulse tap flow (an extra optional step after '
  'the pulse''s normal required taps, not a new prompt/schedule). Added '
  '2026-08-11 in place of deploying a separate mood_chart capture flow — '
  'see migration 0140''s header comment.';

-- ── recovery_pulses_daily: surface mood_score, worst-case-wins (lower =
-- worse, so MIN picks the worst reading of the day, matching every other
-- field's philosophy in this view). Appended at the end — CREATE OR
-- REPLACE VIEW cannot reorder existing columns, only append. ────────────
CREATE OR REPLACE VIEW public.recovery_pulses_daily AS
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
    CASE MAX(CASE day_win WHEN 'rough_day' THEN 3 WHEN 'nothing_much' THEN 2 WHEN 'something_did' THEN 1 END)
        WHEN 3 THEN 'rough_day' WHEN 2 THEN 'nothing_much' WHEN 1 THEN 'something_did' END AS day_win,
    MIN(mood_score) AS mood_score
FROM public.recovery_pulses
GROUP BY log_date;

COMMENT ON VIEW public.recovery_pulses_daily IS
'One row per log_date, collapsing recovery_pulses'' multiple daily pulse entries '
'(morning/midday/evening) into worst-case-wins values per field. Feeds '
'analytics_health_daily as a third source alongside captains_log_entries and '
'health_daily_logs. day_win added 2026-08-10, mood_score added 2026-08-11 '
'(worst-case-wins = MIN, since lower is worse on the 1-10 scale).';

-- ── analytics_health_daily: surface p.mood_score alongside the existing
-- pulse-only columns (unchanged precedence/columns otherwise). Captured,
-- not yet wired into compute_recovery_score()'s formula weights — that's
-- a separate weighting decision, disclosed as open, not silently done
-- here. ───────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW public.analytics_health_daily AS
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
    p.day_win AS pulse_day_win,
    p.mood_score AS pulse_mood_score
   FROM captains_log_entries c
     FULL JOIN health_daily_logs d ON c.log_date = d.log_date
     FULL JOIN recovery_pulses_daily p ON COALESCE(c.log_date, d.log_date) = p.log_date
  ORDER BY (COALESCE(c.log_date, d.log_date, p.log_date)) DESC;

COMMENT ON VIEW public.analytics_health_daily IS
'FULL JOIN of captains_log_entries, health_daily_logs, and recovery_pulses_daily '
'(migration 0082, extended 0138/0140) — one row per day across all three '
'logging surfaces.';
