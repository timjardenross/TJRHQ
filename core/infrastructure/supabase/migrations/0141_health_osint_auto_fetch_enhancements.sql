-- Health OSINT Phase 1: schema for TJR MIND & Body alignment + automated fetching.
-- Per HEALTH_OSINT_IMPLEMENTATION.md section 2. health_domain/signal_type on
-- health_signals are free-text (no existing CHECK), so no constraint update needed.

ALTER TABLE health_signals
  ADD COLUMN IF NOT EXISTS contributing_factor_type VARCHAR(50),
  ADD COLUMN IF NOT EXISTS auto_ingested BOOLEAN DEFAULT false;

ALTER TABLE health_signals
  ADD CONSTRAINT contributing_factor_type_check CHECK (
    contributing_factor_type IN ('sleep', 'stress', 'nutrition', 'training', 'environment')
    OR contributing_factor_type IS NULL
  );

CREATE INDEX IF NOT EXISTS idx_health_signals_auto_ingested
  ON health_signals(auto_ingested, collected_at DESC);

-- ─── health_source_fetch_config ──────────────────────────────────────────
-- Tracks which health_source_registry entries are auto-fetched, their
-- scrape tool/cadence/parser, and per-source monthly request budget.

CREATE TABLE IF NOT EXISTS health_source_fetch_config (
  config_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID NOT NULL REFERENCES health_source_registry(source_id) ON DELETE CASCADE,

  fetch_tool VARCHAR(50) NOT NULL,      -- firecrawl | bright_data | manual
  fetch_url TEXT,
  cadence VARCHAR(50) NOT NULL,         -- daily | weekly | 2x/week | 3x/week
  parser_function VARCHAR(255),

  monthly_budget INTEGER,
  requests_used INTEGER DEFAULT 0,
  budget_reset_date DATE DEFAULT CURRENT_DATE,

  dedup_field VARCHAR(50),              -- title | md5_title | doi

  auto_publish BOOLEAN DEFAULT false,
  default_confidence_level VARCHAR(10),

  last_fetch TIMESTAMPTZ,
  last_fetch_status VARCHAR(50),        -- success | failed | skipped
  last_fetch_message TEXT,

  active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_health_source_fetch_active
  ON health_source_fetch_config(active, fetch_tool);

-- ─── RLS: same pattern as migration 0093 (auth.role() = 'authenticated'
-- for reads, service_role for writes; ENABLE is mandatory, a policy alone
-- does nothing) ─────────────────────────────────────────────────────────

ALTER TABLE health_source_fetch_config ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated can read health_source_fetch_config"
  ON health_source_fetch_config FOR SELECT
  USING (auth.role() = 'authenticated');

GRANT SELECT ON health_source_fetch_config TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON health_source_fetch_config TO service_role;
