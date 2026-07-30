-- ============================================================
-- Migration 0062 — core_events: Complete RLS policy suite
-- Fixes degradation: 0060's INSERT policy lacked role specification
-- (applies only to `public` role), and SELECT/UPDATE were missing.
-- This migration completes the RLS contract for all operations
-- (poll_events, mark_event_status, publish_event variants).
-- ============================================================

-- 1. Fix INSERT: explicitly allow authenticated (LCARS Portal) and anon
--    (future integrations) to insert. Both already have service-role as
--    fallback for safety-critical ops, so this layer is defense-in-depth.
DROP POLICY IF EXISTS "core_events_insert" ON core_events;
CREATE POLICY "core_events_insert_authenticated" ON core_events
  FOR INSERT
  TO authenticated, anon
  WITH CHECK (true);

-- 2. Add SELECT: allow authenticated and anon to read (poll_events contract).
--    No row filtering — this table is a published event log, not user-scoped.
CREATE POLICY "core_events_select" ON core_events
  FOR SELECT
  TO authenticated, anon
  USING (true);

-- 3. Add UPDATE: allow authenticated and anon to mark status. Same reasoning —
--    this is a shared audit log that any participant can acknowledge/act on.
CREATE POLICY "core_events_update" ON core_events
  FOR UPDATE
  TO authenticated, anon
  USING (true)
  WITH CHECK (true);

COMMENT ON POLICY "core_events_insert_authenticated" ON core_events IS
  'Allows LCARS Portal (authenticated) and future anon integrations to publish. '
  'Service-role client is used for safety-critical callers (Python backend), '
  'making this layer defense-in-depth.';

COMMENT ON POLICY "core_events_select" ON core_events IS
  'Allows poll_events() to read the shared event log.';

COMMENT ON POLICY "core_events_update" ON core_events IS
  'Allows mark_event_status() to advance event state. Shared audit log — '
  'any participant can acknowledge/act on published events.';
