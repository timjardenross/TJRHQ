-- ============================================================
-- Migration 0086 — Health-Mission Correlation Results Storage
-- USS Starship Endeavour NCC-170230
--
-- Issue 17: Persistent storage for health × mission correlations.
-- Pure statistics (Pearson correlation, deterministic).
-- Results computed daily, displayed on Home/Intelligence dashboard.
--
-- Additive & idempotent. Safe to run repeatedly.
-- ============================================================

create table if not exists intelligence_health_correlations (
  id                  uuid primary key default gen_random_uuid(),
  computed_at         timestamptz not null default now(),
  status              text check (status in ('ok', 'insufficient_data')),
  n_health_entries    int,
  n_mission_days      int,
  correlations        jsonb,  -- {pain_vs_mission_activity: {r, interpretation, n}, ...}
  findings            jsonb,  -- array of finding strings
  pain_productivity_answer text,  -- narrative answer to "does pain affect productivity?"
  created_at          timestamptz not null default now()
);

comment on table intelligence_health_correlations is
  'Issue 17: Daily health-mission correlation results. Pure statistics (no LLM). '
  'Persists output of core.intelligence.health_mission_correlation.compute_health_mission_correlations(). '
  'Displayed on Home dashboard or dedicated Intelligence dashboard.';

comment on column intelligence_health_correlations.correlations is
  'Structured results from Pearson correlation analysis: '
  '{pain_vs_mission_activity, energy_vs_mission_activity, sleep_vs_next_day_mission_activity, '
  'cpap_vs_next_day_productivity, mood_vs_mission_activity}. Each has {r, interpretation, n, note}.';

comment on column intelligence_health_correlations.findings is
  'Array of human-readable finding strings, e.g. '
  '[''PAIN-PRODUCTIVITY: Captain updates 2.3 more missions on low-pain days...'', '
  '''ENERGY→ACTIVITY: r=0.45 (moderate_positive, n=67)'']';

create index if not exists idx_health_corr_computed_at on intelligence_health_correlations(computed_at desc);
