-- Migration 0239: restrict eleven public tables from anon-readable to authenticated-readable
--
-- Addresses the owner decision of 2026-10-19 ("Restrict values") after the
-- live check showed `SELECT true` policies for anon/public on these tables, so
-- anyone holding the public anon key could read them through the REST API.
-- Not run automatically; the owner decides when. Merge and deploy the portal
-- change that stops reading architecture_records / commander_decisions with the
-- anon client BEFORE running this.
--
-- Effect per table:
--   * the open read policy (anon, or public with USING true) is dropped;
--   * an authenticated-only read policy is created where one does not exist;
--   * SELECT is revoked from anon.
-- Unchanged: every *_service_write policy, the existing auth_read /
-- xo_bot_select / telegram_engineer_ro_select / service_role_full_access
-- policies, and the authenticated insert/update policies on alert_silences.
-- service_role bypasses RLS, so bots and portal routes that use the service
-- key keep working.

-- Open read policies named *_read (role public, USING true).
DROP POLICY IF EXISTS alert_silences_read ON public.alert_silences;
DROP POLICY IF EXISTS alert_sources_read ON public.alert_sources;
DROP POLICY IF EXISTS alerts_read ON public.alerts;
DROP POLICY IF EXISTS domain_heartbeats_read ON public.domain_heartbeats;
DROP POLICY IF EXISTS domain_registry_read ON public.domain_registry;
DROP POLICY IF EXISTS emergency_alert_summary_state_read ON public.emergency_alert_summary_state;
DROP POLICY IF EXISTS verification_state_read ON public.verification_state;

-- Open read policies named anon_read.
DROP POLICY IF EXISTS anon_read ON public.architecture_records;
DROP POLICY IF EXISTS anon_read ON public.commander_decisions;
DROP POLICY IF EXISTS anon_read ON public.lessons_learned;
DROP POLICY IF EXISTS anon_read ON public.intelligence_source_health;

-- Authenticated-only replacements for tables that had no authenticated read
-- policy of their own (architecture_records, commander_decisions and
-- lessons_learned already have auth_read).
CREATE POLICY alert_silences_authenticated_read ON public.alert_silences
  FOR SELECT TO authenticated USING (true);
CREATE POLICY alert_sources_authenticated_read ON public.alert_sources
  FOR SELECT TO authenticated USING (true);
CREATE POLICY alerts_authenticated_read ON public.alerts
  FOR SELECT TO authenticated USING (true);
CREATE POLICY domain_heartbeats_authenticated_read ON public.domain_heartbeats
  FOR SELECT TO authenticated USING (true);
CREATE POLICY domain_registry_authenticated_read ON public.domain_registry
  FOR SELECT TO authenticated USING (true);
CREATE POLICY emergency_alert_summary_state_authenticated_read ON public.emergency_alert_summary_state
  FOR SELECT TO authenticated USING (true);
CREATE POLICY verification_state_authenticated_read ON public.verification_state
  FOR SELECT TO authenticated USING (true);
CREATE POLICY intelligence_source_health_authenticated_read ON public.intelligence_source_health
  FOR SELECT TO authenticated USING (true);

REVOKE SELECT ON
  public.alert_silences,
  public.alert_sources,
  public.alerts,
  public.architecture_records,
  public.commander_decisions,
  public.domain_heartbeats,
  public.domain_registry,
  public.emergency_alert_summary_state,
  public.intelligence_source_health,
  public.lessons_learned,
  public.verification_state
FROM anon;
