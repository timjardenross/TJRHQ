-- ============================================================
-- Migration 0023 — Engineering & Delivery Officer (EDO) instrumentation
-- MSN-EDO-001 → EDO-002/004/008. Additive + idempotent.
--
-- Instruments the mission delivery lifecycle without changing existing
-- `missions` semantics:
--   1. edo_canonical_state(status)  — normalises the 9 statuses to a canonical
--      delivery lifecycle (proposed/planned/in_progress/in_review/validated/
--      closed/archived/blocked).
--   2. mission_state_transitions    — records real state transitions going
--      forward (timestamp + actor + evidence), fixing the "0-day binary" gap.
--   3. mission_delivery (view)      — normalised, age/cycle-annotated mission rows
--      for the delivery dashboard and engine.
--   4. mission_delivery_metrics (view) — cycle time, completion, PR, outcome,
--      rework roll-up.
-- ============================================================

-- 1. Canonical delivery-state mapping
CREATE OR REPLACE FUNCTION edo_canonical_state(s text)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE lower(coalesce(s, ''))
    WHEN 'proposed' THEN 'proposed'
    WHEN 'designed' THEN 'planned'
    WHEN 'implemented' THEN 'in_progress'
    WHEN 'tested' THEN 'in_review'
    WHEN 'awaiting number one review' THEN 'in_review'
    WHEN 'validated' THEN 'validated'
    WHEN 'awaiting xo approval' THEN 'validated'
    WHEN 'closed' THEN 'closed'
    WHEN 'archived' THEN 'archived'
    WHEN 'blocked' THEN 'blocked'
    ELSE 'other'
  END
$$;

COMMENT ON FUNCTION edo_canonical_state(text) IS
  'EDO: maps a mission.status to the canonical delivery lifecycle state.';

-- 2. State-transition log (the instrumentation the live data was missing)
CREATE TABLE IF NOT EXISTS mission_state_transitions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mission_id  text NOT NULL,
  from_state  text,
  to_state    text NOT NULL,
  actor       text,
  evidence    text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mst_mission
  ON mission_state_transitions (mission_id, created_at DESC);

COMMENT ON TABLE mission_state_transitions IS
  'EDO MSN-EDO-004: real mission state transitions with timestamp/actor/evidence. '
  'Closes the bottleneck-visibility gap (missions previously went Designed→Closed '
  'with no intermediate states recorded).';

-- 3. Normalised, annotated delivery view
CREATE OR REPLACE VIEW mission_delivery AS
SELECT
  m.id,
  m.mission_id,
  m.title,
  lower(coalesce(m.task_type, 'unspecified')) AS task_type_norm,
  coalesce(nullif(trim(m.priority), ''), 'unset')  AS priority_norm,
  m.status,
  edo_canonical_state(m.status) AS delivery_state,
  m.pr_url,
  m.branch_name,
  m.repo,
  m.outcome_rating,
  m.rework_of,
  m.created_by,
  m.created_at,
  m.updated_at,
  m.closed_at,
  (CURRENT_DATE - m.created_at::date) AS age_days,
  CASE WHEN edo_canonical_state(m.status) IN ('closed', 'archived')
       THEN round(extract(epoch FROM (coalesce(m.closed_at, m.updated_at) - m.created_at)) / 86400.0, 1)
  END AS cycle_days
FROM missions m;

COMMENT ON VIEW mission_delivery IS
  'EDO MSN-EDO-002: normalised mission rows (canonical state, normalised '
  'task_type/priority, age + cycle days) for the delivery dashboard and engine.';

-- 4. Delivery metrics roll-up
CREATE OR REPLACE VIEW mission_delivery_metrics AS
SELECT
  count(*)                                                                          AS total,
  count(*) FILTER (WHERE edo_canonical_state(status) NOT IN ('closed','archived'))  AS open_count,
  count(*) FILTER (WHERE edo_canonical_state(status) = 'closed')                    AS closed_count,
  count(*) FILTER (WHERE edo_canonical_state(status) = 'blocked')                   AS blocked_count,
  count(*) FILTER (WHERE pr_url IS NOT NULL AND pr_url <> '')                       AS with_pr,
  count(*) FILTER (WHERE outcome_rating IS NOT NULL)                                AS with_outcome,
  count(*) FILTER (WHERE rework_of IS NOT NULL)                                     AS rework_count,
  round(avg(CASE WHEN edo_canonical_state(status) IN ('closed','archived')
                 THEN extract(epoch FROM (coalesce(closed_at, updated_at) - created_at)) / 86400.0 END)::numeric, 1)
                                                                                    AS avg_cycle_days
FROM missions;

COMMENT ON VIEW mission_delivery_metrics IS
  'EDO MSN-EDO-008: delivery metrics roll-up (open/closed/blocked, PR rate, '
  'outcome rate, rework rate, average cycle days).';
