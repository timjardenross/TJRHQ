-- ============================================================
-- USS TJR Health Data Foundation Schema
-- Mission: Health Data Foundation (Step 1)
-- ============================================================
--
-- PRIVACY BOUNDARY
-- This schema stores summary-level health data ONLY.
-- Clinical documents, imaging, specialist letters, GP notes
-- are NEVER stored here — they remain in memory/health/documents/
-- (local filesystem only).
--
-- Fields that are PROHIBITED in this schema:
--   - diagnosis or diagnoses
--   - prescription or medication name/dose
--   - clinical notes or imaging findings verbatim
--   - provider identifying information beyond a display name
--   - any field that could constitute a medical record
--
-- Apply in Supabase SQL editor.
-- ============================================================

-- ── health_daily_logs ─────────────────────────────────────
-- One row per daily check-in. Summary-level only.
-- Source: /health-check Slack command (Step 2).

create table if not exists health_daily_logs (
  id              uuid primary key default gen_random_uuid(),
  logged_at       timestamptz not null default now(),
  log_date        date not null default current_date,

  -- Pain (summary level — no location diagnosis, no clinical labels)
  pain_score      smallint check (pain_score between 0 and 10),
  pain_location   text,           -- e.g. "lower back", "legs" — descriptive only
  pain_notes      text,           -- max 500 chars, enforced below

  -- Energy & mood
  energy          text check (energy in ('low', 'moderate', 'high')),
  mood            text check (mood in ('low', 'stable', 'positive')),

  -- Sleep
  sleep_hours     numeric(4,1) check (sleep_hours between 0 and 24),
  sleep_quality   text check (sleep_quality in ('poor', 'fair', 'good')),
  cpap_used       boolean,
  cpap_hours      numeric(4,1) check (cpap_hours between 0 and 24),

  -- Activity
  movement_notes  text,           -- e.g. "short walk", "stretching" — max 300 chars

  -- Context (summary only — no medication names or doses)
  medication_notes text,          -- e.g. "as prescribed", "pain relief taken" — no specifics
  notes           text,           -- free-form, max 1000 chars

  -- Workload impact (feeds COP constraint)
  workload_constraint text check (workload_constraint in ('reduced', 'normal', 'unknown'))
                       default 'unknown',

  -- Source and metadata
  source          text not null default 'manual'
                  check (source in ('slack', 'manual', 'import')),
  created_at      timestamptz not null default now()
);

-- Enforce text length constraints via check
alter table health_daily_logs
  add constraint pain_notes_length    check (char_length(pain_notes) <= 500),
  add constraint movement_notes_length check (char_length(movement_notes) <= 300),
  add constraint medication_notes_length check (char_length(medication_notes) <= 300),
  add constraint notes_length         check (char_length(notes) <= 1000);

-- One log per calendar day (prevent duplicates; update via upsert)
create unique index if not exists health_daily_logs_date_uniq
  on health_daily_logs (log_date);

-- Time-series query index
create index if not exists health_daily_logs_logged_at_idx
  on health_daily_logs (logged_at desc);


-- ── health_events ─────────────────────────────────────────
-- Timeline of significant health events.
-- Supports "when did X first appear?" and appointment history.

create table if not exists health_events (
  id              uuid primary key default gen_random_uuid(),
  event_date      date not null,
  event_type      text not null check (event_type in (
                    'appointment',
                    'procedure',
                    'surgery',
                    'imaging_ordered',    -- ordered; result stored locally
                    'medication_change',  -- summary only, no drug names
                    'symptom_onset',
                    'symptom_change',
                    'recovery_milestone',
                    'referral',
                    'other'
                  )),

  title           text not null,          -- e.g. "Spine review with specialist"
  description     text,                   -- summary, max 2000 chars
  provider        text,                   -- display name only, e.g. "Spine Specialist"
  outcome         text,                   -- e.g. "Follow-up MRI ordered"
  follow_up_required boolean default false,
  follow_up_date  date,
  follow_up_notes text,

  -- Link back to the daily log for the same day if one exists
  linked_log_id   uuid references health_daily_logs(id) on delete set null,

  -- Local document reference (path only — no content in Supabase)
  local_document_path text,        -- e.g. "memory/health/documents/2026-06-12-mri-order.pdf"
                                   -- path pointer only; file stays local

  source          text not null default 'manual'
                  check (source in ('slack', 'manual', 'import')),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

alter table health_events
  add constraint description_length  check (char_length(description) <= 2000),
  add constraint outcome_length      check (char_length(outcome) <= 1000);

-- Timeline queries
create index if not exists health_events_date_idx
  on health_events (event_date desc);

create index if not exists health_events_type_idx
  on health_events (event_type);


-- ── health_insights ───────────────────────────────────────
-- AI-generated pattern summaries and trend observations.
-- Written by the weekly synthesis job; read by health adapter.

create table if not exists health_insights (
  id              uuid primary key default gen_random_uuid(),
  generated_at    timestamptz not null default now(),
  period_start    date not null,
  period_end      date not null,
  insight_type    text not null check (insight_type in (
                    'weekly_summary',
                    'pain_trend',
                    'energy_trend',
                    'sleep_trend',
                    'trigger_pattern',
                    'activity_correlation',
                    'appointment_prep'
                  )),

  -- Plain-language summary (feeds Health-Summary.md and COP)
  summary         text not null,

  -- Structured supporting data (aggregates, not raw logs)
  supporting_data jsonb not null default '{}'::jsonb,
  -- Expected shape: { avg_pain, pain_trend, avg_sleep_hours,
  --                   energy_distribution, log_count, event_count }

  -- Which model generated this
  generated_by    text default 'manual',

  -- The Health-Summary.md content generated for this period
  health_summary_md text,         -- full markdown block, written to file on generation

  created_at      timestamptz not null default now()
);

-- Prevent duplicate insight types for the same period
create unique index if not exists health_insights_period_type_uniq
  on health_insights (period_start, period_end, insight_type);

-- Recent-first queries
create index if not exists health_insights_generated_at_idx
  on health_insights (generated_at desc);


-- ── updated_at trigger (health_events) ────────────────────

create or replace function update_updated_at_column()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger health_events_updated_at
  before update on health_events
  for each row execute function update_updated_at_column();


-- ── row-level comments ────────────────────────────────────

comment on table health_daily_logs is
  'Summary-level daily health check-ins. No clinical data. Privacy boundary enforced via constraints.';

comment on table health_events is
  'Timeline of significant health events. local_document_path is a pointer only — files remain local.';

comment on table health_insights is
  'AI-generated health summaries and trend observations. Feeds Health-Summary.md auto-generation.';

comment on column health_events.local_document_path is
  'Path pointer to a local file only. Clinical documents are NEVER uploaded to Supabase.';
