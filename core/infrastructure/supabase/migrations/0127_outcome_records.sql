-- ============================================================================
-- Migration 0030 — outcome_records: unified Outcome & Learning Capture ledger
-- ============================================================================
-- Mission: USS-TJR-MSN-0076 (Outcome & Learning Capture Loop)
--
-- Purpose:
--   One lightweight, cross-source ledger recording WHAT HAPPENED after a
--   meaningful work item — missions, decisions, intelligence briefs,
--   recommendations, actions, or a manual Captain note. Closes the loop:
--     Signal → Intelligence → Knowledge → Decision → Action →
--     OUTCOME → Learning → Reuse → Content
--
-- Reuse note (WP1):
--   This is DISTINCT from the existing decision-specific `decision_outcomes`
--   table (MSN-0060B B1B, schema in tools/supabase/schema/MSN-0060B-B1B-*.sql),
--   which is FK-bound to `decision_records` and intentionally minimal (status +
--   notes) to feed the B1C/B1D quality-scoring pipeline. Extending that table to
--   be polymorphic across all source types would break its FK semantics and the
--   decision learning pipeline — confusion and technical debt. Per the mission's
--   guidance, a new additive table is therefore created. Lessons captured here
--   still flow into the existing `lessons_learned` table (the source of truth for
--   lesson surfacing in the recommendation engine) via core/knowledge/lesson_capture.py.
--
-- Authoritative outcome record location: outcome_records (this table).
--
-- Apply via Supabase SQL Editor or psql. Safe to re-run (IF NOT EXISTS).
-- ============================================================================

CREATE TABLE IF NOT EXISTS outcome_records (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    outcome_id                TEXT UNIQUE NOT NULL,        -- e.g. "OUTR-20260625-143000"

    -- What this outcome is about (the source work item).
    source_type               TEXT NOT NULL
        CHECK (source_type IN (
            'mission', 'decision', 'intelligence_brief',
            'recommendation', 'action', 'note'
        )),
    source_id                 TEXT NOT NULL,               -- mission_id / decision id / brief_id / free ref
    title                     TEXT NOT NULL,

    -- What happened.
    outcome_summary           TEXT,
    outcome_status            TEXT
        CHECK (outcome_status IN (
            'worked', 'partial', 'failed', 'mixed', 'too_early', 'abandoned'
        )),
    decision_or_action_taken  TEXT,
    actual_result             TEXT,
    expected_result           TEXT,
    variance                  TEXT,

    -- What we learned / can reuse.
    lesson_learned            TEXT,
    reusable_insight          TEXT,
    reuse_tags                TEXT[] DEFAULT '{}',         -- free-form reuse tags
    lesson_id                 TEXT,                        -- link to lessons_learned(lesson_id) if promoted

    -- Content reuse flags (WP6) — consumed later by COMMS-001. Never publishes.
    content_potential         TEXT DEFAULT 'none'
        CHECK (content_potential IN ('none', 'low', 'medium', 'high')),
    content_classification    TEXT DEFAULT 'internal_work'
        CHECK (content_classification IN (
            'internal_work', 'linkedin', 'coaching', 'wellness',
            'operational_resilience', 'leadership', 'personal_learning',
            'not_for_publication'
        )),
    coaching_relevance        BOOLEAN DEFAULT false,
    work_relevance            BOOLEAN DEFAULT false,

    -- Confidence + evidence.
    confidence                INTEGER CHECK (confidence BETWEEN 1 AND 5),
    evidence_links            TEXT[] DEFAULT '{}',

    -- Provenance.
    created_at                TIMESTAMPTZ DEFAULT now(),
    created_by                TEXT DEFAULT 'captain',
    updated_at                TIMESTAMPTZ DEFAULT now(),

    -- One outcome record per source item (idempotent upsert key) — prevents duplicates.
    CONSTRAINT outcome_records_source_unique UNIQUE (source_type, source_id)
);

-- Helpful indexes for retrieval / briefing queries.
CREATE INDEX IF NOT EXISTS idx_outcome_records_created_at
    ON outcome_records (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_outcome_records_source
    ON outcome_records (source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_outcome_records_content
    ON outcome_records (content_potential, content_classification);

-- Enable RLS. Posture CORRECTED at activation (MSN-0081 WP1): authenticated read
-- + service_role full access — matching the project's established pattern
-- (lessons_learned / health / missions). NO anon policy: outcome_records holds
-- sensitive personal_story / not_for_publication free-text, which must never be
-- readable via the public anon key. (The original draft granted anon SELECT; that
-- was removed before any production application — see MSN-0081.)
ALTER TABLE outcome_records ENABLE ROW LEVEL SECURITY;

-- Service role has full access.
DROP POLICY IF EXISTS "service_role_full_access" ON outcome_records;
CREATE POLICY "service_role_full_access" ON outcome_records
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Authenticated read only (NO anon).
DROP POLICY IF EXISTS "auth_read" ON outcome_records;
CREATE POLICY "auth_read" ON outcome_records
    FOR SELECT TO authenticated USING (true);
