-- Wire recovery_pulses (the only actively-used health logging surface — 62
-- rows, 12 in the last 7 days, via Telegram) into weekly_synthesis.py's
-- source view. captains_log_entries and health_daily_logs, the two sources
-- analytics_health_daily previously joined, both went quiet in June.
--
-- recovery_pulses has multiple rows/day (morning/midday/end_of_day), so it
-- can't join directly the way captains_log_entries/health_daily_logs do
-- (one row/day each). recovery_pulses_daily collapses each day to one row
-- first, worst-case-wins per field (this pipeline exists to catch risk
-- signals, so a bad morning shouldn't be smoothed away by a better evening).

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
    MAX(created_at) AS created_at
FROM recovery_pulses
GROUP BY log_date;

COMMENT ON VIEW recovery_pulses_daily IS
'One row per log_date, collapsing recovery_pulses'' multiple daily pulse entries '
'(morning/midday/end_of_day) into worst-case-wins values per field. Feeds '
'analytics_health_daily as a third source alongside captains_log_entries and '
'health_daily_logs.';

-- Extend analytics_health_daily with recovery_pulses_daily as a third FULL
-- JOIN source (p). Existing columns keep their current COALESCE precedence
-- (captains_log > health_daily_logs); pulses only fill a value in when
-- neither of the other two logged that day. New pulse-only fields
-- (pulse_body_signals, pulse_stress, pulse_readiness, pulse_count) are new
-- columns since no prior source models them — additive, nothing that reads
-- the existing columns breaks.
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
    p.pulse_count
   FROM captains_log_entries c
     FULL JOIN health_daily_logs d ON c.log_date = d.log_date
     FULL JOIN recovery_pulses_daily p ON COALESCE(c.log_date, d.log_date) = p.log_date
  ORDER BY (COALESCE(c.log_date, d.log_date, p.log_date)) DESC;

COMMENT ON VIEW analytics_health_daily IS
'FULL JOIN of captains_log_entries, health_daily_logs, and recovery_pulses_daily '
'(migration 0082) — one row per day across all three logging surfaces.';
