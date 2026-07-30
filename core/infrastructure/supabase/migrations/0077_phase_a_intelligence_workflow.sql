-- ============================================================
-- Migration 0077 — Phase A: Intelligence Workflow Infrastructure
-- USS Starship Endeavour NCC-170230
--
-- Implements the schema layer of the Phase A Operational Resilience
-- Intelligence Workflow (Phase-A-Intelligence-Workflow-Design.md).
--
-- ARCHITECTURE DECISION (Captain-approved 2026-07-11):
--   The Phase A spec named fresh ori_signals / ori_briefs / mutation_audit_log
--   tables. Per CLAUDE.md standing constraints ("no duplicate workflows,
--   databases, or governance models; no parallel routing architecture; no new
--   tables except where explicitly required") this migration instead EXTENDS the
--   existing intelligence_* platform (migrations 0004/0006/0007):
--     * ori_signals            -> intelligence_events (extended below)
--     * ori_briefs             -> intelligence_briefs (extended below)
--     * ori_themes             -> intelligence_briefs.emerging_themes (jsonb, existing)
--     * mutation_audit_log     -> audit_events (migration 0054) via category='mutation'
--   Only the three genuinely-absent tables are created new:
--     watchlist_items, watchlist_tracking, brief_lessons_learned.
--
-- Additive & idempotent. Safe to run repeatedly.
-- ============================================================

-- ─── 1. Signal lifecycle + governance columns on intelligence_events ─────────
-- Maps Phase A "ori_signals" extension onto the canonical events table.
alter table intelligence_events
  -- Lifecycle state machine (Stages 2–13).
  add column if not exists signal_status text not null default 'TO_COLLECT'
    check (signal_status in (
      'TO_COLLECT','SCORED','VERIFYING','VERIFIED',
      'READY_FOR_BRIEF','IN_BRIEF','ARCHIVED','DUPLICATE'
    )),
  -- Role that currently owns the signal (Analyst, Intelligence Lead, ...).
  add column if not exists signal_owner text,
  -- Stage 3 source-tier (1=most authoritative … 4=discovery-only). Distinct from
  -- source_priority on the registry: this is the auto-classified tier per signal.
  add column if not exists source_tier int check (source_tier between 1 and 4),
  -- Stage 7 human-gate outputs.
  add column if not exists confidence_level text
    check (confidence_level in ('Confirmed','Probable','Emerging','Unverified')),
  add column if not exists verified_against jsonb,  -- {tier_1_source: URL, verified_date: ISO}
  -- Stage 8–9 scoring outputs (10-dimension model).
  add column if not exists relevance_score numeric(3,1),        -- 1.0–5.0
  add column if not exists score_breakdown jsonb,               -- {criticality:5, scale:4, ...}
  add column if not exists risk_rating text
    check (risk_rating in ('HIGH','MEDIUM','LOW')),
  add column if not exists score_override_reason text,          -- if manually adjusted
  -- Stage 12 Briefing Officer extraction.
  add column if not exists analysis_summary text,
  add column if not exists services_affected jsonb,             -- ["service1","service2"]
  add column if not exists customers_affected text,             -- scale description
  -- Stage 6 fuzzy near-duplicate clustering (complements exact dedup_hash).
  add column if not exists canonical_signal_id uuid references intelligence_events(event_id),
  add column if not exists cluster_similarity numeric(4,3);     -- 0.000–1.000 vs canonical

comment on column intelligence_events.signal_status is
  'Phase A signal lifecycle. TO_COLLECT->SCORED->VERIFYING->VERIFIED->READY_FOR_BRIEF'
  '->IN_BRIEF->ARCHIVED, or DUPLICATE. Human gates gate the VERIFYING/READY transitions.';
comment on column intelligence_events.source_tier is
  'Auto-classified source authority tier 1–4 (source_tier_classifier.py). '
  'Conservative: unknown domains default to 4.';
comment on column intelligence_events.canonical_signal_id is
  'Set on a near-duplicate signal, pointing at the retained canonical event. '
  'NULL for canonical/unclustered signals.';

create index if not exists idx_ievents_signal_status on intelligence_events(signal_status);
create index if not exists idx_ievents_source_tier    on intelligence_events(source_tier);
create index if not exists idx_ievents_canonical      on intelligence_events(canonical_signal_id);

-- ─── 2. Approval / QA-gate columns on intelligence_briefs ────────────────────
-- Maps Phase A "ori_briefs" governance extension onto the canonical briefs table.
alter table intelligence_briefs
  add column if not exists approval_status text not null default 'IN_REVIEW'
    check (approval_status in (
      'IN_REVIEW','DATA_QA_PASSED','FACTUAL_QA_PASSED',
      'ANALYTICAL_QA_PASSED','QA_READY','EXECUTIVE_APPROVED','PUBLISHED'
    )),
  -- Per-gate audit: {data_qa:{status,approved_by,timestamp}, factual_qa:{...}, ...}
  add column if not exists approval_audit jsonb not null default '{}',
  add column if not exists signal_ids jsonb,   -- selected event_ids (Stage 11 human gate)
  add column if not exists published_at timestamptz;

comment on column intelligence_briefs.approval_status is
  'Phase A 4-gate QA + executive approval state machine. mark_qa_ready requires '
  'data/factual/analytical gates passed; publish requires Executive Approver.';
comment on column intelligence_briefs.approval_audit is
  'Per-gate sign-off record. Append-only in practice; every transition also '
  'writes an audit_events row (category=''mutation'').';

create index if not exists idx_ibriefs_approval_status on intelligence_briefs(approval_status);

-- ─── 3. watchlist_items (new — Stage 14 human-curated forward watch) ─────────
create table if not exists watchlist_items (
  id           uuid        primary key default gen_random_uuid(),
  brief_id     uuid        not null references intelligence_briefs(brief_id) on delete cascade,
  item_text    text        not null,
  query        jsonb       not null default '{}',  -- {keyword, lookfor, timeframe}
  approved_by  text,                               -- Intelligence Lead (role/actor)
  approved_at  timestamptz,
  created_at   timestamptz not null default now()
);

comment on table watchlist_items is
  'Phase A Stage 14: Intelligence-Lead-curated forward-watch items on a brief. '
  'query drives next-cycle materialisation matching (watchlist_tracking).';

-- ─── 4. watchlist_tracking (new — post-brief materialisation detection) ──────
create table if not exists watchlist_tracking (
  id                 uuid        primary key default gen_random_uuid(),
  watchlist_item_id  uuid        not null references watchlist_items(id) on delete cascade,
  event_id           uuid        references intelligence_events(event_id),  -- NULL until matched
  materialized       boolean     not null default false,
  materialized_at    timestamptz,
  match_score        numeric(4,3),                -- optional match strength
  created_at         timestamptz not null default now()
);

comment on table watchlist_tracking is
  'Phase A post-brief automation: links a watchlist_item to the next-cycle signal '
  'that materialised its forward-watch prediction (or a not-yet-materialised marker).';

-- ─── 5. brief_lessons_learned (new — Intelligence-Lead reflection) ───────────
create table if not exists brief_lessons_learned (
  id           uuid        primary key default gen_random_uuid(),
  brief_id     uuid        not null references intelligence_briefs(brief_id) on delete cascade,
  lesson_text  text        not null,
  category     text        check (category in ('assumption','surprise','methodology_change','other')),
  recorded_by  text,                              -- Intelligence Lead (role/actor)
  created_at   timestamptz not null default now()
);

comment on table brief_lessons_learned is
  'Phase A learning loop: Intelligence-Lead lessons captured against a published '
  'brief (assumptions that held/broke, surprises, methodology changes).';

-- ─── 6. RLS + indexes (mirror audit_events/task_events pattern) ──────────────
alter table watchlist_items       enable row level security;
alter table watchlist_tracking    enable row level security;
alter table brief_lessons_learned enable row level security;

create index if not exists idx_watchlist_items_brief    on watchlist_items(brief_id);
create index if not exists idx_watchlist_track_item     on watchlist_tracking(watchlist_item_id);
create index if not exists idx_watchlist_track_event    on watchlist_tracking(event_id);
create index if not exists idx_watchlist_track_pending  on watchlist_tracking(materialized);
create index if not exists idx_lessons_brief            on brief_lessons_learned(brief_id);
