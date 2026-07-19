-- ============================================================
-- Migration 0017 — analytics_health_daily v2
-- ROS-001 v1.1 — Stage 1 Recovery Operating System
-- Date: 2026-06-19
--
-- Drops and recreates analytics_health_daily to surface the three
-- new ROS fields added in migration 0016. All existing view logic
-- preserved; new columns appended after created_at.
--
-- APPLIED: 2026-06-19 via Supabase MCP
-- ============================================================

DROP VIEW IF EXISTS analytics_health_daily;

CREATE VIEW analytics_health_daily AS
SELECT
  COALESCE(c.log_date, d.log_date)                    AS log_date,

  -- ── Body context (pain) — lagging/contextual indicator ────
  COALESCE(c.pain_score, d.pain_score)                AS pain_score,
  COALESCE(c.pain_location, d.pain_location)          AS pain_location,

  -- ── Energy / mood (Title Case, captains_log preferred) ───
  COALESCE(c.energy, initcap(d.energy))               AS energy,
  COALESCE(c.mood,   initcap(d.mood))                 AS mood,

  -- ── Sleep ─────────────────────────────────────────────────
  COALESCE(c.sleep_hours, d.sleep_hours)              AS sleep_hours,
  COALESCE(c.sleep_quality, initcap(d.sleep_quality)) AS sleep_quality,
  c.cpap_status,
  d.cpap_hours,

  -- ── Physical capacity ──────────────────────────────────────
  c.physical_capacity,

  -- ── Narrative (captains_log only) ─────────────────────────
  c.what_happened,
  c.what_changed,
  c.wins,
  c.blockers,
  c.decisions_made,
  c.tomorrows_priority,
  c.overall_note,

  -- ── Movement / physical context ───────────────────────────
  d.movement_notes,
  d.work_location,
  d.sitting_tolerance_minutes,
  COALESCE(d.workload_constraint, 'unknown')          AS workload_constraint,
  d.notes,

  -- ── RAG status ────────────────────────────────────────────
  c.health_status,
  c.work_status,
  c.personal_status,
  c.captain_capacity_rating,

  -- ── Source metadata ────────────────────────────────────────
  CASE
    WHEN c.log_date IS NOT NULL AND d.log_date IS NOT NULL THEN 'both'
    WHEN c.log_date IS NOT NULL                            THEN 'captains_log'
    ELSE                                                        'health_daily_logs'
  END                                                     AS data_source,
  COALESCE(c.created_at, d.created_at)                  AS created_at,

  -- ── ROS-001 v1.1 fields (appended; schema additions 0016) ──
  -- Nervous system state: first-class daily input, ANS activation signal.
  -- Distinct from mood. Sourced from health_daily_logs (lightweight check-in).
  d.nervous_system_state,

  -- Recovery practice tracking (completion flags only; no content stored).
  c.expressive_write_done,
  c.pleasure_creativity_marker

FROM captains_log_entries  c
FULL JOIN health_daily_logs d ON c.log_date = d.log_date
ORDER BY COALESCE(c.log_date, d.log_date) DESC;

COMMENT ON VIEW analytics_health_daily IS
  'Unified daily health analytics view. Merges captains_log_entries (reflective journal) '
  'and health_daily_logs (lightweight check-in) on log_date via FULL JOIN. '
  'captains_log_entries fields are preferred on conflict (COALESCE pattern). '
  'Case normalised to Title Case for cross-table consistency. '
  'ROS-001 v1.1 (migration 0017): includes nervous_system_state, expressive_write_done, '
  'pleasure_creativity_marker. ADR-HEALTH-001: permanent dual-table architecture.';
