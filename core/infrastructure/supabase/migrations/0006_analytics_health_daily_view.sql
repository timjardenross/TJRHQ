-- ============================================================
-- Migration 0006 — analytics_health_daily view
-- ADR: ADR-HEALTH-001 (Option B: dual-purpose coexistence)
-- Date: 2026-06-13
--
-- PURPOSE
-- Creates a unified analytics view that merges health_daily_logs
-- (operational Slack check-in) and captains_log_entries (reflective
-- journal) on log_date.
--
-- This view is the primary data source for weekly_synthesis.py and
-- any future analytics pipeline, so that both capture paths contribute
-- to health intelligence without merging the underlying tables.
--
-- DESIGN PRINCIPLES (ADR-HEALTH-001)
-- - health_daily_logs and captains_log_entries remain separate tables
-- - The view provides a single query surface for analytics
-- - captains_log_entries fields take precedence where both sources have
--   data for the same date (COALESCE order)
-- - Case-convention differences are normalised to Title Case here,
--   matching the captains_log_entries convention used by capacity_score.py
-- - Energy and mood from health_daily_logs (lowercase) are uppercased
--   via INITCAP() so downstream code sees one convention
--
-- APPLY: Supabase SQL editor or supabase db push
-- ============================================================


-- ── Drop existing view if present (idempotent) ────────────────────────────
drop view if exists analytics_health_daily;


-- ── Unified analytics view ────────────────────────────────────────────────
create or replace view analytics_health_daily as
select
    -- Date (from whichever source has it — both always should)
    coalesce(c.log_date, d.log_date)                            as log_date,

    -- Pain — prefer Captain's Log; fall back to Slack check-in
    coalesce(c.pain_score,    d.pain_score)                     as pain_score,
    coalesce(c.pain_location, d.pain_location)                  as pain_location,

    -- Energy — normalise health_daily_logs lowercase to Title Case
    coalesce(
        c.energy,
        initcap(d.energy)
    )                                                           as energy,

    -- Mood — normalise health_daily_logs lowercase to Title Case
    coalesce(
        c.mood,
        initcap(d.mood)
    )                                                           as mood,

    -- Sleep
    coalesce(c.sleep_hours,   d.sleep_hours)                    as sleep_hours,
    coalesce(
        c.sleep_quality,
        initcap(d.sleep_quality)
    )                                                           as sleep_quality,

    -- CPAP — captains_log_entries has cpap_status (text enum);
    --        health_daily_logs has cpap_hours (numeric).
    --        Expose both so consumers can pick the appropriate field.
    c.cpap_status                                               as cpap_status,
    d.cpap_hours                                                as cpap_hours,

    -- Physical capacity (captains_log_entries only)
    c.physical_capacity                                         as physical_capacity,

    -- Narrative fields (captains_log_entries only)
    c.what_happened                                             as what_happened,
    c.what_changed                                              as what_changed,
    c.wins                                                      as wins,
    c.blockers                                                  as blockers,
    c.decisions_made                                            as decisions_made,
    c.tomorrows_priority                                        as tomorrows_priority,
    c.overall_note                                              as overall_note,

    -- Operational fields (health_daily_logs enriched fields)
    d.movement_notes                                            as movement_notes,
    d.work_location                                             as work_location,
    d.sitting_tolerance_minutes                                 as sitting_tolerance_minutes,
    coalesce(d.workload_constraint, 'unknown')                  as workload_constraint,
    d.notes                                                     as notes,

    -- RAG status fields (captains_log_entries only)
    c.health_status                                             as health_status,
    c.work_status                                               as work_status,
    c.personal_status                                           as personal_status,
    c.captain_capacity_rating                                   as captain_capacity_rating,

    -- Source provenance
    case
        when c.log_date is not null and d.log_date is not null then 'both'
        when c.log_date is not null                            then 'captains_log'
        else                                                        'health_daily_logs'
    end                                                         as data_source,

    -- Timestamps
    coalesce(c.created_at, d.created_at)                        as created_at

from
    captains_log_entries c
    full outer join health_daily_logs d on c.log_date = d.log_date

order by
    coalesce(c.log_date, d.log_date) desc;


comment on view analytics_health_daily is
    'Unified daily health analytics view. '
    'Merges captains_log_entries (reflective journal) and health_daily_logs '
    '(operational Slack check-in) on log_date via FULL OUTER JOIN. '
    'captains_log_entries fields take precedence on conflict. '
    'Energy and mood normalised to Title Case from health_daily_logs lowercase. '
    'ADR-HEALTH-001: this view is the canonical analytics input for '
    'weekly_synthesis.py and all downstream intelligence pipelines.';


-- ── Extend workload_constraint check constraint (WP-5) ────────────────────
-- Add 'modified' as a valid value for the AMBER state (three-tier signal).
-- The original constraint only allows 'reduced', 'normal', 'unknown'.
-- This ALTER is idempotent when run via IF NOT EXISTS equivalent approach:
-- drop and recreate the constraint.

alter table health_daily_logs
    drop constraint if exists health_daily_logs_workload_constraint_check;

alter table health_daily_logs
    add constraint health_daily_logs_workload_constraint_check
    check (workload_constraint in ('reduced', 'modified', 'normal', 'unknown'));
