-- ============================================================
-- Migration 0025 — Delivery feedback loop (MSN-EDO-003 WP3)
-- Closes the loop from outcomes back to recommendations. Reuses existing stores
-- (human_systems_recommendations / _feedback, missions, mission_execution_events)
-- — no new telemetry store. Additive + idempotent.
-- ============================================================

-- Link a recommendation to the mission it concerned (enables outcome linkage).
ALTER TABLE human_systems_recommendations
  ADD COLUMN IF NOT EXISTS mission_id text;

COMMENT ON COLUMN human_systems_recommendations.mission_id IS
  'EDO-003 WP3: optional link to the mission a recommendation concerned, so '
  'recommendation effectiveness can be related to delivery outcomes.';

-- Recommendation effectiveness, derived from the Helpful/Neutral/Not-Helpful
-- feedback taxonomy (migration 0021). Drives learned confidence adjustments.
CREATE OR REPLACE VIEW recommendation_effectiveness AS
SELECT
  coalesce(domain, 'unspecified') AS domain,
  count(*)                                            AS total,
  count(*) FILTER (WHERE category = 'helpful')        AS helpful,
  count(*) FILTER (WHERE category = 'neutral')        AS neutral,
  count(*) FILTER (WHERE category = 'not_helpful')    AS not_helpful,
  round(count(*) FILTER (WHERE category = 'helpful')::numeric
        / nullif(count(*), 0), 2)                     AS helpful_rate
FROM human_systems_feedback
GROUP BY coalesce(domain, 'unspecified');

COMMENT ON VIEW recommendation_effectiveness IS
  'EDO-003 WP3: helpful-rate by domain from human_systems_feedback. Feeds learned '
  'confidence adjustments into highest_leverage / allocate_capacity. Reporting only '
  '— no autonomous decision-making.';

-- Delivery dispatch health, derived from execution telemetry (migration 0024).
CREATE OR REPLACE VIEW dispatch_health AS
SELECT
  count(*)                                          AS events,
  count(*) FILTER (WHERE status = 'dispatched')     AS dispatched,
  count(*) FILTER (WHERE status = 'pr_opened')      AS pr_opened,
  count(*) FILTER (WHERE status = 'failed')         AS failed,
  count(*) FILTER (WHERE status = 'rolled_back')    AS rolled_back,
  count(DISTINCT mission_id)                         AS missions_dispatched
FROM mission_execution_events;

COMMENT ON VIEW dispatch_health IS
  'EDO-003 WP1/WP4: execution-dispatch health roll-up from mission_execution_events.';
