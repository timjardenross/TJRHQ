-- ============================================================
-- Migration 0007 — health_events FK repair
-- ADR: ADR-HEALTH-001 decision: health_events.linked_log_id
--      should reference captains_log_entries (richer reflective record)
-- Date: 2026-06-13
--
-- PROBLEM
-- health_events.linked_log_id currently references health_daily_logs(id).
-- All current writes go to captains_log_entries, not health_daily_logs,
-- so the FK join returns zero matches for all live event records.
--
-- FIX
-- Drop the existing FK constraint and add a new one pointing to
-- captains_log_entries(id). ON DELETE SET NULL preserves event records
-- if the linked journal entry is deleted.
--
-- ALSO: Add pharmacy to the event_type check constraint (WP-6 + prior
-- Pharmacy event type added in health_event.py but not in the DB enum).
--
-- APPLY: Supabase SQL editor or supabase db push
-- ============================================================


-- ── Drop existing FK referencing health_daily_logs ────────────────────────
-- The constraint may have been auto-named by Postgres; try both naming
-- conventions.
alter table health_events
    drop constraint if exists health_events_linked_log_id_fkey;

alter table health_events
    drop constraint if exists health_events_linked_log_id_fk;


-- ── Add FK referencing captains_log_entries ───────────────────────────────
alter table health_events
    add constraint health_events_linked_log_id_fkey
    foreign key (linked_log_id)
    references captains_log_entries(id)
    on delete set null;


-- ── Add pharmacy to event_type check constraint ───────────────────────────
-- Drop and recreate event_type check to include 'pharmacy'.
-- The original schema in HEALTH-FOUNDATION-SCHEMA.sql did not include it.
alter table health_events
    drop constraint if exists health_events_event_type_check;

alter table health_events
    add constraint health_events_event_type_check
    check (event_type in (
        'appointment',
        'procedure',
        'surgery',
        'imaging_ordered',
        'medication_change',
        'symptom_onset',
        'symptom_change',
        'recovery_milestone',
        'referral',
        'pharmacy',
        'other'
    ));


comment on column health_events.linked_log_id is
    'FK to captains_log_entries(id) — the richer reflective record most '
    'likely to contain narrative context about this health event. '
    'ON DELETE SET NULL: event is preserved if the journal entry is removed. '
    'ADR-HEALTH-001: FK target updated from health_daily_logs to '
    'captains_log_entries (migration 0007).';
