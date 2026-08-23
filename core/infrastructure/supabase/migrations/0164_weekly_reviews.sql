-- ============================================================
-- Migration 0164 — Weekly Reviews
-- USS Starship Endeavour NCC-170230
--
-- Weekly Review workbench: one row per completed weekly ritual.
-- The review itself is computed live from existing tables (no
-- staging/mirror tables) — this table only persists the OUTCOME of
-- running it: a frozen snapshot (for history/trend) plus free notes,
-- so "review debt" (weeks since last completed review) is queryable
-- and completed reviews don't need to be recomputed to look back on.
--
-- Additive & idempotent. Safe to re-run.
-- ============================================================

CREATE TABLE IF NOT EXISTS weekly_reviews (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Rolling 7-day window this review covers (matches the platform's
    -- established "now - 7 days" convention, not calendar Mon-Sun).
    week_start      date        NOT NULL,
    week_end        date        NOT NULL,

    completed_at    timestamptz,            -- NULL until "mark review complete"
    summary         jsonb,                  -- frozen system-summary counts at completion
    notes           text,                   -- free-form reflection, optional

    created_at      timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE weekly_reviews IS
  'One row per Weekly Review ritual run. The review content itself is '
  'computed live from existing tables at view time; this table only '
  'persists completion state + a frozen summary snapshot for history.';

CREATE UNIQUE INDEX IF NOT EXISTS idx_weekly_reviews_week_start
    ON weekly_reviews (week_start);
CREATE INDEX IF NOT EXISTS idx_weekly_reviews_completed_at
    ON weekly_reviews (completed_at DESC);

ALTER TABLE weekly_reviews ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_full_access" ON weekly_reviews;
CREATE POLICY "service_role_full_access" ON weekly_reviews
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "authenticated_full_access" ON weekly_reviews;
CREATE POLICY "authenticated_full_access" ON weekly_reviews
    FOR ALL TO authenticated USING (true) WITH CHECK (true);
