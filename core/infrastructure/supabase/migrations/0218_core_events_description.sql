-- ============================================================
-- Migration 0218 — core_events.description (Briefs/Captain's Brief
-- Consolidation, signal-leakage fix)
--
-- `core_events.recommended_action` had become dual-purposed: a genuine
-- reasoned action proposal for most emitters, but a raw-signal dumping
-- ground for a few (a scraped news headline, a source-health error
-- message, a bare systemd state transition) that had no other field to
-- carry readable content into a push notification. That conflation is
-- exactly how raw signals leaked into "recommendations"/"next actions"/
-- "interrupt-now" items downstream (core/platform/captain_brief_contract.py,
-- captain_brief_orchestrator.py, interrupt_dispatcher.py).
--
-- This column gives those emitters a home for "what happened, in readable
-- form" that is explicitly NOT treated as a recommendation by any
-- downstream consumer. Additive, nullable — no backfill, no behaviour
-- change for existing rows or emitters that don't pass it.
-- ============================================================

ALTER TABLE core_events
    ADD COLUMN IF NOT EXISTS description text;

COMMENT ON COLUMN core_events.description IS
  'Human-readable account of what this event *is* (a headline, an error '
  'message, a state transition) — distinct from recommended_action, which '
  'is reserved for a genuine reasoned action proposal. Populated via '
  'core/platform/event_bus.py publish_event(description=...).';

COMMENT ON COLUMN core_events.recommended_action IS
  'A genuine reasoned action proposal the platform is putting to the '
  'Captain. Do NOT populate with raw signal content (a headline, an '
  'exception message, a bare state string) — use description for that. '
  'core/platform/captain_brief_contract.py::recommendation_from_event() '
  'treats any populated value here as "the platform is recommending '
  'something."';
