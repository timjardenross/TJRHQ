-- ============================================================
-- Migration 0020 — Human Systems Framework
-- HSF-001 — Human Systems Doctrine (extends ROS-001 v1.1)
-- Date: 2026-06-20
--
-- Adds the Human Systems data model:
--   1. Energy-domain + capacity columns on health_daily_logs
--   2. human_systems_recommendations  — proactive output issued
--   3. human_systems_feedback         — Captain feedback on usefulness
--   4. human_systems_patterns         — significant patterns / preferences / triggers
--   5. human_systems_daily            — convenience view over analytics_health_daily
--
-- All additive and idempotent. Privacy-first: sensitive context lives in the
-- existing health tables; these tables store the system's reasoning artefacts.
--
-- STATUS: Ready to apply via Supabase MCP / CLI.
-- ============================================================

-- ── 1. Energy-domain + capacity columns on health_daily_logs ─────────────────
-- Optional Captain-entered or system-derived energy-budget signals (doctrine §8).
-- Bands follow the framework engine: good | moderate | limited | depleted.
-- Nullable throughout — absence means unrecorded and the engine derives a value.

ALTER TABLE health_daily_logs
  ADD COLUMN IF NOT EXISTS energy_physical text
    CHECK (energy_physical IN ('good','moderate','limited','depleted'));
ALTER TABLE health_daily_logs
  ADD COLUMN IF NOT EXISTS energy_cognitive text
    CHECK (energy_cognitive IN ('good','moderate','limited','depleted'));
ALTER TABLE health_daily_logs
  ADD COLUMN IF NOT EXISTS energy_emotional text
    CHECK (energy_emotional IN ('good','moderate','limited','depleted'));
ALTER TABLE health_daily_logs
  ADD COLUMN IF NOT EXISTS energy_social text
    CHECK (energy_social IN ('good','moderate','limited','depleted'));

ALTER TABLE health_daily_logs
  ADD COLUMN IF NOT EXISTS daily_capacity_score numeric(5,2)
    CHECK (daily_capacity_score >= 0 AND daily_capacity_score <= 100);

ALTER TABLE health_daily_logs
  ADD COLUMN IF NOT EXISTS movement_completed boolean;
ALTER TABLE health_daily_logs
  ADD COLUMN IF NOT EXISTS nutrition_anchors_completed smallint
    CHECK (nutrition_anchors_completed >= 0 AND nutrition_anchors_completed <= 10);
ALTER TABLE health_daily_logs
  ADD COLUMN IF NOT EXISTS recovery_actions text;

COMMENT ON COLUMN health_daily_logs.daily_capacity_score IS
  'HSF-001 §8: Operational roll-up of the four energy domains plus ROS recovery '
  'posture (0–100). Answers "what can I safely do today?" — never "what must I do?". '
  'Nullable — engine derives when absent.';
COMMENT ON COLUMN health_daily_logs.movement_completed IS
  'HSF-001 Movement domain: did any movement happen today? Consistency signal, '
  'never a target or grade. Nullable.';
COMMENT ON COLUMN health_daily_logs.nutrition_anchors_completed IS
  'HSF-001 Nutrition domain: count of nutrition anchors met (e.g. protein, '
  'hydration, regular timing). Support signal, not restriction. Nullable.';
COMMENT ON COLUMN health_daily_logs.recovery_actions IS
  'HSF-001: free-text note of recovery actions taken (resets, wind-down, rest). '
  'Nullable.';

-- ── 2. human_systems_recommendations ─────────────────────────────────────────
-- Every proactive recommendation / push surfaced to the Captain (doctrine §Memory).

CREATE TABLE IF NOT EXISTS human_systems_recommendations (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  issued_on    date NOT NULL DEFAULT CURRENT_DATE,
  kind         text NOT NULL,        -- readiness | reflection | weekly_review | degradation | plan_* | escalation
  domain       text,                 -- medical | movement | nutrition | mind | performance | resilience
  output_class text NOT NULL DEFAULT 'information'
                 CHECK (output_class IN ('information','trend','risk_signal','action')),
  summary      text NOT NULL,
  source       text NOT NULL DEFAULT 'system'   -- system | captain_pull | scheduler
                 CHECK (source IN ('system','captain_pull','scheduler')),
  user_id      text,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_hs_recs_issued_on
  ON human_systems_recommendations (issued_on DESC);

COMMENT ON TABLE human_systems_recommendations IS
  'HSF-001: log of proactive recommendations / pushes issued to the Captain. '
  'Supports "store proactive recommendations issued" and personalisation over time.';

-- ── 3. human_systems_feedback ────────────────────────────────────────────────
-- Captain feedback on usefulness, including rejected / unhelpful guidance.

CREATE TABLE IF NOT EXISTS human_systems_feedback (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  given_on    date NOT NULL DEFAULT CURRENT_DATE,
  summary     text NOT NULL,
  useful      boolean NOT NULL,
  note        text,
  domain      text,
  user_id     text,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_hs_feedback_useful
  ON human_systems_feedback (useful, created_at DESC);

COMMENT ON TABLE human_systems_feedback IS
  'HSF-001: Captain feedback on recommendation usefulness. Stores rejected / '
  'unhelpful guidance too, so the system can avoid repeating it.';

-- ── 4. human_systems_patterns ────────────────────────────────────────────────
-- Significant patterns, preferences, effective interventions, recurring triggers.

CREATE TABLE IF NOT EXISTS human_systems_patterns (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  observed_on  date NOT NULL DEFAULT CURRENT_DATE,
  pattern_type text NOT NULL
                 CHECK (pattern_type IN ('pattern','preference','intervention','trigger','rejected')),
  description  text NOT NULL,
  domain       text,
  user_id      text,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_hs_patterns_type
  ON human_systems_patterns (pattern_type, created_at DESC);

COMMENT ON TABLE human_systems_patterns IS
  'HSF-001 Command Memory integration: significant patterns, Captain preferences, '
  'effective interventions, recurring triggers, and rejected recommendations.';

-- ── 5. human_systems_daily view ──────────────────────────────────────────────
-- Convenience surface for the dashboard / engine: the unified daily health row
-- plus the new energy-domain + capacity columns from health_daily_logs.

CREATE OR REPLACE VIEW human_systems_daily AS
SELECT
  a.*,
  d.energy_physical,
  d.energy_cognitive,
  d.energy_emotional,
  d.energy_social,
  d.daily_capacity_score,
  d.movement_completed,
  d.nutrition_anchors_completed,
  d.recovery_actions
FROM analytics_health_daily a
LEFT JOIN health_daily_logs d ON d.log_date = a.log_date;

COMMENT ON VIEW human_systems_daily IS
  'HSF-001: analytics_health_daily extended with Human Systems energy-domain and '
  'capacity columns. Primary read surface for the Human Systems dashboard panel.';
