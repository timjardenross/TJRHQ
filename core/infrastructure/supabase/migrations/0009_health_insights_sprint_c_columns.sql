-- ============================================================
-- Migration 0009 — health_insights Sprint C columns
-- Date: 2026-06-14
--
-- PURPOSE
-- Adds Sprint C intelligence columns to the health_insights table.
-- These columns store the outputs of the new pain location, mood
-- longitudinal, recovery monitoring, physical capacity, and
-- day-of-week pattern capabilities introduced in weekly_synthesis.py v3.0.
--
-- All columns are nullable — rows written by synthesis v1.0/v2.0
-- remain valid. The upsert path falls back to legacy columns if
-- this migration has not been applied.
--
-- APPLY: Supabase SQL editor → Run
-- PREREQUISITE: Migration 0008 must be applied first.
-- ============================================================

-- Pain location frequency analysis
ALTER TABLE health_insights
    ADD COLUMN IF NOT EXISTS pain_location_analysis JSONB;

-- Mood longitudinal trend and distribution
ALTER TABLE health_insights
    ADD COLUMN IF NOT EXISTS mood_trend_30d JSONB;

-- Recovery status classification
ALTER TABLE health_insights
    ADD COLUMN IF NOT EXISTS recovery_status TEXT;

-- Physical capacity trajectory analysis
ALTER TABLE health_insights
    ADD COLUMN IF NOT EXISTS physical_capacity_analysis JSONB;

-- Day-of-week pain pattern (populated when ≥2 entries per weekday)
ALTER TABLE health_insights
    ADD COLUMN IF NOT EXISTS dow_pain_pattern JSONB;

-- Day-of-week energy pattern
ALTER TABLE health_insights
    ADD COLUMN IF NOT EXISTS dow_energy_pattern JSONB;

COMMENT ON COLUMN health_insights.pain_location_analysis IS
    'Sprint C: Frequency analysis of pain_location field — location_counts, most_common';
COMMENT ON COLUMN health_insights.mood_trend_30d IS
    'Sprint C: Mood trend over 7-day and 30-day windows with distribution';
COMMENT ON COLUMN health_insights.recovery_status IS
    'Sprint C: Recovery classification — Active Recovery / Stable / Declining / Acute / Insufficient Data';
COMMENT ON COLUMN health_insights.physical_capacity_analysis IS
    'Sprint C: Better/Same/Worse trajectory with streak and distribution';
COMMENT ON COLUMN health_insights.dow_pain_pattern IS
    'Sprint C: Day-of-week pain averages (populated when sufficient data)';
COMMENT ON COLUMN health_insights.dow_energy_pattern IS
    'Sprint C: Day-of-week energy averages (populated when sufficient data)';
