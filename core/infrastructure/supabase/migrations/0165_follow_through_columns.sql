-- ============================================================
-- Migration 0165 — Adaptive Follow-Through columns on Personal Tasks
-- USS Starship Endeavour NCC-170230
--
-- Adaptive Follow-Through via XO: the engine needs to know WHEN to
-- next consider surfacing a task and HOW insistently, without a
-- separate dedup/rate-limit table — these columns on personal_tasks
-- ARE the dedup ledger (next_review_at/last_surfaced_at), replacing
-- the prior SQLite NudgeRateLimiter (/tmp/adhd_nudges.db, not durable).
--
-- Additive & idempotent. Safe to re-run.
-- ============================================================

ALTER TABLE personal_tasks
    ADD COLUMN IF NOT EXISTS follow_through_mode text NOT NULL DEFAULT 'normal'
        CHECK (follow_through_mode IN ('gentle', 'normal', 'persistent', 'deadline', 'waiting')),
    ADD COLUMN IF NOT EXISTS next_review_at        timestamptz,
    ADD COLUMN IF NOT EXISTS snoozed_until          timestamptz,
    ADD COLUMN IF NOT EXISTS last_surfaced_at       timestamptz,
    ADD COLUMN IF NOT EXISTS nudge_count            integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS deferral_count         integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS blocker_category       text
        CHECK (blocker_category IS NULL OR blocker_category IN
            ('too_big', 'need_info', 'waiting', 'no_idea', 'missing', 'not_now', 'other')),
    ADD COLUMN IF NOT EXISTS follow_through_paused  boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN personal_tasks.follow_through_mode IS
  'How insistently the Follow-Through Engine should resurface this item: '
  'gentle (once), normal (default, 2 surfaces then stop), persistent '
  '(keeps resurfacing until resolved), deadline (escalation ladder vs '
  'due_date), waiting (reviews at due_date-as-expected-date instead of '
  'nagging an action the user cannot currently take).';
COMMENT ON COLUMN personal_tasks.next_review_at IS
  'When the Follow-Through Engine should next consider surfacing this '
  'task. NULL means "compute on next pass" (new item or a mode that has '
  'stopped auto-resurfacing).';
COMMENT ON COLUMN personal_tasks.snoozed_until IS
  'Explicit user snooze, takes precedence over next_review_at while in '
  'the future.';
COMMENT ON COLUMN personal_tasks.last_surfaced_at IS
  'Last time XO actually sent something about this task.';
COMMENT ON COLUMN personal_tasks.nudge_count IS
  'Total times surfaced — learning-data column for future follow-through '
  'tuning, not used for gating beyond the normal-mode 2-surface cap.';
COMMENT ON COLUMN personal_tasks.deferral_count IS
  'Consecutive snooze/tomorrow taps. Resets on Done/Start/Blocked. '
  'Drives the repeated-deferral flow (>=3 -> "what''s getting in the '
  'way?" instead of another plain reminder).';
COMMENT ON COLUMN personal_tasks.blocker_category IS
  'Set by the Blocked flow — why this isn''t progressing.';
COMMENT ON COLUMN personal_tasks.follow_through_paused IS
  'Manual per-item pause. The engine skips paused items entirely.';
COMMENT ON COLUMN personal_tasks.due_date IS
  'Deadline for most modes. Reused as the "expected response/payment '
  'date" when follow_through_mode=''waiting'' — same field, mode-'
  'dependent meaning, to avoid a redundant column.';

CREATE INDEX IF NOT EXISTS idx_personal_tasks_next_review
    ON personal_tasks (next_review_at) WHERE follow_through_paused = false;
