-- Migration 0238: harden capacity_checkins_today and anon table grants
--
-- Addresses TJR-Life-iOS register D-020 (security-definer view, advisor ERROR)
-- and D-021 (anon holds write/TRUNCATE grants on public tables).
-- Not run automatically; the owner decides when.
--
-- 1. capacity_checkins_today ran with its owner's rights, and anon held SELECT
--    on it by default privileges, so the view could expose capacity_checkins
--    rows past RLS. It becomes security_invoker, so the caller's own RLS on
--    capacity_checkins applies. Existing consumers keep working: the view is
--    granted to xo_bot and authenticated, both have a SELECT policy on
--    capacity_checkins, and service_role bypasses RLS and keeps an explicit
--    SELECT grant. anon loses access, and write privileges on the view are
--    removed from every role.
--
-- 2. anon never writes: every write policy in public is service_role or
--    authenticated. Revoke INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES and
--    TRIGGER from anon on all public tables, and stop new tables inheriting
--    them. anon SELECT is deliberately NOT touched: eleven tables have an
--    explicit anon/public SELECT policy (alerts, alert_sources,
--    alert_silences, architecture_records, commander_decisions,
--    domain_heartbeats, domain_registry, emergency_alert_summary_state,
--    intelligence_source_health, lessons_learned, verification_state) and
--    whether they should stay anon-readable is a separate owner decision.

ALTER VIEW public.capacity_checkins_today SET (security_invoker = true);
-- The view is read-only aggregate output: no role needs write privileges on it.
-- Live ACL before this migration (2026-10-19): service_role and authenticated
-- held arwdDxtm, anon awdDxtm, xo_bot r. service_role BYPASSRLS does not bypass
-- object privileges, so SELECT is granted to it explicitly.
REVOKE ALL ON public.capacity_checkins_today FROM anon, authenticated, service_role, xo_bot, PUBLIC;
GRANT SELECT ON public.capacity_checkins_today TO xo_bot, authenticated, service_role;

DO $$
DECLARE
  t record;
BEGIN
  FOR t IN
    SELECT n.nspname, c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
  LOOP
    EXECUTE format(
      'REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON %I.%I FROM anon',
      t.nspname, t.relname);
  END LOOP;
END $$;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLES FROM anon;
