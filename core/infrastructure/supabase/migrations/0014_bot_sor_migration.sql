-- MSN-BOT-SOR: Bot System of Record Migration
-- Removes bot dependency on mission-index.txt, missions.db, and notifications.db.
-- These three tables make Supabase the authoritative store for:
--   1. Mission state transitions (bot-originated status changes)
--   2. Escalation tracking (replaces notifications.db SQLite)
--   3. Escalation event log (replaces alert_events SQLite table)
--
-- Apply via: Supabase Dashboard → SQL Editor, or supabase db push

-- ---------------------------------------------------------------------------
-- 1. mission_state_transitions
--    Records every bot-originated (or any) mission status change.
--    The Command Centre also writes here via PATCH /api/v1/missions/:id/status.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS mission_state_transitions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mission_id      TEXT NOT NULL,
    from_status     TEXT,
    to_status       TEXT NOT NULL,
    transitioned_by TEXT,
    transitioned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    note            TEXT,
    source          TEXT DEFAULT 'slack-bot'  -- 'slack-bot', 'command-centre', 'manual'
);

CREATE INDEX IF NOT EXISTS idx_mst_mission_id
    ON mission_state_transitions(mission_id);
CREATE INDEX IF NOT EXISTS idx_mst_transitioned_at
    ON mission_state_transitions(transitioned_at DESC);

COMMENT ON TABLE mission_state_transitions IS
    'Audit log of all mission status transitions. Written by slack-bot and command-centre.';


-- ---------------------------------------------------------------------------
-- 2. escalation_history
--    Replaces the escalation_history table in notifications.db (SQLite).
--    Tracks one row per (mission_id, alert_type) combination.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS escalation_history (
    id                  TEXT PRIMARY KEY,  -- alert_key: "{mission_id}:{alert_type}"
    mission_id          TEXT NOT NULL,
    alert_type          TEXT NOT NULL,
    original_severity   TEXT NOT NULL,
    current_severity    TEXT NOT NULL,
    first_detected      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_notified       TIMESTAMPTZ,
    notification_count  INTEGER NOT NULL DEFAULT 0,
    resolved_at         TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_esc_history_mission_id
    ON escalation_history(mission_id);
CREATE INDEX IF NOT EXISTS idx_esc_history_resolved
    ON escalation_history(resolved_at) WHERE resolved_at IS NULL;

COMMENT ON TABLE escalation_history IS
    'Escalation lifecycle per (mission, alert_type). Replaces notifications.db SQLite store.';


-- ---------------------------------------------------------------------------
-- 3. escalation_events
--    Replaces the alert_events table in notifications.db (SQLite).
--    Event log: one row per notification, acknowledgement, or resolution.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS escalation_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    escalation_id   TEXT NOT NULL REFERENCES escalation_history(id),
    event_type      TEXT NOT NULL,  -- 'created', 'notified', 'acknowledged', 'resolved'
    severity        TEXT,
    event_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata        JSONB
);

CREATE INDEX IF NOT EXISTS idx_esc_events_escalation_id
    ON escalation_events(escalation_id);
CREATE INDEX IF NOT EXISTS idx_esc_events_event_at
    ON escalation_events(event_at DESC);
CREATE INDEX IF NOT EXISTS idx_esc_events_type
    ON escalation_events(event_type);

COMMENT ON TABLE escalation_events IS
    'Event log for escalation lifecycle (created/notified/acknowledged/resolved). Replaces alert_events SQLite.';
