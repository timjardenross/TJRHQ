-- Migration 0010: lessons_learned table
-- Sprint D — Learning Loop
-- Stores structured lessons from mission closures and retrospectives.
-- Source of truth for lesson surfacing in the recommendation engine.
-- Synced from knowledge/Lessons-Learned.md by lesson_capture.py.

CREATE TABLE IF NOT EXISTS lessons_learned (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lesson_id       TEXT UNIQUE NOT NULL,          -- e.g. "LL-001"
    title           TEXT NOT NULL,
    date_recorded   DATE,
    context         TEXT,
    lesson_text     TEXT,
    outcome         TEXT,
    future_guidance TEXT,
    mission_id      TEXT,                           -- linked mission, if any
    source          TEXT DEFAULT 'manual'           -- 'manual', 'mission_closure', 'backfill'
        CHECK (source IN ('manual', 'mission_closure', 'backfill')),
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Enable RLS
ALTER TABLE lessons_learned ENABLE ROW LEVEL SECURITY;

-- Service role has full access
CREATE POLICY "service_role_full_access" ON lessons_learned
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Anon can read (same as decisions table pattern)
CREATE POLICY "anon_read" ON lessons_learned
    FOR SELECT TO anon USING (true);
