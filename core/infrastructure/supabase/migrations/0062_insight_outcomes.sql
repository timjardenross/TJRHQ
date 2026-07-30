-- Migration 0062 — Insight Outcomes (MSN-0329 Phase 4, Intelligence
-- Optimisation & Expansion)
--
-- Objectives 2/3/5 of Phase 4 (continuous measurement, evidence-based
-- tuning, confidence scoring built from observed performance rather
-- than static assumptions) all require a durable record of what the
-- Insight/Reasoning Engines actually generated and whether it turned
-- out to be useful. None of that can happen without this table existing
-- first — Phase 3 produced exactly one real insight and had nowhere to
-- record whether it was ever acted on.
--
-- Deliberately a NEW, dedicated table, not a reuse of core_events: an
-- insight is a derived intelligence PRODUCT (the output of the
-- Understanding/Insight/Reasoning pipeline), not a domain signal core_events
-- indexes — conflating the two would mean an insight's own lifecycle
-- (generated -> shown to Captain -> outcome recorded) polluting the
-- domain event stream it was itself derived FROM.

CREATE TABLE IF NOT EXISTS insight_outcomes (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    generated_at        timestamptz NOT NULL,
    source_kind         text        NOT NULL CHECK (source_kind IN ('relationship', 'conflict')),
    source_domains      jsonb       NOT NULL DEFAULT '[]',
    evidence_chain      jsonb       NOT NULL DEFAULT '[]',  -- core_events.event_id values this insight traced to

    -- What the Insight Engine produced
    observation         text        NOT NULL,
    why_it_matters       text        NOT NULL,
    potential_impact     text        NOT NULL,
    insight_confidence   smallint    CHECK (insight_confidence BETWEEN 0 AND 100),

    -- What the Reasoning Engine produced, if it ran (nullable — an
    -- insight can exist without a recommendation if that stage failed
    -- or was skipped)
    recommended_action     text,
    alternatives            jsonb    DEFAULT '[]',
    trade_offs              text,
    expected_outcome        text,
    recommendation_confidence smallint CHECK (recommendation_confidence BETWEEN 0 AND 100),

    -- Outcome — null until someone (today: an engineer reviewing
    -- results; eventually: the Captain, via a real UI) records one.
    -- This is the field objectives 2/3/5 are actually built on.
    outcome             text        CHECK (outcome IN ('useful', 'not_useful', 'incorrect', 'pending') ) DEFAULT 'pending',
    outcome_note         text,
    outcome_recorded_at  timestamptz,

    created_at          timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE insight_outcomes IS
  'MSN-0329 Phase 4: durable record of every Insight/Recommendation the '
  'Cognitive Core pipeline generates, plus its eventual outcome. The '
  'evidence base for objective 5 (confidence scoring from observed '
  'performance) and objective 3 (evidence-based prompt/threshold tuning) '
  '-- neither is possible without this table accumulating real history.';

ALTER TABLE insight_outcomes ENABLE ROW LEVEL SECURITY;

-- Matches this repo's established convention for app-writable tables
-- (e.g. 0034_advisory_sessions.sql) -- open WITH CHECK, no per-user
-- isolation, single-Captain platform.
CREATE POLICY "insight_outcomes_all" ON insight_outcomes
  FOR ALL USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS insight_outcomes_generated_at_idx
    ON insight_outcomes (generated_at DESC);

CREATE INDEX IF NOT EXISTS insight_outcomes_outcome_idx
    ON insight_outcomes (outcome);
