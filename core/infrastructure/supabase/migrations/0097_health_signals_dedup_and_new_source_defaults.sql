-- Migration 0097: dedup support for health_signals + auto-registration defaults
--
-- health_signals had no dedup_hash/canonical_url (unlike intelligence_events),
-- so a real ingestion pipeline would double-insert the same PubMed article on
-- every run. Adding both, mirroring the technical pipeline's pattern.

ALTER TABLE health_signals ADD COLUMN IF NOT EXISTS dedup_hash TEXT;
ALTER TABLE health_signals ADD COLUMN IF NOT EXISTS canonical_url TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_health_signals_dedup_hash
  ON health_signals(dedup_hash) WHERE dedup_hash IS NOT NULL;

COMMENT ON COLUMN health_signals.dedup_hash IS
  'sha256(source_id || pmid/nct_id) — prevents re-inserting the same article/trial on repeated collection runs.';
COMMENT ON COLUMN health_signals.canonical_url IS
  'Direct link to the source article/trial record (PubMed/ClinicalTrials.gov permalink).';

-- Track auto-registered journal sources distinctly from hand-curated ones,
-- so it's visible later which sources have never been reviewed by a person.
ALTER TABLE health_source_registry ADD COLUMN IF NOT EXISTS auto_registered BOOLEAN DEFAULT false;
COMMENT ON COLUMN health_source_registry.auto_registered IS
  'true if this row was created automatically by the PubMed ingestion job '
  'on encountering an unseen journal, rather than hand-curated at build time.';
