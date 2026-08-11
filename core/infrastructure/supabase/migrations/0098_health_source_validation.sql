-- Migration 0098: health source validation loop
--
-- health_source_registry's replication_success_rate/retraction_rate (inputs
-- to the reliability_score formula) were static values hand-set at
-- seed/auto-registration time, with no mechanism to update them from real
-- evidence — the exact same "SRS scoring inert" shape found and fixed on
-- the technical workbench this session. Adding a validation table + tracking
-- columns so a daily job can turn these into real, evolving values.

CREATE TABLE IF NOT EXISTS health_signal_validation (
  validation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  signal_id UUID NOT NULL REFERENCES health_signals(signal_id) ON DELETE CASCADE,
  source_id UUID NOT NULL REFERENCES health_source_registry(source_id) ON DELETE CASCADE,
  is_accurate BOOLEAN,
  validation_method TEXT,
  validation_detail TEXT,
  validated_at TIMESTAMPTZ DEFAULT now(),
  validated_by TEXT DEFAULT 'system'
);

COMMENT ON TABLE health_signal_validation IS
  'Tracks heuristic validation of health_signals, mirroring intelligence_event_validation. '
  'Used to recompute replication_success_rate/retraction_rate for each source from real evidence '
  'instead of leaving them at static seed-time defaults forever.';

CREATE INDEX IF NOT EXISTS idx_health_signal_validation_source
  ON health_signal_validation(source_id, validated_at DESC);

ALTER TABLE health_source_registry ADD COLUMN IF NOT EXISTS accuracy_sample_size INT DEFAULT 0;
ALTER TABLE health_source_registry ADD COLUMN IF NOT EXISTS accuracy_last_updated TIMESTAMPTZ;

ALTER TABLE health_signal_validation ENABLE ROW LEVEL SECURITY;
CREATE POLICY "authenticated can read health_signal_validation"
  ON health_signal_validation FOR SELECT USING (auth.role() = 'authenticated');
GRANT SELECT ON health_signal_validation TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON health_signal_validation TO service_role;
