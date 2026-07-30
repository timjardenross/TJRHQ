-- ============================================================
-- Migration 0028 — Captain's Notebook (EXEC-010B WP1)
-- Intelligence intake and refinement layer. Captain captures rough thoughts;
-- Officer Corps determines what they mean, why they matter, where they route.
-- Additive + idempotent. No duplicate storage of mission/decision records.
-- ============================================================

CREATE TABLE IF NOT EXISTS intelligence_notes (
  id                         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title                      text,
  raw_content                text NOT NULL,
  source                     text NOT NULL DEFAULT 'manual',
  source_url                 text,
  tags                       text[]    NOT NULL DEFAULT '{}',
  status                     text      NOT NULL DEFAULT 'CAPTURED'
                               CHECK (status IN (
                                 'CAPTURED',
                                 'OFFICER_REVIEW',
                                 'NUMBER_ONE_REVIEW',
                                 'READY_FOR_ROUTING',
                                 'ROUTED',
                                 'ARCHIVED'
                               )),
  created_at                 timestamptz NOT NULL DEFAULT now(),
  updated_at                 timestamptz NOT NULL DEFAULT now(),
  assigned_officers          text[]    NOT NULL DEFAULT '{}',
  officer_findings           jsonb     NOT NULL DEFAULT '{}',
  triage_summary             text,
  classification             text,
  confidence_score           numeric(3,2) CHECK (confidence_score           BETWEEN 0 AND 1),
  strategic_alignment_score  numeric(3,2) CHECK (strategic_alignment_score  BETWEEN 0 AND 1),
  value_score                numeric(3,2) CHECK (value_score                BETWEEN 0 AND 1),
  urgency_score              numeric(3,2) CHECK (urgency_score              BETWEEN 0 AND 1),
  effort_score               numeric(3,2) CHECK (effort_score               BETWEEN 0 AND 1),
  content_potential_score    numeric(3,2) CHECK (content_potential_score    BETWEEN 0 AND 1),
  recommended_route          text CHECK (recommended_route IN ('captain','xo','number_one','officer','knowledge','archive')),
  routed_to_type             text CHECK (routed_to_type IN ('mission','decision','lesson','knowledge','archived')),
  routed_to_id               text
);

CREATE INDEX IF NOT EXISTS intelligence_notes_status_idx    ON intelligence_notes (status);
CREATE INDEX IF NOT EXISTS intelligence_notes_created_at_idx ON intelligence_notes (created_at DESC);

ALTER TABLE intelligence_notes ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION set_intelligence_notes_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS intelligence_notes_updated_at ON intelligence_notes;
CREATE TRIGGER intelligence_notes_updated_at
  BEFORE UPDATE ON intelligence_notes
  FOR EACH ROW EXECUTE FUNCTION set_intelligence_notes_updated_at();
