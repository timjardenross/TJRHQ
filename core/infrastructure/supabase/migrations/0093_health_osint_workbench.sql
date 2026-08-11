-- Migration 0093: Health/Human Performance OSINT Workbench
--
-- Adapts the technical OSINT workbench (intelligence_events /
-- intelligence_source_registry) to the health/clinical domain per
-- HEALTH_OSINT_WORKBENCH.md. Additive only — no existing tables touched.

-- ─── health_source_registry ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS health_source_registry (
  source_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_name TEXT NOT NULL,
  source_type VARCHAR(50),           -- journal | clinical_trial_db | health_agency | researcher | institution | manufacturer
  source_url TEXT,

  peer_reviewed BOOLEAN DEFAULT false,
  impact_factor FLOAT,
  publisher_reputation FLOAT DEFAULT 0.50,  -- 0-1, hand-curated

  conflict_of_interest_disclosure BOOLEAN DEFAULT false,
  funding_transparency FLOAT DEFAULT 0.50,  -- 0-1

  replication_success_rate FLOAT DEFAULT 0.50,  -- 0-1
  retraction_rate FLOAT DEFAULT 0.05,           -- 0-1, lower is better

  -- study-methodology inputs used for the SRS methodology_quality term
  -- (per-source average, since methodology varies by study we don't track
  -- individual study_design here — see health_signals.methodology_quality_score
  -- for the per-signal figure)
  avg_methodology_quality FLOAT DEFAULT 0.50,   -- 0-1

  -- Health_SRS = publisher_reputation
  --            × (1.2 if peer_reviewed else 0.8)
  --            × avg_methodology_quality
  --            × ((replication_success_rate × 0.5) + (1 - retraction_rate × 0.3))
  --            × ((conflict_of_interest_disclosure × 0.5) + (funding_transparency × 0.5))
  reliability_score NUMERIC(4, 3) GENERATED ALWAYS AS (
    ROUND((
      publisher_reputation
      * (CASE WHEN peer_reviewed THEN 1.2 ELSE 0.8 END)
      * avg_methodology_quality
      * ((replication_success_rate * 0.5) + (1.0 - retraction_rate * 0.3))
      * ((CASE WHEN conflict_of_interest_disclosure THEN 1.0 ELSE 0.0 END * 0.5) + (funding_transparency * 0.5))
    )::NUMERIC, 3)
  ) STORED,

  reliability_tier TEXT GENERATED ALWAYS AS (
    CASE
      WHEN (
        publisher_reputation
        * (CASE WHEN peer_reviewed THEN 1.2 ELSE 0.8 END)
        * avg_methodology_quality
        * ((replication_success_rate * 0.5) + (1.0 - retraction_rate * 0.3))
        * ((CASE WHEN conflict_of_interest_disclosure THEN 1.0 ELSE 0.0 END * 0.5) + (funding_transparency * 0.5))
      ) > 0.85 THEN 'TIER_1'
      WHEN (
        publisher_reputation
        * (CASE WHEN peer_reviewed THEN 1.2 ELSE 0.8 END)
        * avg_methodology_quality
        * ((replication_success_rate * 0.5) + (1.0 - retraction_rate * 0.3))
        * ((CASE WHEN conflict_of_interest_disclosure THEN 1.0 ELSE 0.0 END * 0.5) + (funding_transparency * 0.5))
      ) > 0.65 THEN 'TIER_2'
      WHEN (
        publisher_reputation
        * (CASE WHEN peer_reviewed THEN 1.2 ELSE 0.8 END)
        * avg_methodology_quality
        * ((replication_success_rate * 0.5) + (1.0 - retraction_rate * 0.3))
        * ((CASE WHEN conflict_of_interest_disclosure THEN 1.0 ELSE 0.0 END * 0.5) + (funding_transparency * 0.5))
      ) > 0.45 THEN 'TIER_3'
      ELSE 'TIER_4'
    END
  ) STORED,

  last_updated TIMESTAMPTZ DEFAULT now(),
  accuracy_last_updated TIMESTAMPTZ
);

COMMENT ON TABLE health_source_registry IS
  'Health/clinical OSINT source registry. reliability_score/tier are GENERATED per the Health_SRS formula in HEALTH_OSINT_WORKBENCH.md section 3.';

CREATE INDEX IF NOT EXISTS idx_health_source_registry_tier
  ON health_source_registry(reliability_tier, reliability_score DESC);

-- ─── health_signals ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS health_signals (
  signal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  description TEXT,
  signal_type VARCHAR(50) NOT NULL,   -- study_result | adverse_event | outbreak | efficacy_claim | safety_alert
  health_domain VARCHAR(50) NOT NULL, -- epidemiology | treatment | supplement | performance | mental_health | vaccine

  study_design VARCHAR(50),           -- RCT | observational | case_study | meta_analysis | anecdotal
  sample_size INTEGER,
  population_description TEXT,
  p_value FLOAT,
  effect_size FLOAT,
  confidence_interval_lower FLOAT,
  confidence_interval_upper FLOAT,

  methodology_quality_score FLOAT,    -- 0-1, per-signal (study_design + sample_size + rigor)
  replication_count INTEGER DEFAULT 0,
  replication_success_rate FLOAT,     -- 0-1

  rank_score FLOAT DEFAULT 50,        -- 0-100 sort order
  confidence_level VARCHAR(10),       -- HIGH | MEDIUM | LOW | UNKNOWN

  severity VARCHAR(20),               -- mild | moderate | severe | critical
  adverse_event_text TEXT,
  fda_flagged BOOLEAN DEFAULT false,
  frequency_reported INTEGER,

  source_id UUID NOT NULL REFERENCES health_source_registry(source_id) ON DELETE CASCADE,
  collected_at TIMESTAMPTZ DEFAULT now(),
  published_at TIMESTAMPTZ,
  suppressed BOOLEAN DEFAULT false,

  actionable_recommendation TEXT,
  known_unknowns JSONB
);

COMMENT ON TABLE health_signals IS
  'Health/clinical OSINT signal feed — health-domain analogue of intelligence_events.';

CREATE INDEX IF NOT EXISTS idx_health_signals_domain_confidence
  ON health_signals(health_domain, confidence_level);
CREATE INDEX IF NOT EXISTS idx_health_signals_type_collected
  ON health_signals(signal_type, collected_at);
CREATE INDEX IF NOT EXISTS idx_health_signals_source_rank
  ON health_signals(source_id, rank_score DESC);

-- ─── health_signal_corroboration ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS health_signal_corroboration (
  corroboration_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  signal_id UUID NOT NULL REFERENCES health_signals(signal_id) ON DELETE CASCADE,
  corroborating_signal_id UUID NOT NULL REFERENCES health_signals(signal_id) ON DELETE CASCADE,
  corroboration_type VARCHAR(50),   -- direct_replication | similar_finding | conflicting_result | contextual_evidence
  agreement_strength FLOAT,          -- 0-1
  overlap_population BOOLEAN,
  overlap_intervention BOOLEAN,
  created_at TIMESTAMPTZ DEFAULT now(),
  CONSTRAINT no_self_corroboration CHECK (signal_id <> corroborating_signal_id)
);

CREATE INDEX IF NOT EXISTS idx_health_signal_corroboration_signal
  ON health_signal_corroboration(signal_id, agreement_strength DESC);

-- ─── health_adverse_events ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS health_adverse_events (
  event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  treatment_or_intervention TEXT NOT NULL,
  adverse_event_description TEXT NOT NULL,
  severity VARCHAR(20),             -- mild | moderate | severe | critical
  frequency_reported INTEGER DEFAULT 0,
  fda_flagged BOOLEAN DEFAULT false,
  probability_score FLOAT,          -- 0-1
  impact_score FLOAT,               -- 0-1
  source_id UUID REFERENCES health_source_registry(source_id) ON DELETE SET NULL,
  collected_at TIMESTAMPTZ DEFAULT now(),
  suppressed BOOLEAN DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_health_adverse_events_severity
  ON health_adverse_events(severity, fda_flagged);

-- ─── RLS: enable + authenticated-read on all 4 tables ────────────────────
-- Per the RLS lesson from migration 0087/0092: RLS must be explicitly
-- ENABLEd (CREATE POLICY alone does nothing) and use auth.role() =
-- 'authenticated' (not 'authenticated_user'). Reads are authenticated-only;
-- writes are service_role-only (ingestion runs server-side).

ALTER TABLE health_source_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE health_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE health_signal_corroboration ENABLE ROW LEVEL SECURITY;
ALTER TABLE health_adverse_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated can read health_source_registry"
  ON health_source_registry FOR SELECT
  USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated can read health_signals"
  ON health_signals FOR SELECT
  USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated can read health_signal_corroboration"
  ON health_signal_corroboration FOR SELECT
  USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated can read health_adverse_events"
  ON health_adverse_events FOR SELECT
  USING (auth.role() = 'authenticated');

GRANT SELECT ON health_source_registry, health_signals, health_signal_corroboration, health_adverse_events TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON health_source_registry, health_signals, health_signal_corroboration, health_adverse_events TO service_role;

-- ─── Seed: canonical health sources ──────────────────────────────────────

INSERT INTO health_source_registry
  (source_name, source_type, source_url, peer_reviewed, impact_factor, publisher_reputation,
   conflict_of_interest_disclosure, funding_transparency, replication_success_rate, retraction_rate, avg_methodology_quality)
VALUES
  ('NIH', 'health_agency', 'https://www.nih.gov', true, NULL, 0.97, true, 0.95, 0.85, 0.01, 0.90),
  ('FDA', 'health_agency', 'https://www.fda.gov', true, NULL, 0.96, true, 0.95, 0.85, 0.01, 0.88),
  ('CDC', 'health_agency', 'https://www.cdc.gov', true, NULL, 0.96, true, 0.95, 0.83, 0.01, 0.88),
  ('WHO', 'health_agency', 'https://www.who.int', true, NULL, 0.94, true, 0.90, 0.80, 0.02, 0.85),
  ('New England Journal of Medicine', 'journal', 'https://www.nejm.org', true, 96.2, 0.97, true, 0.90, 0.82, 0.01, 0.92),
  ('Nature Medicine', 'journal', 'https://www.nature.com/nm', true, 58.7, 0.95, true, 0.88, 0.78, 0.02, 0.90),
  ('The Lancet', 'journal', 'https://www.thelancet.com', true, 98.4, 0.96, true, 0.88, 0.79, 0.02, 0.90),
  ('JAMA', 'journal', 'https://jamanetwork.com', true, 63.1, 0.94, true, 0.87, 0.77, 0.02, 0.88),
  ('ClinicalTrials.gov', 'clinical_trial_db', 'https://clinicaltrials.gov', false, NULL, 0.85, true, 0.85, 0.60, 0.03, 0.70),
  ('Mayo Clinic Research', 'institution', 'https://www.mayoclinic.org', true, NULL, 0.88, true, 0.80, 0.72, 0.02, 0.80),
  ('Cochrane Reviews', 'journal', 'https://www.cochranelibrary.com', true, 11.9, 0.93, true, 0.90, 0.85, 0.01, 0.93),
  ('PLOS ONE', 'journal', 'https://journals.plos.org/plosone', true, 3.7, 0.72, true, 0.75, 0.55, 0.05, 0.65),
  ('Examine.com', 'institution', 'https://examine.com', false, NULL, 0.68, true, 0.70, 0.50, 0.05, 0.55),
  ('medRxiv (preprint)', 'journal', 'https://www.medrxiv.org', false, NULL, 0.40, false, 0.40, 0.30, 0.15, 0.30),
  ('Manufacturer press release', 'manufacturer', NULL, false, NULL, 0.25, false, 0.20, 0.20, 0.10, 0.20),
  ('Social media health claim', 'researcher', NULL, false, NULL, 0.10, false, 0.10, 0.05, 0.30, 0.10)
ON CONFLICT DO NOTHING;

-- ─── Done ─────────────────────────────────────────────────────────────────
-- Verify tier distribution:
-- SELECT source_name, reliability_score, reliability_tier FROM health_source_registry ORDER BY reliability_score DESC;
