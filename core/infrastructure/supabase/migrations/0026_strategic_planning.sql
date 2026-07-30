-- ============================================================
-- Migration 0026 — Strategic Planning Command MVP (MSN-SPC-001 WP2/WP3)
-- A thin strategic layer ABOVE missions: one objectives store + one nullable
-- link on the existing missions table. No parallel mission store, no new
-- dashboard. Additive + idempotent. Reuses the Active-Priorities P0–P5 scale and
-- the {closed,archived} terminal-status convention (mission_load.py).
-- ============================================================

-- WP2: Objective Registry — the only new store the strategic layer introduces.
CREATE TABLE IF NOT EXISTS strategic_objectives (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  objective_id text UNIQUE,                       -- human key, e.g. OBJ-HEALTH-01
  domain       text NOT NULL,                     -- one of the six strategic domains
  title        text NOT NULL,
  description  text,
  status       text NOT NULL DEFAULT 'active',
  priority     text DEFAULT 'P2',                 -- reuses the P0–P5 scale
  owner        text,
  horizon      text,                              -- e.g. 'Q3 2026', 'this year'
  created_at   timestamptz DEFAULT now(),
  updated_at   timestamptz DEFAULT now(),
  CONSTRAINT strategic_objectives_domain_chk CHECK (domain IN (
    'Health & Human Systems',
    'Career & Professional Impact',
    'Starship Endeavour',
    'Coaching Enterprise',
    'Financial & Lifestyle',
    'Learning & Growth')),
  CONSTRAINT strategic_objectives_status_chk CHECK (status IN ('active','achieved','paused','dropped')),
  CONSTRAINT strategic_objectives_priority_chk CHECK (priority IS NULL OR priority IN ('P0','P1','P2','P3','P4','P5'))
);

COMMENT ON TABLE strategic_objectives IS
  'SPC-001 WP2: finite, outcome-shaped targets, each rolling up to exactly one of '
  'the six strategic domains. The strategic layer above missions. Captain-owned.';

-- WP3: Mission alignment — a single nullable link on the EXISTING missions table
-- (no parallel mission store). A mission with NULL link is an orphan (visible,
-- not blocked).
ALTER TABLE missions
  ADD COLUMN IF NOT EXISTS strategic_objective_id text;

COMMENT ON COLUMN missions.strategic_objective_id IS
  'SPC-001 WP3: optional link to strategic_objectives.objective_id. NULL = orphan '
  '(a mission not yet aligned to a strategic objective).';

CREATE INDEX IF NOT EXISTS idx_missions_strategic_objective
  ON missions (strategic_objective_id);

-- WP3/WP4: Objective progress, derived from linked missions (reporting only).
CREATE OR REPLACE VIEW strategic_objective_progress AS
SELECT
  o.objective_id,
  o.domain,
  o.title,
  o.status,
  o.priority,
  count(m.id)                                                                  AS linked_missions,
  count(m.id) FILTER (WHERE lower(coalesce(m.status,'')) NOT IN ('closed','archived')) AS open_missions,
  count(m.id) FILTER (WHERE lower(coalesce(m.status,'')) IN ('closed','archived'))     AS completed_missions,
  round(
    count(m.id) FILTER (WHERE lower(coalesce(m.status,'')) IN ('closed','archived'))::numeric
    / nullif(count(m.id), 0), 2)                                               AS completion_rate
FROM strategic_objectives o
LEFT JOIN missions m ON m.strategic_objective_id = o.objective_id
GROUP BY o.objective_id, o.domain, o.title, o.status, o.priority;

COMMENT ON VIEW strategic_objective_progress IS
  'SPC-001 WP3/WP4: per-objective linked/open/completed mission counts + completion '
  'rate. Feeds the Daily Operating Picture strategic focus. Reporting only.';

-- WP3: Orphan missions — open missions with no strategic objective (information,
-- not failure).
CREATE OR REPLACE VIEW strategic_orphan_missions AS
SELECT
  mission_id,
  title,
  status,
  priority
FROM missions
WHERE strategic_objective_id IS NULL
  AND lower(coalesce(status,'')) NOT IN ('closed','archived');

COMMENT ON VIEW strategic_orphan_missions IS
  'SPC-001 WP3: open missions not yet aligned to a strategic objective. Surfaced '
  'in the fortnightly objective review so the Captain can adopt or retire them.';
