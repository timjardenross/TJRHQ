-- ============================================================
-- Migration 0163 — Life Admin fields on Personal Tasks
-- USS Starship Endeavour NCC-170230
--
-- Ready Room Workbench: extends personal_tasks (migration 0090)
-- with life-admin semantics (category, due date, waiting-on note)
-- and task-decomposition output fields, instead of forking a new
-- table. personal_tasks already had the right shape (urgency,
-- work_state incl. 'blocked') and zero writers — this activates it.
--
-- Additive & idempotent. Safe to re-run.
-- ============================================================

ALTER TABLE personal_tasks
    ADD COLUMN IF NOT EXISTS category text NOT NULL DEFAULT 'task'
        CHECK (category IN (
            'task',        -- generic decomposed task, no life-admin angle
            'bill',
            'appointment',
            'renewal',
            'subscription',
            'form',
            'follow_up',
            'errand',
            'waiting_on'
        )),
    ADD COLUMN IF NOT EXISTS due_date     date,
    ADD COLUMN IF NOT EXISTS waiting_on   text,   -- free text: what/who this is blocked on
    ADD COLUMN IF NOT EXISTS micro_action text,   -- decompose_task() output: the tiny first step
    ADD COLUMN IF NOT EXISTS mvp_note     text,   -- "good enough" version of done
    ADD COLUMN IF NOT EXISTS stop_point   text,   -- where the user left off
    ADD COLUMN IF NOT EXISTS restart_cue  text;   -- how to re-enter after interruption

COMMENT ON COLUMN personal_tasks.category IS
  'Life-admin category for Ready Room triage. ''task'' = generic decomposed task.';
COMMENT ON COLUMN personal_tasks.due_date IS
  'Optional deadline. Drives Ready Room''s Now/Upcoming grouping.';
COMMENT ON COLUMN personal_tasks.waiting_on IS
  'What/who this is blocked on, shown alongside work_state=''blocked'' so a '
  'waiting item is legible without opening it.';
COMMENT ON COLUMN personal_tasks.micro_action IS
  'Output of intelligence.adhd.task_decomposition.decompose_task() — the '
  'single concrete 5-15min first step, editable by the user.';
COMMENT ON COLUMN personal_tasks.mvp_note IS
  'The minimum viable / "good enough" version of this task being done.';
COMMENT ON COLUMN personal_tasks.stop_point IS
  'Where the user left off, set on pause/blocked.';
COMMENT ON COLUMN personal_tasks.restart_cue IS
  'A short cue for re-entering the task after interruption (e.g. '
  '"reopen the folder, re-read the last paragraph").';

CREATE INDEX IF NOT EXISTS idx_personal_tasks_category_due
    ON personal_tasks (category, due_date);
