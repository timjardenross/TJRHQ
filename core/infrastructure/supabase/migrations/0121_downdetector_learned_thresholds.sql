-- 0121_downdetector_learned_thresholds.sql
--
-- 2026-08-10 (Captain-directed follow-up to downdetector_adapter.py's
-- two-layer push-alert gate, see
-- .claude/skills/bot-reviews/fixes-2026-08-09/cadence-tiering-and-learned-threshold.md):
-- replaces the flat `_REPORT_COUNT_FLOOR = 150` constant with a per-source,
-- LLM-learned threshold -- Captain's direction: "it needs to be learned on
-- the LLM ... as it's hard to set a floor per provider". Two tables:
--
-- downdetector_baseline_history -- the raw accumulation ledger. Every real
-- Downdetector fetch (not just push-alert-qualifying ones -- see
-- DowndetectorAdapter.collect()) logs its parsed status tier + report count
-- here, regardless of whether the two-layer gate passed. This is what
-- accumulates the real per-source history the nightly recompute job
-- reasons over; it starts accumulating faster for the 6 tiered-cadence
-- priority sources (NAB/ANZ/CBA/Westpac/Telstra/Optus) now that they're
-- checked during business hours, not just once/day.
--
-- downdetector_learned_thresholds -- one row per source, the CURRENT
-- threshold in force plus how it got there (threshold_source), upserted by
-- intelligence/ingestion/downdetector_thresholds.py::recompute_all() (see
-- intelligence/scheduler.py::_downdetector_threshold_recompute_job, nightly).
-- Explicit, logged bootstrap -> learned transition per point 3 of the
-- Captain's brief: a source with < _MIN_HISTORY_DAYS of real observations
-- gets a disclosed sector bootstrap default (threshold_source =
-- 'bootstrap_default_insufficient_history'), not a silently-applied number.
--
-- Applied live via Supabase MCP (mcp__plugin_supabase_supabase__apply_migration,
-- name "downdetector_learned_thresholds") -- this file is the repo-tracked
-- mirror, matching this directory's established migrations-as-source-of-truth
-- convention (see migration 0118's own header for the same note).
--
-- RLS mirrors wellness_reminder_log's pattern (migration 0118): service_role
-- (the scheduler daemon's SUPABASE_SERVICE_ROLE_KEY client, both
-- intelligence_store.py's _post/_get and the recompute job use it) gets
-- full access; authenticated gets read-only (future Workbench visibility
-- into learned thresholds / observation history -- no authenticated writer
-- exists for either table, unlike wellness_reminder_log which the XO bot's
-- own session also writes to).

create table if not exists downdetector_baseline_history (
  id             uuid primary key default gen_random_uuid(),
  source_name    text not null,
  sector         text not null check (sector in ('telecom', 'banking', 'government', 'other')),
  status         text not null check (status in ('no_problems', 'possible_problems', 'problems')),
  report_count   integer,
  observed_at    timestamptz not null default now(),
  created_at     timestamptz not null default now()
);

comment on table downdetector_baseline_history is
  'Every real Downdetector AU fetch (not just push-alert-qualifying ones) logs its parsed status tier + report count here -- the accumulation ledger intelligence/ingestion/downdetector_thresholds.py::recompute_all() reasons over to learn a per-source report-count threshold. report_count is nullable: the adapter''s prose-fallback parse path (page shape changed, aria-label pattern didn''t match) recovers status only, never fabricates a count. See migration 0121.';

create index if not exists downdetector_baseline_history_source_observed_idx
  on downdetector_baseline_history (source_name, observed_at desc);

alter table downdetector_baseline_history enable row level security;

create policy service_all
  on downdetector_baseline_history
  for all
  to service_role
  using (true)
  with check (true);

create policy auth_read
  on downdetector_baseline_history
  for select
  to authenticated
  using (true);


create table if not exists downdetector_learned_thresholds (
  id                  uuid primary key default gen_random_uuid(),
  source_name         text not null unique,
  sector              text not null check (sector in ('telecom', 'banking', 'government', 'other')),
  threshold_value     integer not null,
  threshold_source    text not null check (threshold_source in (
    'bootstrap_default_insufficient_history',
    'bootstrap_default_llm_unavailable',
    'bootstrap_default_after_llm_reject',
    'llm_learned'
  )),
  reasoning           text,
  history_days_used   integer,
  llm_provider        text,
  computed_at         timestamptz not null default now(),
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

comment on table downdetector_learned_thresholds is
  'Current per-source report-count floor for downdetector_adapter.py''s two-layer push-alert gate, replacing the flat _REPORT_COUNT_FLOOR=150 constant. One row per source, upserted nightly by recompute_all(). threshold_source records HOW the current value was reached (bootstrap default while history accumulates, LLM-learned once >= _MIN_HISTORY_DAYS of real observations exist, or a bootstrap fallback because the LLM was unavailable or its recommendation failed the sanity guard) -- always explicit, never a silent transition. See migration 0121.';

create unique index if not exists downdetector_learned_thresholds_source_idx
  on downdetector_learned_thresholds (source_name);

alter table downdetector_learned_thresholds enable row level security;

create policy service_all
  on downdetector_learned_thresholds
  for all
  to service_role
  using (true)
  with check (true);

create policy auth_read
  on downdetector_learned_thresholds
  for select
  to authenticated
  using (true);
