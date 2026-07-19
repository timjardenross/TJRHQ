-- Migration 0035 — anon read policies for intelligence tables
-- RLS was enabled but no SELECT policy existed for anon role,
-- causing the portal to return empty results for signals, sources, and source health.

CREATE POLICY "anon_read" ON intelligence_events
  FOR SELECT USING (true);

CREATE POLICY "anon_read" ON intelligence_source_registry
  FOR SELECT USING (true);

CREATE POLICY "anon_read" ON intelligence_source_health
  FOR SELECT USING (true);
