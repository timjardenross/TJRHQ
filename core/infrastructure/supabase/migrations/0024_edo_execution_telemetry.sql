-- ============================================================
-- Migration 0024 — EDO execution telemetry (MSN-EDO-003 WP1)
-- Records the execution-dispatch lifecycle (distinct from state transitions):
-- which backend, which branch, dispatch status, PR, failures, rollbacks.
-- Reuses mission_state_transitions for state; this is dispatch telemetry only.
-- Additive + idempotent.
-- ============================================================

CREATE TABLE IF NOT EXISTS mission_execution_events (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mission_id  text NOT NULL,
  branch      text,
  backend     text,         -- claude_code | manual | generic
  status      text NOT NULL -- dispatched | pr_opened | failed | rolled_back
                CHECK (status IN ('dispatched','pr_opened','failed','rolled_back')),
  pr_url      text,
  detail      text,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mee_mission
  ON mission_execution_events (mission_id, created_at DESC);

COMMENT ON TABLE mission_execution_events IS
  'EDO MSN-EDO-003 WP1: execution-dispatch telemetry + audit trail (backend, '
  'branch, dispatch status, PR, failures/rollbacks). Complements '
  'mission_state_transitions (state) — not a duplicate store.';
