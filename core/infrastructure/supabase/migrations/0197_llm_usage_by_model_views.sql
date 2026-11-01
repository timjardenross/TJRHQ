-- 0197_llm_usage_by_model_views.sql
-- HQ Status ("agent-status-workbench") Usage tab.
--
-- Every LLM call already lands in llm_call_metrics (0085, Issue 21 cost
-- governance) with provider/model_name/tokens/cost/latency/success. This
-- migration adds two read-only views shaping that audit trail for display —
-- no new logging or scoring logic; call sites already write via
-- intelligence/governance/llm_cost_governance.py's log_call().
--
-- llm_call_metrics has RLS enabled with no policies (0087) — service_role
-- (the scheduler) writes, no end-user read path existed. These views are
-- created with definer (owner) semantics, same convention as
-- intelligence_ingestion_quality_daily (0187): the view owner reads the
-- locked-down table, and default grants expose the aggregated view to
-- authenticated (this is a single-tenant app — any authenticated session
-- is the Captain, per supabase-server.ts).
--
-- Whatever provider/model strings get logged show up here automatically.
-- Today that's Gemini/Mistral/Ollama/Qwen/Kimi/GLM (see
-- core/llm/provider_chain.py) — if Claude or OpenAI calls are ever routed
-- through log_call(), they appear with no view changes.

create or replace view llm_usage_by_model_30d as
select
  provider,
  model_name,
  count(*) as call_count,
  sum(case when success then 1 else 0 end) as successful_calls,
  sum(case when success then 0 else 1 end) as failed_calls,
  sum(coalesce(input_tokens, 0)) as total_input_tokens,
  sum(coalesce(output_tokens, 0)) as total_output_tokens,
  sum(coalesce(estimated_cost_usd, 0))::numeric(10,4) as total_cost_usd,
  avg(latency_ms)::int as avg_latency_ms,
  max(call_at) as last_call_at
from llm_call_metrics
where call_at >= now() - interval '30 days'
group by provider, model_name
order by total_cost_usd desc nulls last, call_count desc;

comment on view llm_usage_by_model_30d is
  'HQ Status Usage tab: per-provider/model call volume, tokens, cost, and '
  'success rate over the trailing 30 days. Reads llm_call_metrics (0085) '
  'directly — no new scoring logic.';

create or replace view llm_usage_daily_totals_14d as
select
  date_trunc('day', call_at)::date as day,
  count(*) as call_count,
  sum(case when success then 1 else 0 end) as successful_calls,
  sum(case when success then 0 else 1 end) as failed_calls,
  sum(coalesce(estimated_cost_usd, 0))::numeric(10,4) as total_cost_usd
from llm_call_metrics
where call_at >= now() - interval '14 days'
group by day
order by day desc;

comment on view llm_usage_daily_totals_14d is
  'HQ Status Usage tab: daily LLM call volume and spend across every '
  'provider/model, trailing 14 days. Reads llm_call_metrics (0085) directly.';
