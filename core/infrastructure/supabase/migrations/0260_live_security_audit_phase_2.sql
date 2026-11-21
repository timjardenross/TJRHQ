-- 0260_live_security_audit_phase_2.sql
--
-- Low-risk performance remediation from the 2026-11-21 live Supabase audit.
-- This migration preserves access semantics while removing redundant policy
-- evaluation, caching auth.uid() once per statement, and covering foreign keys.

-- Keep the UNIQUE constraint-backed index, which is the more heavily used copy.
drop index if exists public.downdetector_learned_thresholds_source_idx;

-- Cover every currently unindexed foreign key. These relations are small enough
-- for ordinary transactional index creation in the migration window.
create index if not exists idx_revs_crisis_events_user_id_fk
  on archive.revs_crisis_events (user_id);
create index if not exists idx_revs_pem_screen_log_user_id_fk
  on archive.revs_pem_screen_log (user_id);
create index if not exists idx_batch_jobs_mission_id_fk
  on public.batch_jobs (mission_id);
create index if not exists idx_capacity_intervention_events_checkin_id_fk
  on public.capacity_intervention_events (checkin_id);
create index if not exists idx_captured_items_duplicate_of_fk
  on public.captured_items (duplicate_of);
create index if not exists idx_content_signals_event_id_fk
  on public.content_signals (event_id);
create index if not exists idx_health_adverse_events_source_id_fk
  on public.health_adverse_events (source_id);
create index if not exists idx_health_events_linked_log_id_fk
  on public.health_events (linked_log_id);
create index if not exists idx_health_signal_corroboration_corroborating_signal_id_fk
  on public.health_signal_corroboration (corroborating_signal_id);
create index if not exists idx_health_signal_validation_signal_id_fk
  on public.health_signal_validation (signal_id);
create index if not exists idx_health_source_fetch_config_source_id_fk
  on public.health_source_fetch_config (source_id);
create index if not exists idx_missions_rework_of_fk
  on public.missions (rework_of);
create index if not exists idx_ori_source_documents_superseded_by_fk
  on public.ori_source_documents (superseded_by);
create index if not exists idx_pain_recovery_events_user_id_fk
  on public.pain_recovery_events (user_id);
create index if not exists idx_pain_recovery_model_interactions_session_id_fk
  on public.pain_recovery_model_interactions (session_id);
create index if not exists idx_physical_workout_sessions_readiness_checkin_id_fk
  on public.physical_workout_sessions (readiness_checkin_id);
create index if not exists idx_processing_documents_memory_document_id_fk
  on public.processing_documents (memory_document_id);
create index if not exists idx_retrieval_logs_specialist_id_fk
  on public.retrieval_logs (specialist_id);

-- auth.uid() in a scalar subquery becomes an initplan and is evaluated once per
-- statement. The ownership predicates and target role remain unchanged.
alter policy own_select on public.shopping_list_saved_views
  using (owner_id = (select auth.uid()));
alter policy own_insert on public.shopping_list_saved_views
  with check (owner_id = (select auth.uid()));
alter policy own_update on public.shopping_list_saved_views
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));
alter policy own_delete on public.shopping_list_saved_views
  using (owner_id = (select auth.uid()));

alter policy pain_recovery_sessions_owner on public.pain_recovery_sessions
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));
alter policy pain_recovery_events_owner on public.pain_recovery_events
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));
alter policy pain_recovery_reviews_owner on public.pain_recovery_reviews
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));
alter policy pain_recovery_model_interactions_owner on public.pain_recovery_model_interactions
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));
alter policy pain_recovery_recipe_owner on public.pain_recovery_recipe_ingredients
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

alter policy "Authenticated users can manage activity_logs" on public.activity_logs
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
alter policy "Authenticated users can manage weight_logs" on public.weight_logs
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
alter policy auth_write on public.health_daily_logs
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
alter policy auth_read on public.health_insights
  using ((select auth.uid()) = user_id);

-- These policies are exact semantic duplicates. Keep the table-specific owner
-- policy and remove the later generic copy.
drop policy if exists pain_recovery_owner_all on public.pain_recovery_sessions;
drop policy if exists pain_recovery_owner_all on public.pain_recovery_events;
drop policy if exists pain_recovery_owner_all on public.pain_recovery_reviews;
drop policy if exists pain_recovery_owner_all on public.pain_recovery_model_interactions;
drop policy if exists pain_recovery_owner_all on public.pain_recovery_recipe_ingredients;

-- FOR ALL already supplies SELECT access with the same TRUE predicate.
drop policy if exists auth_read on public.captains_log_entries;
drop policy if exists decide_ledger_auth_read on public.decide_ledger;
drop policy if exists auth_read on public.health_daily_logs;
drop policy if exists home_sessions_auth_read on public.home_sessions;
