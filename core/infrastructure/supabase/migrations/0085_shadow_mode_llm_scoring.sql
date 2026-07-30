-- ============================================================
-- Migration 0085 — Shadow-Mode LLM Scoring + Cost Governance
-- USS Starship Endeavour NCC-170230
--
-- Implements the schema layer for:
--   * Issue 14: Dual-path heuristic/LLM scoring (shadow mode)
--   * Issue 20: Structured output + disclosure standard
--   * Issue 21: Cost/rate-limit governance for LLM calls
--
-- Adds columns to intelligence_events to track both scoring paths
-- independently, with full provenance and audit trail.
--
-- Additive & idempotent. Safe to run repeatedly.
-- ============================================================

-- ─── 1. Dual-path scoring columns on intelligence_events ──────────────────────
-- Keeps the existing heuristic columns (score_breakdown, relevance_score,
-- risk_rating) as-is (now explicitly the heuristic path), and adds
-- parallel LLM-path columns.
alter table intelligence_events
  -- LLM path results (parallel to heuristic columns)
  add column if not exists llm_score_breakdown jsonb,
  add column if not exists llm_relevance_score numeric(3,1),
  add column if not exists llm_risk_rating text
    check (llm_risk_rating is null or llm_risk_rating in ('HIGH','MEDIUM','LOW')),
  add column if not exists llm_provider text,  -- 'mistral' | 'gemini' | 'ollama' etc

  -- Disclosure: which scoring path was authoritative
  add column if not exists score_method text not null default 'heuristic'
    check (score_method in ('heuristic','llm','blended')),

  -- Full provenance metadata (JSON for extensibility)
  add column if not exists score_provenance jsonb not null default '{}'::jsonb;
    -- Structure: {
    --   heuristic_scored_at: ISO timestamp,
    --   llm_scored_at: ISO timestamp,
    --   llm_agree_with_heuristic: boolean,
    --   scoring_version: integer (for audit trail across prompt changes),
    --   notes: {LLM failures, timeouts, parsing issues}
    -- }

comment on column intelligence_events.llm_score_breakdown is
  'Shadow-mode LLM path result: 10-dimension breakdown (Issue 14).';
comment on column intelligence_events.llm_relevance_score is
  'Shadow-mode LLM path result: 1.0–5.0 overall relevance (Issue 14).';
comment on column intelligence_events.llm_risk_rating is
  'Shadow-mode LLM path result: HIGH/MEDIUM/LOW (Issue 14).';
comment on column intelligence_events.llm_provider is
  'Which LLM provider generated this path (Issue 20 disclosure).';
comment on column intelligence_events.score_method is
  'Disclosure: which method is authoritative (heuristic/llm/blended). '
  'Currently always ''heuristic'' during Issue 14 shadow mode (Issue 20).';
comment on column intelligence_events.score_provenance is
  'Complete scoring provenance: when each path ran, whether they agree, '
  'version history for audit trail (Issue 20).';

create index if not exists idx_ievents_score_method on intelligence_events(score_method);

-- ─── 2. LLM call metrics table (Issue 21: cost governance) ────────────────────
create table if not exists llm_call_metrics (
  id                 uuid primary key default gen_random_uuid(),
  call_at            timestamptz not null default now(),
  task_type          text not null,  -- 'signal-scoring' | 'brief-synthesis' | etc
  provider           text not null,
  model_name         text,
  input_tokens       int,
  output_tokens      int,
  estimated_cost_usd numeric(8,6),   -- For tracking spend
  latency_ms         int,
  success            boolean not null,
  failure_reason     text,
  event_id           uuid references intelligence_events(event_id),  -- nullable (some calls aren't event-tied)
  metadata           jsonb default '{}'::jsonb
);

comment on table llm_call_metrics is
  'Issue 21: Complete audit trail of every LLM call for cost governance. '
  'Used for monitoring, alerts, and cost tracking.';

create index if not exists idx_llm_metrics_call_at    on llm_call_metrics(call_at desc);
create index if not exists idx_llm_metrics_task_type  on llm_call_metrics(task_type);
create index if not exists idx_llm_metrics_provider   on llm_call_metrics(provider);
create index if not exists idx_llm_metrics_event_id   on llm_call_metrics(event_id);

-- ─── 3. Cost governance configuration table ───────────────────────────────────
create table if not exists llm_cost_governance (
  id                    uuid primary key default gen_random_uuid(),
  task_type             text not null unique,  -- per-task-type quotas
  daily_call_limit      int,
  daily_cost_limit_usd  numeric(10,2),
  throttle_on_exceed    text check (throttle_on_exceed in ('alert','fall_back_to_heuristic','stop_calls')),
  alert_at_percent      numeric(5,2) default 80,  -- alert when spending 80% of daily budget
  enabled               boolean not null default true,
  notes                 text,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);

comment on table llm_cost_governance is
  'Issue 21: Per-task-type cost governance thresholds and policies. '
  'Determines what happens when LLM call volume or spend exceeds limits.';

-- ─── 4. Daily cost tracking materialized view ──────────────────────────────────
-- Queries this to check if we've hit daily limits (refreshed hourly)
create materialized view if not exists llm_daily_costs as
select
  current_date::date as cost_date,
  task_type,
  count(*) as call_count,
  sum(estimated_cost_usd)::numeric(10,2) as total_cost_usd,
  sum(case when success then 1 else 0 end) as successful_calls,
  sum(case when success then 0 else 1 end) as failed_calls,
  max(call_at) as last_call_at
from llm_call_metrics
where call_at >= (current_date::timestamptz)
group by cost_date, task_type
order by task_type;

create index if not exists idx_llm_daily_costs_date_type
  on llm_daily_costs(cost_date, task_type);

comment on materialized view llm_daily_costs is
  'Issue 21: Daily LLM cost summary by task type. Refresh hourly to track spend. '
  'Used by cost_check.py to determine if we''ve exceeded thresholds.';
