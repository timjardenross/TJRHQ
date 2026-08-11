-- Migration 0137 — insight_outcomes.aggregation_key (Captain directive,
-- 2026-08-10)
--
-- The evolved-insight-generation cron (added today, intelligence/scheduler.py
-- _evolved_insight_generation_job) surfaced a real quality gap on its first
-- live run: 'aggregation'-kind Relationships (understanding_engine.py's
-- _aggregation_relationships(), surfacing the Attention Engine's own
-- SHOULD_BE_AGGREGATED groups) describe a structurally PERMANENT property
-- of bursty domains (Downdetector collection bursts, daily readiness
-- snapshots, a wellness event that fires on every decision cycle including
-- no-ops) -- not a novel finding. With no dedup, the same non-actionable
-- claim re-surfaced on nearly every run. This column lets the pipeline
-- recognise "I already told the Captain about this exact
-- domain:event_type cluster recently" and skip re-synthesizing it --
-- see understanding_engine.py's Relationship.aggregation_key and
-- insight_engine.py's generate_insights(recent_aggregation_keys=...).
--
-- Nullable: only 'aggregation'-kind relationships populate it;
-- shared_mission/temporal_sequence relationships and conflicts have no
-- single (domain, event_type) identity to dedupe on and leave this null.

ALTER TABLE insight_outcomes
    ADD COLUMN IF NOT EXISTS aggregation_key text;

CREATE INDEX IF NOT EXISTS insight_outcomes_aggregation_key_idx
    ON insight_outcomes (aggregation_key)
    WHERE aggregation_key IS NOT NULL;

COMMENT ON COLUMN insight_outcomes.aggregation_key IS
  'domain:event_type identity of the Attention Engine SHOULD_BE_AGGREGATED '
  'group this insight was synthesized from, when source_kind=relationship '
  'and kind=aggregation. Used to suppress re-synthesizing the same '
  'structurally-permanent cluster on every scheduled run.';
