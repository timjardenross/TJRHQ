-- ============================================================
-- Migration 0095 — Content Workflow Extensions (COMMS-002 / Content Workbench)
--
-- Purely additive support for a new, standalone Content Workbench
-- (/content-workbench) implementing Capture -> Research -> Content Prep ->
-- Proofing on top of the existing comms_content lifecycle store from
-- migration 0027/0036. Publishing stays out of scope here by design — the
-- canonical status enum, TRANSITIONS state machine
-- (api/comms/[id]/advance/route.ts), and every existing route/component in
-- comms-workbench/ and capture-workbench/ are UNCHANGED by this migration.
-- No column added here is read or written by any pre-existing route.
--
-- Stage model used by the new workbench (computed at read time, not stored
-- as a new status value, specifically so the existing status_chk constraint
-- and TRANSITIONS map never need to change):
--   capture      status = 'opportunity' AND research_notes IS NULL
--   research     status = 'opportunity' AND research_notes IS NOT NULL
--   content_prep status = 'draft'
--   proofing     status IN ('review', 'approved')
-- ============================================================

-- ── Research stage fields ───────────────────────────────────────────────────

ALTER TABLE comms_content
  ADD COLUMN IF NOT EXISTS research_notes         text,
  ADD COLUMN IF NOT EXISTS research_sources       jsonb DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS research_angle         text,
  ADD COLUMN IF NOT EXISTS research_completed_at  timestamptz;

COMMENT ON COLUMN comms_content.research_notes IS
  'Content Workbench (COMMS-002): human-authored research brief captured before '
  'draft generation. Presence of this field (research_completed_at set) is what '
  'gates /api/content-workbench/[id]/generate.';
COMMENT ON COLUMN comms_content.research_sources IS
  'COMMS-002: array of {label, url} source references gathered during research.';
COMMENT ON COLUMN comms_content.research_angle IS
  'COMMS-002: confirmed framing angle — pre-filled from content_signals.suggested_angle '
  'when the opportunity came from a signal, editable, required for capture-only items.';

-- ── Proofing / QA stage fields ────────────────────────────────────────────────

ALTER TABLE comms_content
  ADD COLUMN IF NOT EXISTS qa_checklist   jsonb DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS qa_status      text,
  ADD COLUMN IF NOT EXISTS reviewed_by    text,
  ADD COLUMN IF NOT EXISTS reviewed_at    timestamptz;

ALTER TABLE comms_content
  DROP CONSTRAINT IF EXISTS comms_content_qa_status_chk;

ALTER TABLE comms_content
  ADD CONSTRAINT comms_content_qa_status_chk
  CHECK (qa_status IS NULL OR qa_status IN ('pending', 'qa_passed', 'qa_failed'));

COMMENT ON COLUMN comms_content.qa_checklist IS
  'COMMS-002: proofing checklist, e.g. {"accuracy":true,"brand_voice":true,'
  '"compliance":true,"links_checked":true,"notes":"..."}. Structured QA gate — '
  'previously "review"/"approved" were bare status labels with no checklist.';
COMMENT ON COLUMN comms_content.qa_status IS
  'COMMS-002: pending|qa_passed|qa_failed. Independent of comms_content.status — '
  'lets a reviewer flag issues without forking the canonical advance() state machine.';

-- ── Capture-time scoring fields ───────────────────────────────────────────────
-- Closes the gap where capture-sourced opportunities (source_kind='capture')
-- previously bypassed classification/ranking entirely (no rank_score, no real
-- pillar unless typed in). The Content Workbench's own capture endpoint scores
-- every capture with a TypeScript port of content_classifier.py/content_ranker.py
-- (see lcars-portal/src/lib/contentScoring.ts) before insert. This does NOT
-- touch lib/capture.ts or /api/content/draft — the existing Capture Workbench's
-- 'comms' capture type is untouched and still bypasses scoring as before.

ALTER TABLE comms_content
  ADD COLUMN IF NOT EXISTS rank_score       double precision,
  ADD COLUMN IF NOT EXISTS capture_scored   boolean DEFAULT false;

COMMENT ON COLUMN comms_content.rank_score IS
  'COMMS-002: 0-100 composite score, same formula and scale as content_signals.rank_score, '
  'computed at capture time for items created via /api/content-workbench/capture. '
  'NULL for pre-existing rows and for items created via the original /api/content/draft path.';
COMMENT ON COLUMN comms_content.capture_scored IS
  'COMMS-002: true once this row has passed through classification/ranking at capture '
  'time. Distinguishes scored Content Workbench captures from the unscored legacy path.';

-- ── Draft revision history ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS comms_content_revisions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  content_id  uuid NOT NULL REFERENCES comms_content(id) ON DELETE CASCADE,
  body        text NOT NULL,
  edited_by   text,
  created_at  timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_comms_content_revisions_content_id
  ON comms_content_revisions (content_id, created_at DESC);

COMMENT ON TABLE comms_content_revisions IS
  'COMMS-002: append-only draft revision history for comms_content.body edits made '
  'in the Content Workbench (Content Prep stage). The pre-existing PATCH '
  '/api/content/pipeline overwrite-on-save behaviour in comms-workbench is unchanged; '
  'this table is only written by the new /api/content-workbench/[id]/draft route.';

ALTER TABLE comms_content_revisions ENABLE ROW LEVEL SECURITY;
-- No anon policy: mirrors comms_content's own write pattern (service-role client
-- only, from session-gated API routes via requireSession() — see gotcha #9 in
-- the Content Workbench engineering notes). Service-role bypasses RLS regardless.

-- ── Indexes to support the new workbench's board query ────────────────────────

CREATE INDEX IF NOT EXISTS idx_comms_content_research_completed
  ON comms_content (research_completed_at) WHERE research_completed_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_comms_content_qa_status
  ON comms_content (qa_status) WHERE qa_status IS NOT NULL;
