-- ============================================================
-- Migration 0191 — Explicit user selection for Today (Ready Room)
-- USS Starship Endeavour NCC-170230
--
-- Human Execution Loop mission: Human Systems context may shrink the
-- Today capacity cap (rankToday's capacityLimit) on a constrained day,
-- but a task the Captain has explicitly chosen to keep in Today must
-- never be silently dropped by that shrink (mission §13/§45, tested by
-- §56 "user-selected Today task remains selected"). There was no
-- existing column distinguishing "the algorithm ranked this into Today"
-- from "the Captain pinned this into Today" — pinned_today closes that
-- gap without inventing a second task store or a scoring override.
--
-- Additive & idempotent. Safe to re-run.
-- ============================================================

ALTER TABLE personal_tasks
    ADD COLUMN IF NOT EXISTS pinned_today boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN personal_tasks.pinned_today IS
  'Captain explicitly chose to keep this in Today. rankToday() always includes pinned, non-completed, non-blocked tasks ahead of the capacity-driven cap — Human Systems context can shrink how many additional tasks are ranked in, never remove a pinned one.';
