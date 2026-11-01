-- 2026-09-15 adversarial review (Fix Next #14): a drift-detection RPC so
-- tools/check_advisory_sessions_rls.py can verify the live pg_policies
-- catalog directly instead of trusting migration-file history, which is
-- known to drift from reality here -- 0034_advisory_sessions.sql's
-- original text still reads USING(true)/WITH CHECK(true) even though
-- 0100_advisory_sessions_rls_drift_reconcile.sql already tightened it in
-- production; a future migration replay gap (or another table getting
-- the same "no auth yet" placeholder pattern) could silently reopen a
-- table to anon with nothing to catch it.
--
-- pg_policies is a system catalog, not exposed via PostgREST directly,
-- so this SECURITY DEFINER function exposes only the narrow fact the
-- check needs (does `anon` have any policy on this table, and what do
-- they look like) -- not general catalog access.
CREATE OR REPLACE FUNCTION public.check_anon_grants(p_table_name text)
RETURNS TABLE (
  policy_name text,
  command     text,
  roles       text[],
  using_expr  text,
  check_expr  text
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT
    polname::text,
    CASE pol.polcmd
      WHEN 'r' THEN 'SELECT' WHEN 'a' THEN 'INSERT' WHEN 'w' THEN 'UPDATE'
      WHEN 'd' THEN 'DELETE' WHEN '*' THEN 'ALL' ELSE pol.polcmd::text
    END,
    ARRAY(SELECT rolname::text FROM pg_roles WHERE oid = ANY(pol.polroles)),
    pg_get_expr(pol.polqual, pol.polrelid),
    pg_get_expr(pol.polwithcheck, pol.polrelid)
  FROM pg_policy pol
  JOIN pg_class cls ON cls.oid = pol.polrelid
  WHERE cls.relname = p_table_name
    AND (
      pol.polroles = '{0}'  -- empty polroles means "PUBLIC" (all roles, anon included)
      OR EXISTS (
        SELECT 1 FROM pg_roles r
        WHERE r.oid = ANY(pol.polroles) AND r.rolname = 'anon'
      )
    );
$$;

-- Only the service_role (used by tools/check_advisory_sessions_rls.py and
-- similar CI checks) may call this -- it is a security-audit primitive,
-- not a general-purpose catalog query, so it must not itself be callable
-- by anon/authenticated.
--
-- 2026-09-15 correction: `REVOKE ALL ... FROM PUBLIC` alone was NOT
-- sufficient -- verified live that the anon key could still call this via
-- POST /rest/v1/rpc/check_anon_grants and get a 200 (empty result for a
-- clean table, but it would have returned real policy text -- USING/CHECK
-- expressions -- for a table that actually had one). Revoking from PUBLIC,
-- anon, and authenticated explicitly closes it; verified live afterwards
-- that the anon key now gets 42501 permission denied and service_role
-- calls still succeed.
REVOKE ALL ON FUNCTION public.check_anon_grants(text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.check_anon_grants(text) TO service_role;
