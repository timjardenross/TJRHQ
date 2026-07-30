-- ============================================================
-- Migration 0058 — Operational Pattern Library (SUOC Wave 3, Workstream E)
-- First real implementation. Stores reusable engineering patterns
-- extracted from completed missions, as platform knowledge rather than
-- isolated mission history. Not AI-specific — this is general platform
-- engineering-process capability.
-- ============================================================

CREATE TABLE IF NOT EXISTS operational_patterns (
    pattern_id       uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern_name     text        NOT NULL UNIQUE,
    pattern_category text        NOT NULL,   -- 'stabilisation' | 'convergence' | 'readiness-gate' | 'review' | 'build-vs-borrow' | 'security' | 'validation'
    description      text        NOT NULL,
    when_to_use      text        NOT NULL,
    steps            jsonb       NOT NULL DEFAULT '[]',
    source_missions  jsonb       NOT NULL DEFAULT '[]',
    confidence       smallint    CHECK (confidence BETWEEN 0 AND 100),
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE operational_patterns IS
  'SUOC Wave 3: reusable engineering patterns extracted from completed missions. '
  'Populated via core/platform/operational_pattern_library.py. Not tied to any '
  'specific AI/agent implementation — general platform engineering-process knowledge.';

ALTER TABLE operational_patterns ENABLE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS operational_patterns_category_idx ON operational_patterns (pattern_category);
