-- ============================================================
-- Migration 0022 — Human Systems friction register (HSF-002 WP4)
-- Persists detected recurring causes of capacity loss so friction
-- accumulates over time and can be reviewed. Additive + idempotent.
-- ============================================================

CREATE TABLE IF NOT EXISTS human_systems_friction (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  observed_on   date NOT NULL DEFAULT CURRENT_DATE,
  friction_key  text NOT NULL,          -- short_sleep_next_day | nervous_system_run | recovery_debt | sleep_debt_avg | ...
  description   text NOT NULL,          -- the pattern, framed as information
  lever         text NOT NULL,          -- the actionable change
  confidence    numeric(4,3) NOT NULL DEFAULT 0.5
                  CHECK (confidence >= 0 AND confidence <= 1),
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_hs_friction_key
  ON human_systems_friction (friction_key, observed_on DESC);

COMMENT ON TABLE human_systems_friction IS
  'HSF-002 WP4: friction register — recurring causes of capacity loss detected '
  'by the Decision Engine. Non-diagnostic; patterns are information, not verdicts.';
