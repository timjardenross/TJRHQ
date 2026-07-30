-- Migration 0033: Captain's Daily Briefs persistence table
-- USS-TJR-MSN-0201 — stores every generated daily brief so they are queryable.
--
-- Apply: psql $DATABASE_URL -f 0033_captains_daily_briefs.sql

CREATE TABLE IF NOT EXISTS captains_daily_briefs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brief_type      TEXT NOT NULL CHECK (brief_type IN ('morning', 'midday', 'eod', 'weekly')),
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    brief_date      DATE NOT NULL DEFAULT CURRENT_DATE,
    brief_text      TEXT NOT NULL,
    signals_count   INT DEFAULT 0,
    health_snapshot JSONB,          -- capacity_score, pain_score, sleep_hours at time of generation
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_captains_daily_briefs_date
    ON captains_daily_briefs (brief_date DESC);

CREATE INDEX IF NOT EXISTS idx_captains_daily_briefs_type_date
    ON captains_daily_briefs (brief_type, brief_date DESC);
