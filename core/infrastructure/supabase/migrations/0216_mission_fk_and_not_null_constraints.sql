-- Migration 0216: mission FK constraints + NOT NULL on missions.status/created_at
-- Adversarial review 2026-09-15, item #14.
--
-- mission_state_transitions.mission_id and mission_execution_events.mission_id
-- had no FK to missions(mission_id) despite the sibling decisions.mission_id
-- having one — 5 live orphan rows existed (2 explicitly marked "test note",
-- 3 from a legacy pre-ID-standardization dispatch that never landed a real
-- missions row). Deleted before adding the constraint (confirmed via
-- pg_stat_user_tables / direct row inspection these were genuinely
-- disposable, not real history).
--
-- missions.status/created_at were nullable despite being load-bearing for
-- basically every workflow/reporting query on this table (a NULL status
-- silently falls through every `WHERE status = ...` filter instead of
-- erroring). Confirmed zero existing NULLs (157/157 rows populated) before
-- adding NOT NULL.

DELETE FROM mission_state_transitions WHERE mission_id IN ('MSN-EDO-DISPATCH-001', 'MSN-0001');
DELETE FROM mission_execution_events WHERE mission_id IN ('MSN-EDO-DISPATCH-001', 'MSN-0001');

ALTER TABLE mission_state_transitions
  ADD CONSTRAINT mission_state_transitions_mission_id_fkey
  FOREIGN KEY (mission_id) REFERENCES missions(mission_id);

ALTER TABLE mission_execution_events
  ADD CONSTRAINT mission_execution_events_mission_id_fkey
  FOREIGN KEY (mission_id) REFERENCES missions(mission_id);

ALTER TABLE missions ALTER COLUMN status SET NOT NULL;
ALTER TABLE missions ALTER COLUMN created_at SET NOT NULL;

-- captured_items.research_mission_id is NOT touched by an FK here — it
-- turned out to be a different bug entirely (see core/inbox/orchestrator.py
-- fix in the same commit as this migration): every non-null value was
-- self-referential (row's own id echoed back), not a real reference to
-- missions or anything else, because the caller passed the captured_items
-- row's own id as the mission_id seed into ResearchOrchestrator, which only
-- auto-generates a real MSN-YYYYMMDD-HHMMSS id when none is given. Fixed at
-- the call site; the 10 existing self-referential values were nulled out
-- (UPDATE captured_items SET research_mission_id = NULL WHERE id::text =
-- research_mission_id — applied directly, not repeated here since it's a
-- one-time data cleanup, not a repeatable schema change).
