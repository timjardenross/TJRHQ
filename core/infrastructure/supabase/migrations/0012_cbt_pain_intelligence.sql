-- ============================================================
-- Migration 0012 — CBT Pain Intelligence Fields
-- Research basis: MSN-20260613-102725 (chronic pain journal research)
-- Recommendation: Option 2 — Structured CBT-Integrated Journal
-- Date: 2026-06-13
--
-- PURPOSE
-- Adds four CBT-aligned fields to captains_log_entries to enable
-- systematic tracking of pain triggers, pain relievers, coping
-- strategies, and activity impact. These fields feed into
-- narrative_intelligence.py pattern extraction and weekly_synthesis
-- for evidence-based pain self-management intelligence.
--
-- PRIVACY BOUNDARY (same as captains_log_entries)
-- Free-text fields — summary-level only. No clinical diagnoses,
-- medication names, or provider information.
--
-- APPLY: Supabase SQL editor or supabase db push
-- ============================================================

-- ── CBT Pain Intelligence columns ────────────────────────────
-- Additive only — existing rows unaffected (NULLable columns).

alter table captains_log_entries
  add column if not exists pain_triggers    text,
  add column if not exists pain_relievers   text,
  add column if not exists coping_strategies text,
  add column if not exists activity_impact  text;

-- ── Column comments ───────────────────────────────────────────
comment on column captains_log_entries.pain_triggers is
  'CBT behavioral tracking: what activities, postures, or events worsened pain today. '
  'Free text. Feeds narrative_intelligence.py trigger pattern extraction. '
  'Prompt: "What worsened your pain today?"';

comment on column captains_log_entries.pain_relievers is
  'CBT behavioral tracking: what actions or conditions relieved or managed pain. '
  'Free text. Feeds narrative_intelligence.py reliever pattern extraction. '
  'Prompt: "What helped your pain today?"';

comment on column captains_log_entries.coping_strategies is
  'CBT coping strategy log: techniques used today (e.g. pacing, heat, rest, movement). '
  'Free text. Tracked across entries to identify effective strategy patterns. '
  'Prompt: "What coping strategies did you use today?"';

comment on column captains_log_entries.activity_impact is
  'CBT behavioral experiment log: activities attempted and their effect on pain/capacity. '
  'Free text. Used for activity pacing analysis in narrative intelligence. '
  'Prompt: "Which activities did you try, and how did they affect you?"';
