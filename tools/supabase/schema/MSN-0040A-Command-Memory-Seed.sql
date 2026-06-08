-- ============================================================================
-- MSN-0040A — Command Memory MVP — Initial Data Load (Phase 2)
-- ============================================================================
-- Seeds the four tables with the founding operational record. Idempotent via
-- ON CONFLICT DO NOTHING so re-running never duplicates or overwrites.
--
-- This data is ALREADY LOADED in the deployed Supabase project (verified live).
-- Kept in-repo as source of truth and for fresh-environment restore.
-- ============================================================================

-- Capability: Slack Commander
INSERT INTO capabilities (id, name, purpose, owner, status, created_at, updated_at, updated_by)
VALUES (
  'CAP-2026-001',
  'Slack Commander',
  'Decision Intelligence and mission routing through Slack',
  'U001',
  'Operational',
  '2026-06-08T18:30:00Z',
  '2026-06-08T18:30:00Z',
  'U001'
)
ON CONFLICT (id) DO NOTHING;

-- Mission: Slack Commander Operational Completion (MSN-0011B)
INSERT INTO missions (id, title, created_by, created_at, status, owner, updated_at, updated_by)
VALUES (
  'M-20260608-120000',
  'Slack Commander Operational Completion',
  'U001',
  '2026-06-08T12:00:00Z',
  'Completed',
  'U001',
  '2026-06-08T18:30:00Z',
  'U001'
)
ON CONFLICT (id) DO NOTHING;

-- Mission: Command Memory Core Architecture (MSN-0039)
INSERT INTO missions (id, title, created_by, created_at, status, owner, updated_at, updated_by)
VALUES (
  'M-20260608-140000',
  'Command Memory Core Architecture',
  'U001',
  '2026-06-08T14:00:00Z',
  'Completed',
  'U001',
  '2026-06-08T16:00:00Z',
  'U001'
)
ON CONFLICT (id) DO NOTHING;

-- Decision: Supabase as primary data store for Command Memory
INSERT INTO decisions (id, statement, rationale, created_by, created_at, owner, status, alternatives, updated_at, updated_by)
VALUES (
  'DEC-20260608-100000',
  'We will use Supabase as the primary data store for Command Memory',
  'Supabase provides SQL queries, full-text search, JSON support with minimal operational overhead. Cost is sustainable (<$50/month). Alternatives are premature for current needs.',
  'U001',
  '2026-06-08T10:00:00Z',
  'U001',
  'Active',
  '[
    {"name": "Option A: Supabase Only", "assessment": "Optimal. $20-50/month, low complexity."},
    {"name": "Option B: Supabase + Embeddings", "assessment": "2-3x cost, unnecessary complexity."},
    {"name": "Option C: Vector Database", "assessment": "10x cost, over-engineered."}
  ]'::json,
  '2026-06-08T10:00:00Z',
  'U001'
)
ON CONFLICT (id) DO NOTHING;

-- Architecture Record: Command Memory Data Store Selection
INSERT INTO architecture_records (id, title, problem_statement, decision_summary, recommended_option, decision_authority, decision_date, status, alternatives, created_at, updated_at, updated_by)
VALUES (
  'ADR-20260608-140000',
  'Command Memory Data Store Selection',
  'What is the simplest architecture for Command Memory Core over 12-24 months?',
  'Use Supabase only. SQL + text search sufficient. No embeddings or vector DB needed initially.',
  'Option A: Supabase Only',
  'U001',
  '2026-06-08T14:00:00Z',
  'Active',
  '[
    {"name": "Option A: Supabase Only", "assessment": "Optimal for current needs. $20-50/month, low complexity."},
    {"name": "Option B: Supabase + Embeddings", "assessment": "2-3x cost increase, adds operational overhead."},
    {"name": "Option C: Supabase + Vector Database", "assessment": "10x cost, over-engineered for 12-24 months."}
  ]'::json,
  '2026-06-08T14:00:00Z',
  '2026-06-08T14:00:00Z',
  'U001'
)
ON CONFLICT (id) DO NOTHING;
