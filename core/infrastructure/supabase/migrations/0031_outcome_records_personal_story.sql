-- ============================================================================
-- Migration 0031 — outcome_records: add 'personal_story' content_classification
-- ============================================================================
-- Mission: USS-TJR-MSN-0078 (COMMS-001 Regression Repair & Outcome-to-Content Bridge), WP5
--
-- Purpose:
--   Extend the content_classification controlled vocabulary with 'personal_story'
--   to capture future coaching / thought-leadership material grounded in personal
--   experience (resilience, recovery, chronic pain, burnout, leadership under
--   pressure, career transition).
--
-- Governance (enforced in the capture/bridge layer, not the DB):
--   - Sensitive by default. NEVER auto-published.
--   - Excluded from content candidates unless explicitly requested
--     (get_content_candidates(include_internal=True)).
--   - Captain approval required before any draft generation.
--
-- Purely additive: re-defines the CHECK constraint to include the new value.
-- Safe to re-run. No data is modified.
-- ============================================================================

ALTER TABLE outcome_records
    DROP CONSTRAINT IF EXISTS outcome_records_content_classification_check;

ALTER TABLE outcome_records
    ADD CONSTRAINT outcome_records_content_classification_check
    CHECK (content_classification IN (
        'internal_work', 'linkedin', 'coaching', 'wellness',
        'operational_resilience', 'leadership', 'personal_learning',
        'personal_story',
        'not_for_publication'
    ));
