-- ============================================================
-- Migration 0217 — Mission 3: Capture → Task actionability + provenance
-- USS Starship Endeavour NCC-170230
--
-- Mission 3 (Capture, Remember & Follow-Through) closes the
-- captured_items → personal_tasks gap. Two additive pieces:
--
-- 1. captured_items.actionable / actionable_confidence — a typed field
--    for the NEW "does this require action?" determination, kept
--    deliberately separate from `classification` ("what is this?").
--    A 'personal' capture is not automatically a task; a 'reference'
--    capture occasionally is ("buy dog food"). These columns let
--    engineering/debug tooling query the routing decision directly
--    instead of parsing the `summary` jsonb blob.
--
-- 2. Unique index on personal_tasks(source_capture_id) — DB-level
--    idempotency for the new capture→task routing path. The worker
--    already relies on processing_status='pending' filtering to avoid
--    reprocessing, but a crash between INSERT and the captured_items
--    UPDATE would otherwise create a second task on retry. This index
--    makes that impossible regardless of application-level bugs or
--    concurrent worker runs.
--
-- Additive & idempotent. Safe to re-run.
-- ============================================================

ALTER TABLE public.captured_items
  ADD COLUMN IF NOT EXISTS actionable            text,
  ADD COLUMN IF NOT EXISTS actionable_confidence  numeric(3,2);

ALTER TABLE public.captured_items
  DROP CONSTRAINT IF EXISTS captured_items_actionable_check;

ALTER TABLE public.captured_items
  ADD CONSTRAINT captured_items_actionable_check
    CHECK (actionable IS NULL OR actionable IN ('yes', 'no', 'ambiguous'));

COMMENT ON COLUMN public.captured_items.actionable IS
  'Mission 3: does this capture require action, independent of '
  '`classification` (what it is). NULL = not yet determined (pre-'
  'enrichment or enrichment failed). Never inferred from classification '
  'alone — a personal/reference capture can still be actionable.';
COMMENT ON COLUMN public.captured_items.actionable_confidence IS
  'Confidence (0.00-1.00) behind the `actionable` determination. Gates '
  'personal_tasks creation the same way ai_confidence gates the '
  'existing auto-route/promotion paths.';

CREATE INDEX IF NOT EXISTS captured_items_actionable_idx
  ON public.captured_items (actionable);

-- ── Idempotent capture→task routing ─────────────────────────────────
CREATE UNIQUE INDEX IF NOT EXISTS personal_tasks_source_capture_uniq
  ON public.personal_tasks (source_capture_id)
  WHERE source_capture_id IS NOT NULL;

COMMENT ON INDEX public.personal_tasks_source_capture_uniq IS
  'Mission 3: DB-enforced idempotency for captured_items -> personal_tasks '
  'routing. A retried/duplicate enrichment pass cannot create a second '
  'task for the same capture -- the INSERT fails with a unique violation, '
  'which the caller (core/capture/enrichment_worker.py) treats as '
  '"already routed", not an error.';
