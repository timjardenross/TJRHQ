-- ============================================================
-- Migration 0087 — RLS lockdown for shadow-mode / cost-governance tables
-- USS Starship Endeavour NCC-170230
--
-- 0085/0086 shipped llm_call_metrics, llm_cost_governance, and
-- intelligence_health_correlations without RLS — Supabase security
-- advisor flagged all 3 as public + RLS-disabled (anon/authenticated
-- read+write over PostgREST), plus llm_daily_costs (materialized view)
-- selectable via the Data API.
--
-- These are internal job/audit tables written only by the scheduler via
-- SUPABASE_SERVICE_ROLE_KEY (service_role bypasses RLS), with no end-user
-- read path. Matches the existing convention for authority_audit_log /
-- staff_autonomy_log: enable RLS, no policies — service_role only.
--
-- Additive & idempotent. Safe to run repeatedly.
-- ============================================================

alter table llm_call_metrics enable row level security;
alter table llm_cost_governance enable row level security;
alter table intelligence_health_correlations enable row level security;

-- Materialized views can't have RLS; lock down via grants instead.
revoke all on llm_daily_costs from anon, authenticated;
grant select on llm_daily_costs to service_role;
