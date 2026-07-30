-- ============================================================
-- Migration 0056 — Task Engine (SUOC Wave 3, Workstream A)
-- Generalises the strongest existing durable-execution precedent
-- (core/infrastructure/vm-transfer/'s batches/files_state/transfer_log,
-- identified in MSN-0210C §8) into a universal, cross-domain task model.
--
-- Deliberate simplification from 3 tables to 2: vm-transfer's separate
-- "batches" table is replaced by self-referential parent_task_id — a
-- batch/run IS a task, with children linked via parent_task_id, rather
-- than a structurally separate concept. This is a generalisation, not
-- a feature loss: vm-transfer's own batch-level counters are derivable
-- by aggregating child tasks' statuses.
--
-- Additive — does not touch vm-processing's, batch_coding's, or
-- vm-transfer's own existing state tracking. Migration onto this engine
-- is a separate, later step for each (Wave 3 pilot: vm-processing first).
-- ============================================================

CREATE TABLE IF NOT EXISTS tasks (
    task_id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    task_type         text        NOT NULL,      -- 'research' | 'engineering' | 'health' | 'content' | 'operations' | ...
    domain            text        NOT NULL,       -- owning Platform Capability / Intelligence Domain, or 'system'
    owner             text        NOT NULL,       -- officer/service/agent responsible
    status            text        NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'in_progress', 'blocked', 'completed', 'failed', 'cancelled')),
    parent_task_id    uuid        REFERENCES tasks(task_id) ON DELETE SET NULL,
    delegated_to      text,                       -- officer/service this task was delegated to, if any
    idempotency_key   text        UNIQUE,          -- optional; callers that need dedup (vm-transfer-style) set this
    metadata          jsonb       NOT NULL DEFAULT '{}',
    confidence        smallint    CHECK (confidence BETWEEN 0 AND 100),
    attempts          integer     NOT NULL DEFAULT 0,
    last_error        text,
    linked_mission_id text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    started_at        timestamptz,
    completed_at      timestamptz,
    updated_at        timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE tasks IS
  'SUOC Wave 3: universal task model (Task Engine). One canonical lifecycle for '
  'research/engineering/health/content/operations tasks and future execution-engine '
  '(Hermes or otherwise) tasks. parent_task_id models delegation/sub-tasks; '
  'idempotency_key is optional dedup for callers migrating from a keyed retry model.';

CREATE TABLE IF NOT EXISTS task_events (
    event_id     uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id      uuid        NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    event_type   text        NOT NULL,   -- 'created' | 'status_changed' | 'delegated' | 'completed' | 'failed' | ...
    detail       jsonb       NOT NULL DEFAULT '{}',
    occurred_at  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE task_events IS
  'SUOC Wave 3: append-only task history/audit trail. Every lifecycle transition '
  'on a task should produce one row here — this is the Task Engine''s "Task audit" '
  'and "Task history" requirement.';

-- RLS: service_role bypasses; no public read/write
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_events ENABLE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS tasks_status_idx ON tasks (status);
CREATE INDEX IF NOT EXISTS tasks_type_idx ON tasks (task_type);
CREATE INDEX IF NOT EXISTS tasks_domain_idx ON tasks (domain);
CREATE INDEX IF NOT EXISTS tasks_owner_idx ON tasks (owner);
CREATE INDEX IF NOT EXISTS tasks_parent_idx ON tasks (parent_task_id);
CREATE INDEX IF NOT EXISTS tasks_mission_idx ON tasks (linked_mission_id);
CREATE INDEX IF NOT EXISTS task_events_task_idx ON task_events (task_id);
CREATE INDEX IF NOT EXISTS task_events_occurred_at_idx ON task_events (occurred_at DESC);
