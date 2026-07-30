-- ============================================================
-- Migration 0016 — ROS Schema Fields
-- ROS-001 v1.1 — Stage 1 Recovery Operating System
-- Date: 2026-06-19
--
-- Adds three new fields required by Sprint 0:
--   health_daily_logs.nervous_system_state
--   captains_log_entries.expressive_write_done
--   captains_log_entries.pleasure_creativity_marker
--
-- APPLIED: 2026-06-19 via Supabase MCP
-- ============================================================

-- ── health_daily_logs: nervous_system_state ─────────────────────
-- First-class daily input per ROS-001 v1.1.
-- Captures ANS activation and threat response — explicitly distinct
-- from mood (emotional tone). Nullable: absence means unrecorded,
-- treated as neutral (score 60) in Recovery Score computation.

ALTER TABLE health_daily_logs
  ADD COLUMN IF NOT EXISTS nervous_system_state text
    CHECK (nervous_system_state IN ('calm', 'activated', 'dysregulated'));

COMMENT ON COLUMN health_daily_logs.nervous_system_state IS
  'ROS-001 v1.1: Perceived nervous system activation state (Hanscom model). '
  'Distinct from mood (emotional tone). calm = low anxiety, regulated; '
  'activated = elevated alertness, managing; dysregulated = high anxiety/anger, fight-or-flight. '
  'Carries 20% weight in Recovery Score formula and applies a multiplicative modifier. '
  'Nullable — absence treated as neutral (score 60, modifier 1.0) in computation.';

-- ── captains_log_entries: expressive_write_done ─────────────────
-- Tracks completion of Hanscom expressive writing protocol.
-- PRIVACY: completion flag only. No content is stored, inferred, or requested.

ALTER TABLE captains_log_entries
  ADD COLUMN IF NOT EXISTS expressive_write_done boolean;

COMMENT ON COLUMN captains_log_entries.expressive_write_done IS
  'ROS-001 v1.1 / Hanscom expressive writing protocol: '
  'Did the Captain complete expressive writing today (writing down and setting aside '
  'anxious, angry, or distressing thoughts)? Completion flag only — content is not stored. '
  'Medical Officer uses absence pattern in weekly synthesis to recommend when not practised '
  'during elevated-load periods. Nullable — absence means not recorded.';

-- ── captains_log_entries: pleasure_creativity_marker ────────────
-- Optional one-word marker for pleasurable or creative activity.
-- Feeds Life Participation Score presence/absence signal only.
-- Never a target or minimum. Content is the Captain's own language.

ALTER TABLE captains_log_entries
  ADD COLUMN IF NOT EXISTS pleasure_creativity_marker text;

COMMENT ON COLUMN captains_log_entries.pleasure_creativity_marker IS
  'ROS-001 v1.1: Short optional marker for pleasurable, creative, or intrinsically '
  'motivated activity today (e.g. music, walk, reading, swim, cooking). '
  'Done for its own sake — not for outcome. '
  'Presence/absence (not content) feeds Life Participation Score creativity component (20% weight). '
  'Never a target or minimum. Nullable.';
