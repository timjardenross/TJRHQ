-- 2026-09-15 adversarial review (Fix Next #6): content_signals.event_id
-- documented itself as "FK to intelligence_events.event_id via cast" but
-- no constraint ever enforced it. Live readers (lcars-portal's intelligence
-- route, signalsToOpportunities.ts, signal_opportunity_converter.py) join
-- on it as a plain text filter, so an orphaned row doesn't error -- it
-- just silently returns zero rows, which is indistinguishable from "no
-- signal" at the call site.
--
-- Orphan audit run live before this migration: 66 of 7318 rows (0.9%)
-- already reference a non-existent intelligence_events.event_id. Added
-- NOT VALID rather than deleting those rows or requiring a backfill
-- decision here -- this enforces the constraint for every new/updated row
-- from today forward without touching existing data or blocking on a
-- decision about the 66 pre-existing orphans (follow-up: `VALIDATE
-- CONSTRAINT` once those are triaged -- see the audit query below to find
-- them again).
--
-- Audit query to re-find current orphans:
--   SELECT cs.id FROM content_signals cs
--   LEFT JOIN intelligence_events ie ON ie.event_id = cs.event_id
--   WHERE ie.event_id IS NULL;
ALTER TABLE content_signals
  ADD CONSTRAINT content_signals_event_id_fk
  FOREIGN KEY (event_id) REFERENCES intelligence_events(event_id)
  ON DELETE CASCADE
  NOT VALID;
