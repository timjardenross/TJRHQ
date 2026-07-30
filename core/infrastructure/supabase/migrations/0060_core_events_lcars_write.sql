-- Migration 0060 — core_events: LCARS Portal write access
-- MSN-0328 Wave 2: converging the mission-lifecycle domain onto the
-- canonical Captain Brief event pipeline (core/platform/event_bus.py)
-- requires the LCARS Portal's mission API routes (Next.js, anon-key
-- session client) to insert new events. core_events (migration 0055)
-- enabled RLS with no policies at all -- deny-by-default, unlike the
-- older, policy-free `missions` table this same app already writes to.
-- Matches this platform's existing convention for app-writable tables
-- (e.g. 0034_advisory_sessions.sql) -- open WITH CHECK, no per-user
-- isolation, consistent with this being a single-Captain platform.

CREATE POLICY "core_events_insert" ON core_events
  FOR INSERT WITH CHECK (true);
