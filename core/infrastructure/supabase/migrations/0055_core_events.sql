-- ============================================================
-- Migration 0055 — Core Events (SUOC Wave 3, Workstream B: Event Bus)
-- Canonical event log, designed in MSN-0210C §6 and MSN-0210 §9,
-- generalised here platform-wide. Additive — does not replace any
-- existing domain table (research_memory, intelligence_events, etc.);
-- domain services keep their own detailed records and additionally
-- emit a thin core_events row pointing back at them via linked_*.
-- ============================================================

CREATE TABLE IF NOT EXISTS core_events (
    event_id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type          text        NOT NULL,   -- e.g. 'mission.approved', 'research.completed', 'task.created'
    domain              text        NOT NULL,   -- which Intelligence Domain / Platform Capability, or 'system'
    source              text        NOT NULL,   -- originating module, e.g. 'research_orchestration'
    occurred_at         timestamptz NOT NULL DEFAULT now(),
    importance          smallint    CHECK (importance BETWEEN 0 AND 100),
    confidence          smallint    CHECK (confidence BETWEEN 0 AND 100),
    relevance           smallint    CHECK (relevance BETWEEN 0 AND 100),
    linked_entities     jsonb       NOT NULL DEFAULT '[]',
    linked_missions     jsonb       NOT NULL DEFAULT '[]',
    linked_documents    jsonb       NOT NULL DEFAULT '[]',
    recommended_action  text,
    status              text        NOT NULL DEFAULT 'new'
                          CHECK (status IN ('new', 'acknowledged', 'acted_on', 'dismissed', 'superseded')),
    created_at          timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE core_events IS
  'SUOC Wave 3: canonical cross-platform event log (MSN-0210C §6 / MSN-0210 §9). '
  'A thin index over domain-specific detail tables, not a replacement for them. '
  'Populated via core/platform/event_bus.py publish_event().';

-- RLS: service_role bypasses; no public read/write (matches other platform tables)
ALTER TABLE core_events ENABLE ROW LEVEL SECURITY;

-- Poll/query indexes (this is a poll-based bus — no message broker in this platform,
-- consumers query "events since I last checked", not a push subscription)
CREATE INDEX IF NOT EXISTS core_events_occurred_at_idx
    ON core_events (occurred_at DESC);

CREATE INDEX IF NOT EXISTS core_events_type_idx
    ON core_events (event_type);

CREATE INDEX IF NOT EXISTS core_events_domain_idx
    ON core_events (domain);

CREATE INDEX IF NOT EXISTS core_events_status_idx
    ON core_events (status);
