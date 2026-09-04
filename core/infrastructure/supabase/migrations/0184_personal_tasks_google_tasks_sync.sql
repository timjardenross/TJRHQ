-- ============================================================
-- Migration 0184 — Google Tasks sync link on Personal Tasks
-- USS Starship Endeavour NCC-170230
--
-- Two-way sync: personal_tasks <-> Google Tasks (Captain's own
-- account). Google Tasks becomes another capture surface — the
-- follow-through engine (task_nudge_scheduler.py, follow_through_
-- engine.py) still reads personal_tasks directly regardless of
-- origin, so nudging survives a task being added from the phone.
--
-- Additive & idempotent. Safe to re-run.
-- ============================================================

ALTER TABLE personal_tasks
    ADD COLUMN IF NOT EXISTS google_task_id      text,
    ADD COLUMN IF NOT EXISTS google_task_list_id text,
    ADD COLUMN IF NOT EXISTS google_synced_at    timestamptz;

COMMENT ON COLUMN personal_tasks.google_task_id IS
  'Linked Google Tasks task ID. NULL = never synced to/from Google. One row per Google task — see google_task_id unique index.';
COMMENT ON COLUMN personal_tasks.google_task_list_id IS
  'Which Google Tasks list this is linked into (default "@default" unless the Captain picks another).';
COMMENT ON COLUMN personal_tasks.google_synced_at IS
  'Last successful sync timestamp for this row, either direction. Compared against updated_at to decide what needs pushing.';

CREATE UNIQUE INDEX IF NOT EXISTS idx_personal_tasks_google_task_id
    ON personal_tasks (google_task_id)
    WHERE google_task_id IS NOT NULL;
