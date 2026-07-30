-- ============================================================
-- Migration 0005 — captains_log_entries
-- ADR: ADR-HEALTH-001 (Health Data Architecture)
-- Date: 2026-06-13
--
-- PURPOSE
-- Formalises the captains_log_entries table schema that has been
-- operational in production without version-controlled DDL.
-- This migration is a schema capture, not a new table creation —
-- the table already exists. Use CREATE TABLE IF NOT EXISTS so the
-- migration is idempotent if run against production.
--
-- ARCHITECTURE CONTEXT (ADR-HEALTH-001, Option B)
-- captains_log_entries is the PRIMARY reflective health journal.
-- health_daily_logs remains a separate operational check-in table.
-- Both tables are permanent under the approved dual-purpose architecture.
-- Integration occurs via analytics_health_daily (view, migration 0006).
--
-- PRIVACY BOUNDARY
-- This table stores summary-level personal health data ONLY.
-- Prohibited fields (same as health_daily_logs):
--   - diagnosis or diagnoses
--   - medication names, doses, or prescription details
--   - clinical notes or imaging findings verbatim
--   - provider identifying information beyond a display name
--
-- APPLY: Supabase SQL editor or supabase db push
-- ============================================================

-- ── captains_log_entries ─────────────────────────────────────
-- One row per calendar day. Upserted on conflict with log_date.
-- Source: Captain's Log UI (captains-log.html) and Slack bridge.
-- Purpose: Reflective daily journal with narrative context,
--          rich health observations, and operational intent.

create table if not exists captains_log_entries (
  id                    uuid primary key default gen_random_uuid(),
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),

  -- ── Identity ────────────────────────────────────────────
  log_date              date not null default current_date,

  -- ── Pain (summary-level; no clinical labels or diagnoses) ──
  pain_score            smallint check (pain_score between 0 and 10),
  pain_location         text,       -- descriptive only, e.g. "lower back, legs"

  -- ── Energy and mood ─────────────────────────────────────
  -- Title Case enums (distinct from health_daily_logs lowercase convention)
  energy                text check (energy in ('Low', 'Moderate', 'High')),
  mood                  text check (mood in ('Low', 'Stable', 'Positive')),

  -- ── Sleep ───────────────────────────────────────────────
  sleep_hours           numeric(4,1) check (sleep_hours between 0 and 24),
  sleep_quality         text check (sleep_quality in ('Poor', 'Fair', 'Good')),
  cpap_status           text check (cpap_status in ('Yes', 'No', 'Partial', 'Not applicable')),

  -- ── Physical state ──────────────────────────────────────
  physical_capacity     text check (physical_capacity in ('Better', 'Same', 'Worse')),
                        -- Relative day-on-day self-assessment

  -- ── Narrative fields (free text, write-protected by API whitelist) ──
  what_happened         text,       -- key events of the day
  what_changed          text,       -- symptom or context changes
  wins                  text,       -- positive outcomes and achievements
  blockers              text,       -- operational and health blockers
  decisions_made        text,       -- decisions taken today
  tomorrows_priority    text,       -- forward intent for next day
  overall_note          text,       -- end-of-day synthesis note

  -- ── RAG status fields (captain-entered, not computed) ───
  -- These are self-assessed; capacity score is computed separately
  health_status         text check (health_status in ('Green', 'Amber', 'Red')),
  work_status           text check (work_status in ('Green', 'Amber', 'Red')),
  personal_status       text check (personal_status in ('Green', 'Amber', 'Red')),

  -- ── Calibration ─────────────────────────────────────────
  captain_capacity_rating text check (captain_capacity_rating in ('Green', 'Amber', 'Red')),
                        -- Captain's self-assessed capacity; compared to
                        -- computed capacity_score by calibration_engine.py

  -- ── Source ──────────────────────────────────────────────
  source                text not null default 'ui'
                        check (source in ('ui', 'slack', 'manual', 'import'))
);

-- ── Uniqueness ───────────────────────────────────────────────
-- One reflective journal entry per calendar day.
-- Upsert behaviour: ON CONFLICT (log_date) DO UPDATE (merge-duplicates).
create unique index if not exists captains_log_entries_log_date_uniq
  on captains_log_entries (log_date);

-- ── Query indexes ─────────────────────────────────────────────
-- Date-range scans are the primary access pattern (7-day, 30-day windows).
create index if not exists captains_log_entries_log_date_desc_idx
  on captains_log_entries (log_date desc);

create index if not exists captains_log_entries_created_at_idx
  on captains_log_entries (created_at desc);

-- Pain score index for threshold queries (pain >= 7, consecutive day detection).
create index if not exists captains_log_entries_pain_score_idx
  on captains_log_entries (pain_score)
  where pain_score is not null;

-- ── Updated-at trigger ────────────────────────────────────────
-- Reuses the trigger function defined in HEALTH-FOUNDATION-SCHEMA.sql.
-- If that function doesn't exist yet, it will be created here.
create or replace function update_captains_log_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger captains_log_entries_updated_at
  before update on captains_log_entries
  for each row execute function update_captains_log_updated_at();

-- ── Table and column comments ──────────────────────────────────
comment on table captains_log_entries is
  'Primary reflective daily health and operational journal. '
  'One row per calendar day. Upserted by log_date. '
  'Privacy boundary: summary-level only; no clinical data, diagnoses, or medication specifics. '
  'ADR-HEALTH-001: permanent dual-purpose table alongside health_daily_logs.';

comment on column captains_log_entries.log_date is
  'Calendar date (YYYY-MM-DD). Unique conflict key for upsert.';

comment on column captains_log_entries.energy is
  'Title Case enum (Low/Moderate/High). Distinct from health_daily_logs which uses lowercase. '
  'The analytics_health_daily view normalises both to lowercase for cross-table queries.';

comment on column captains_log_entries.mood is
  'Title Case enum (Low/Stable/Positive). See energy column comment for case convention.';

comment on column captains_log_entries.physical_capacity is
  'Relative day-on-day self-assessment (Better/Same/Worse). '
  'Not an absolute score — context depends on recent baseline. '
  'Consumed by capacity_score.py WEIGHTS dict.';

comment on column captains_log_entries.captain_capacity_rating is
  'Captain self-assessed operational capacity (Green/Amber/Red). '
  'Compared to computed capacity_score by calibration_engine.py '
  'to derive model_accuracy_pct and weighting_review_flag.';

comment on column captains_log_entries.health_status is
  'Captain-entered RAG status. Not computed — not validated against pain_score. '
  'Deliberately separate from capacity_status to capture subjective state.';

comment on column captains_log_entries.source is
  'Origin of this entry: ui (Captain''s Log form), slack (bridge), '
  'manual (direct entry), import (bulk load).';
