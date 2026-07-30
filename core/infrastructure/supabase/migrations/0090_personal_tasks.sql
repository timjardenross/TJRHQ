-- ============================================================
-- Migration 0090 — Personal Tasks Table (ADHD Capabilities Suite)
-- USS Starship Endeavour NCC-170230
--
-- Issue 22: New, narrowly-scoped personal task table —
-- deliberate separation from Task Engine (migration 0056).
--
-- Background: Task Engine is a domain-agnostic durable-execution
-- primitive for services/agents delegating work. Personal Tasks
-- is a human productivity surface with different semantics:
-- urgency/importance/effort for prioritization, work_state for
-- workflow tracking, optional link to capture-workbench inbox items.
--
-- CRITICAL: This table does NOT extend or modify migration 0056.
-- Completely separate schema, separate RLS, separate lifecycle.
--
-- Additive & idempotent. Safe to re-run.
-- ============================================================

CREATE TABLE IF NOT EXISTS personal_tasks (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Task definition
    title               text        NOT NULL,
    context             text,           -- free-form task context/description

    -- Prioritization (urgency + importance - effort_minutes = priority_score)
    urgency             smallint    NOT NULL CHECK (urgency BETWEEN 1 AND 5),  -- 1=whenever, 5=now
    importance          smallint    NOT NULL CHECK (importance BETWEEN 1 AND 5),  -- 1=trivial, 5=critical
    effort_minutes      integer     NOT NULL DEFAULT 30,  -- estimated work in minutes

    -- Workflow state (distinct from Task Engine's lifecycle)
    work_state          text        NOT NULL DEFAULT 'captured'
                            CHECK (work_state IN (
                                'captured',      -- newly created, not yet started
                                'in_progress',   -- actively being worked on
                                'blocked',       -- waiting for something external
                                'paused',        -- intentionally paused
                                'completed',     -- finished
                                'abandoned'      -- deliberately dropped
                            )),

    -- Link to originating capture item (optional, for traceability)
    source_capture_id   uuid        REFERENCES captured_items(id) ON DELETE SET NULL,

    -- Provenance & lifecycle
    created_at          timestamptz NOT NULL DEFAULT now(),
    started_at          timestamptz,
    completed_at        timestamptz,
    updated_at          timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE personal_tasks IS
  'Issue 22: Human productivity tasks, completely separate from Task Engine. '
  'Tracks personal work with urgency/importance/effort prioritization. '
  'Intentionally minimal schema for ADHD productivity workflows.';

COMMENT ON COLUMN personal_tasks.urgency IS
  'Urgency scale 1–5: 1=whenever, 2=soon, 3=today, 4=ASAP, 5=NOW. '
  'Complements importance for prioritization.';

COMMENT ON COLUMN personal_tasks.importance IS
  'Importance scale 1–5: 1=trivial, 2=minor, 3=normal, 4=significant, 5=critical. '
  'Complements urgency for prioritization.';

COMMENT ON COLUMN personal_tasks.effort_minutes IS
  'Estimated effort in minutes. Used with urgency/importance for scoring. '
  'Lower effort makes tasks more achievable (helps ADHD task initiation).';

COMMENT ON COLUMN personal_tasks.work_state IS
  'Workflow state: captured (new), in_progress (active), blocked (waiting), '
  'paused (on hold), completed (done), abandoned (dropped). '
  'Distinct from Task Engine's status field.';

COMMENT ON COLUMN personal_tasks.source_capture_id IS
  'Link to captured_items(id) for traceability if this task originated '
  'from the capture-workbench. NULL if created directly.';

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_personal_tasks_work_state
    ON personal_tasks (work_state);
CREATE INDEX IF NOT EXISTS idx_personal_tasks_created_at
    ON personal_tasks (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_personal_tasks_priority_score
    ON personal_tasks ((urgency + importance - (effort_minutes / 60)::smallint) DESC);
CREATE INDEX IF NOT EXISTS idx_personal_tasks_source_capture
    ON personal_tasks (source_capture_id);

-- RLS: Single-user personal data table.
-- Service role has full access; authenticated (personal user) has read/write.
-- No public (anon) access — personal productivity data is never public.
ALTER TABLE personal_tasks ENABLE ROW LEVEL SECURITY;

-- Service role: full access (for backend services/migrations)
DROP POLICY IF EXISTS "service_role_full_access" ON personal_tasks;
CREATE POLICY "service_role_full_access" ON personal_tasks
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Authenticated: read/write access (the Captain's own personal tasks)
DROP POLICY IF EXISTS "authenticated_full_access" ON personal_tasks;
CREATE POLICY "authenticated_full_access" ON personal_tasks
    FOR ALL TO authenticated USING (true) WITH CHECK (true);
