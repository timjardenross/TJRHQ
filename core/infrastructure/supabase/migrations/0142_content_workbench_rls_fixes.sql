-- Content Workbench RLS review (2026-08-11):
-- 1. content_signals still had the anon_read policy from migration 0036
--    ("mirrors 0035 pattern") — 0035's sibling tables (intelligence_events,
--    intelligence_briefs, intelligence_source_registry) had this same
--    world-readable anon policy fixed on 2026-08-09; content_signals was
--    missed. It carries Captain-only content strategy (suggested_angle,
--    captain_focus, suppressed decisions) and is only ever read through
--    authenticated app routes (api/comms, api/intelligence) — no anon
--    consumer exists. Lock it to authenticated, matching the 2026-08-09 fix.
-- 2. comms_content and comms_content_revisions already carry a live
--    "auth_read" (authenticated-only) policy, applied outside migration
--    history at some point. Codifying it here so a schema rebuild/reset
--    doesn't silently reopen either table — the exact risk flagged for
--    Human Systems' RLS in the 2026-08-09 review.

DROP POLICY IF EXISTS anon_read_content_signals ON content_signals;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'content_signals' AND policyname = 'auth_read'
  ) THEN
    EXECUTE 'CREATE POLICY auth_read ON content_signals
      FOR SELECT TO authenticated USING (true)';
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'comms_content' AND policyname = 'auth_read'
  ) THEN
    EXECUTE 'CREATE POLICY auth_read ON comms_content
      FOR SELECT TO authenticated USING (true)';
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'comms_content_revisions' AND policyname = 'auth_read'
  ) THEN
    EXECUTE 'CREATE POLICY auth_read ON comms_content_revisions
      FOR SELECT TO authenticated USING (true)';
  END IF;
END $$;

GRANT SELECT ON content_signals, comms_content, comms_content_revisions TO authenticated;
REVOKE SELECT ON content_signals FROM anon;
