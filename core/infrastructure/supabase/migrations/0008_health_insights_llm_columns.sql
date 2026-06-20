-- ============================================================
-- Migration 0008 — health_insights Sprint A columns
-- Date: 2026-06-13
--
-- PURPOSE
-- Adds Sprint A intelligence columns to the health_insights table.
-- These columns store the outputs of the new baseline, correlation,
-- and LLM narrative capabilities introduced in weekly_synthesis.py v2.0.
--
-- All columns are nullable — rows written by synthesis v1.0 (before
-- this migration) remain valid. The upsert path in weekly_synthesis.py
-- falls back to legacy columns if this migration has not been applied.
--
-- APPLY: Supabase SQL editor → Run
-- ============================================================

-- 30-day baseline statistics
ALTER TABLE health_insights
    ADD COLUMN IF NOT EXISTS baseline_30d        JSONB,
    ADD COLUMN IF NOT EXISTS baseline_comparison JSONB;

-- Deterministic correlation findings (array of human-readable strings)
ALTER TABLE health_insights
    ADD COLUMN IF NOT EXISTS deterministic_findings JSONB;

-- CPAP compliance rate (0.0–1.0) for the synthesis period
ALTER TABLE health_insights
    ADD COLUMN IF NOT EXISTS cpap_compliance_rate NUMERIC(4,3);

-- Top wins logged during the week (array of strings)
ALTER TABLE health_insights
    ADD COLUMN IF NOT EXISTS wins_this_week JSONB;

-- Intention-delivery summary
ALTER TABLE health_insights
    ADD COLUMN IF NOT EXISTS intention_delivery JSONB;

-- LLM-generated intelligence narrative (structured JSON object)
-- Keys: situation, patterns_noticed, what_it_means, recommended_focus, watch_items
ALTER TABLE health_insights
    ADD COLUMN IF NOT EXISTS llm_narrative JSONB;

-- Provider that generated the narrative (gemini-2.5-flash, mistral-small, etc.)
ALTER TABLE health_insights
    ADD COLUMN IF NOT EXISTS llm_provider TEXT;

-- Whether the LLM narrative is available for this row
ALTER TABLE health_insights
    ADD COLUMN IF NOT EXISTS narrative_available BOOLEAN DEFAULT FALSE;

-- Track synthesis version for schema evolution
ALTER TABLE health_insights
    ADD COLUMN IF NOT EXISTS synthesis_version TEXT;

COMMENT ON COLUMN health_insights.baseline_30d IS
    'Sprint A: 30-day rolling baseline stats (pain_avg, sleep_avg, capacity_avg, n_days)';
COMMENT ON COLUMN health_insights.llm_narrative IS
    'Sprint A: LLM-generated intelligence narrative with situation/patterns/recommendations';
COMMENT ON COLUMN health_insights.narrative_available IS
    'True when llm_narrative was successfully generated; False when synthesis fell back to template';
