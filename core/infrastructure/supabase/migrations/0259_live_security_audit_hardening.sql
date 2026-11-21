-- 0259_live_security_audit_hardening.sql
--
-- Safe first-pass remediation for the 2026-11-21 live Supabase audit.
-- Preserve existing application access while tightening function resolution,
-- replacing deprecated auth.role() policy routing with explicit target roles,
-- and removing anon grants from tables that intentionally have no policies.

-- ---------------------------------------------------------------------------
-- Functions: pin search_path and make EXECUTE grants explicit.
-- ---------------------------------------------------------------------------

alter function public.match_research_memories_mistral(public.vector, double precision, integer)
  set search_path = pg_catalog, public;

revoke all on function public.match_research_memories_mistral(public.vector, double precision, integer)
  from public, anon, authenticated, xo_bot;
grant execute on function public.match_research_memories_mistral(public.vector, double precision, integer)
  to authenticated, xo_bot, service_role;

alter function public.count_uncorroborated_events(timestamptz)
  set search_path = pg_catalog, public;

revoke all on function public.count_uncorroborated_events(timestamptz)
  from public, anon, authenticated, xo_bot;
grant execute on function public.count_uncorroborated_events(timestamptz)
  to authenticated, service_role;

alter function public.bulk_update_signal_scores(jsonb)
  set search_path = pg_catalog, public;

revoke all on function public.bulk_update_signal_scores(jsonb)
  from public, anon, authenticated, xo_bot;
grant execute on function public.bulk_update_signal_scores(jsonb)
  to service_role;

-- SECURITY DEFINER remains intentional: this function reads the caller's own
-- clearance from a table that callers cannot access directly. Keep the function
-- callable only by signed-in users and use a pinned search path.
alter function public.current_officer_clearance()
  set search_path = pg_catalog, public;

revoke all on function public.current_officer_clearance()
  from public, anon, authenticated, xo_bot;
grant execute on function public.current_officer_clearance()
  to authenticated;

comment on function public.current_officer_clearance() is
  'Returns the calling authenticated identity''s clearance. SECURITY DEFINER is intentional so RLS predicates can read officer_clearances; EXECUTE is limited to authenticated and search_path is pinned.';

-- ---------------------------------------------------------------------------
-- Policies: target roles explicitly instead of routing through auth.role().
-- These ALTERs preserve the effective predicates and access levels.
-- ---------------------------------------------------------------------------

alter policy alert_silences_service_write on public.alert_silences
  to service_role using (true) with check (true);
alter policy alert_sites_service_write on public.alert_sites
  to service_role using (true) with check (true);
alter policy alert_sources_service_write on public.alert_sources
  to service_role using (true) with check (true);
alter policy alerts_service_write on public.alerts
  to service_role using (true) with check (true);
alter policy conversation_turns_service_write on public.conversation_turns
  to service_role using (true) with check (true);
alter policy domain_heartbeats_service_write on public.domain_heartbeats
  to service_role using (true) with check (true);
alter policy domain_registry_service_write on public.domain_registry
  to service_role using (true) with check (true);
alter policy emergency_alert_feed_state_service_write on public.emergency_alert_feed_state
  to service_role using (true) with check (true);
alter policy emergency_alert_source_integrity_service_write on public.emergency_alert_source_integrity
  to service_role using (true) with check (true);
alter policy emergency_alert_summary_state_service_write on public.emergency_alert_summary_state
  to service_role using (true) with check (true);
alter policy verification_state_service_write on public.verification_state
  to service_role using (true) with check (true);

alter policy "authenticated can read health_adverse_events" on public.health_adverse_events
  to authenticated using (true);
alter policy "authenticated can read health_signal_corroboration" on public.health_signal_corroboration
  to authenticated using (true);
alter policy "authenticated can read health_signal_validation" on public.health_signal_validation
  to authenticated using (true);
alter policy "authenticated can read health_signals" on public.health_signals
  to authenticated using (true);
alter policy "authenticated can read health_source_fetch_config" on public.health_source_fetch_config
  to authenticated using (true);
alter policy "authenticated can read health_source_registry" on public.health_source_registry
  to authenticated using (true);
alter policy "authenticated can read event validations" on public.intelligence_event_validation
  to authenticated using (true);
alter policy "authenticated can read signal_corroboration" on public.signal_corroboration
  to authenticated using (true);
alter policy "authenticated can read signal_escalation_history" on public.signal_escalation_history
  to authenticated using (true);
alter policy "authenticated can read source_reliability_snapshot" on public.source_reliability_snapshot
  to authenticated using (true);
alter policy "authenticated can read validation_job_runs" on public.validation_job_runs
  to authenticated using (true);

alter policy "owner reads own pain recovery consent" on public.pain_recovery_consents
  to authenticated using ((select auth.uid()) = user_id);
alter policy "owner updates own pain recovery consent" on public.pain_recovery_consents
  to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
alter policy "owner writes own pain recovery consent" on public.pain_recovery_consents
  to authenticated with check ((select auth.uid()) = user_id);

-- ---------------------------------------------------------------------------
-- RLS-without-policy tables are intentionally private through the Data API.
-- Remove inherited anon privileges so this deny-by-default intent is explicit.
-- ---------------------------------------------------------------------------

revoke all on table
  public.alerts_tz_backfill_backup_20261106,
  public.authority_audit_log,
  public.brief_lessons_learned,
  public.capabilities,
  public.capacity_calibration,
  public.capacity_calibration_summary,
  public.commander_mission_candidates,
  public.daily_health_snapshot,
  public.escalation_events,
  public.escalation_history,
  public.external_fetch_usage,
  public.google_calendar_tokens,
  public.human_systems_feedback,
  public.human_systems_friction,
  public.human_systems_patterns,
  public.intelligence_health_correlations,
  public.knowledge_edges,
  public.knowledge_nodes,
  public.llm_cost_governance,
  public.operational_patterns,
  public.ori_source_documents,
  public.pgqueuer,
  public.pgqueuer_log,
  public.pgqueuer_schedules,
  public.pgqueuer_statistics,
  public.research_metrics,
  public.retrieval_logs,
  public.specialist_permissions,
  public.specialists,
  public.staff_autonomy_log,
  public.system_heartbeat,
  public.task_events,
  public.tasks,
  public.user_settings,
  public.watchlist_items,
  public.watchlist_tracking,
  public.working_memory
from anon;
