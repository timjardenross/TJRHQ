-- ============================================================
-- Migration 0089 — Drop llm_call_metrics.event_id FK constraint
-- USS Starship Endeavour NCC-170230
--
-- Issue 14/16: score_dual_path()/augment_if_ambiguous() log the LLM call
-- (llm_cost_governance.log_call) BEFORE phase_a_enrichment.enrich_and_save()
-- persists the event row (scoring happens first so the score fields can be
-- included in the same save_event(..., phase_a=) call). With a hard FK to
-- intelligence_events(event_id), every single log_call() during shadow
-- mode / selective augmentation hits a 409 FK-violation, since the
-- referenced event doesn't exist yet at log time — silently defeating
-- Issue 21 cost tracking for every call (log_call() catches and warns,
-- never raises, so this was invisible until run live).
--
-- llm_call_metrics is an audit trail, not a strict relational join —
-- drop the FK, keep the column as a plain nullable uuid for correlation
-- when the referenced event does exist.
--
-- Additive & idempotent. Safe to run repeatedly.
-- ============================================================

alter table llm_call_metrics drop constraint if exists llm_call_metrics_event_id_fkey;

comment on column llm_call_metrics.event_id is
  'Best-effort correlation to intelligence_events.event_id. No FK — logged '
  'before the event is persisted (scoring runs before save_event), so the '
  'referenced row may not exist yet or (for non-event-tied calls) at all.';
