-- Migration 0096: separate column for OSINT source-tier confidence
--
-- intelligence_events.confidence_level (added by migration 0077, "Phase A
-- Intelligence Workflow") is a live governance field written by
-- intelligence/workflow/service.py's verify_event() — an analyst
-- verification action using vocabulary ('Confirmed'/'Probable'/'Emerging'/
-- 'Unverified') for "has a human verified this claim". TECHNICAL_OSINT_
-- WORKBENCH.md's schema section assumed this column was free to reuse for
-- source-tier-derived confidence (HIGH/MEDIUM/LOW/UNKNOWN) — it collides
-- with a real, live, unrelated feature. Using a separate column instead of
-- overwriting governance state.

ALTER TABLE intelligence_events ADD COLUMN IF NOT EXISTS
  osint_confidence_level TEXT CHECK (osint_confidence_level IN ('HIGH', 'MEDIUM', 'LOW', 'UNKNOWN'));

COMMENT ON COLUMN intelligence_events.osint_confidence_level IS
  'Source-tier + corroboration derived confidence per TECHNICAL_OSINT_WORKBENCH.md '
  'section 3. Distinct from confidence_level (Phase A workflow governance status) — '
  'do not conflate the two.';

CREATE INDEX IF NOT EXISTS idx_intelligence_events_osint_confidence
  ON intelligence_events(sector, osint_confidence_level);
