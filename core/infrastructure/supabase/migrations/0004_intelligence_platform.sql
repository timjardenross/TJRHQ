-- WP-ORI-1: Operational Resilience Intelligence Platform schema
-- USS Starship Endeavour NCC-170230
-- Adds four tables to support the OR Intelligence Agent capability.
-- Safe to run repeatedly (all CREATE TABLE use IF NOT EXISTS).

-- ─── Source Registry ─────────────────────────────────────────────────────────

create table if not exists intelligence_source_registry (
  source_id         uuid primary key default gen_random_uuid(),
  source_name       text not null,
  category          text not null check (category in (
                      'regulatory',
                      'emergency_management',
                      'critical_infrastructure',
                      'cloud_technology',
                      'banking_payments',
                      'transport',
                      'media'
                    )),
  priority_rank     int  not null check (priority_rank between 1 and 5),
  url               text not null,
  rss_url           text,
  api_endpoint      text,
  source_type       text not null check (source_type in ('rss','api','scrape','manual')),
  jurisdiction      text not null check (jurisdiction in ('AU','APAC','GLOBAL')),
  confidence_weight numeric(3,2) not null default 0.80 check (confidence_weight between 0 and 1),
  active            boolean not null default true,
  notes             text,
  added_by          text not null default 'WP-ORI-2',
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

create index if not exists idx_isr_category      on intelligence_source_registry(category);
create index if not exists idx_isr_priority      on intelligence_source_registry(priority_rank);
create index if not exists idx_isr_active        on intelligence_source_registry(active);

comment on table intelligence_source_registry is
  'Governed registry of all intelligence sources monitored by the OR Intelligence Agent. '
  'Treat as a platform capability — extend via seed scripts, not ad-hoc inserts.';

-- ─── Source Health ────────────────────────────────────────────────────────────

create table if not exists intelligence_source_health (
  health_id         uuid primary key default gen_random_uuid(),
  source_id         uuid not null references intelligence_source_registry(source_id) on delete cascade,
  checked_at        timestamptz not null default now(),
  status            text not null check (status in ('ok','stale','failed','degraded','skipped')),
  items_retrieved   int  not null default 0,
  latency_ms        int,
  error_message     text,
  http_status       int
);

create index if not exists idx_ish_source_id  on intelligence_source_health(source_id);
create index if not exists idx_ish_checked_at on intelligence_source_health(checked_at desc);

comment on table intelligence_source_health is
  'Rolling health log for each source. One row per collection attempt. '
  'Latest row per source_id gives current health. Never silently dropped.';

-- ─── Intelligence Events ──────────────────────────────────────────────────────

create table if not exists intelligence_events (
  event_id                   uuid primary key default gen_random_uuid(),
  source_id                  uuid not null references intelligence_source_registry(source_id),
  raw_title                  text not null,
  raw_summary                text,
  canonical_url              text,
  published_at               timestamptz,
  collected_at               timestamptz not null default now(),

  -- Classification (all rule-based, no LLM required)
  event_type                 text check (event_type in (
                               'regulatory','cyber','technology_outage','telecom_outage',
                               'payments_disruption','energy_disruption','severe_weather',
                               'transport_disruption','physical_security','third_party_disruption',
                               'geopolitical','supply_chain','workforce','other'
                             )),
  geography                  text check (geography in ('AU','APAC','GLOBAL')),
  sector                     text,

  -- Scoring (0.00–1.00 or boolean flags)
  operational_relevance      numeric(3,2) default 0.00,
  customer_impact            text check (customer_impact in ('low','medium','high')),
  banking_relevance          text check (banking_relevance in ('low','medium','high')),
  cps230_relevance           boolean not null default false,
  dependency_risk            boolean not null default false,
  confidence                 numeric(3,2) not null default 0.50,
  rank_score                 numeric(8,4)  default 0.0000,

  -- Dedup
  dedup_hash                 text unique,   -- SHA-256 of normalised title+source_id+date

  -- Brief linkage
  brief_id                   uuid,          -- FK set once included in intelligence_briefs
  suppressed                 boolean not null default false,
  suppression_reason         text
);

create index if not exists idx_ie_source_id    on intelligence_events(source_id);
create index if not exists idx_ie_collected_at on intelligence_events(collected_at desc);
create index if not exists idx_ie_event_type   on intelligence_events(event_type);
create index if not exists idx_ie_rank_score   on intelligence_events(rank_score desc);
create index if not exists idx_ie_brief_id     on intelligence_events(brief_id);
create index if not exists idx_ie_suppressed   on intelligence_events(suppressed);
create index if not exists idx_ie_dedup        on intelligence_events(dedup_hash);

comment on table intelligence_events is
  'Every intelligence item collected. Classified, ranked, and either included in a brief '
  'or stored for archive querying. dedup_hash prevents double-counting cross-source.';

-- ─── Intelligence Briefs ──────────────────────────────────────────────────────

create table if not exists intelligence_briefs (
  brief_id             uuid primary key default gen_random_uuid(),
  generated_at         timestamptz not null default now(),
  period_start         date not null,
  period_end           date not null,

  -- Collection metadata
  sources_checked      int not null default 0,
  sources_available    int not null default 0,
  sources_failed       int not null default 0,
  sources_stale        int not null default 0,
  events_evaluated     int not null default 0,
  events_included      int not null default 0,
  events_suppressed    int not null default 0,

  -- Brief sections (LLM-generated; may be null if all providers failed)
  executive_snapshot   text,
  emerging_themes      jsonb,
  forward_watch        jsonb,
  cps230_implications  jsonb,
  bottom_line          text,

  -- Structured event list (top 5, stored as snapshot)
  top_events           jsonb,

  -- Quality indicators
  overall_risk         text check (overall_risk in ('GREEN','AMBER','RED','UNKNOWN')),
  llm_used             boolean not null default false,
  provider_used        text,
  confidence           numeric(3,2),
  narrative_available  boolean not null default false,

  -- Provenance
  created_by           text not null default 'OR-Intelligence-Agent',
  trigger_type         text check (trigger_type in ('scheduled','on_demand','test'))
);

create index if not exists idx_ib_generated_at on intelligence_briefs(generated_at desc);
create index if not exists idx_ib_period       on intelligence_briefs(period_start, period_end);

-- FK from events back to briefs (deferred to avoid circular dep at table creation)
do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'fk_ie_brief_id'
  ) then
    alter table intelligence_events
      add constraint fk_ie_brief_id
      foreign key (brief_id) references intelligence_briefs(brief_id)
      on delete set null;
  end if;
end
$$;

comment on table intelligence_briefs is
  'One row per generated OR Intelligence Brief. Narrative sections are LLM-generated '
  'but events, scoring, and metadata are always present even when LLM is unavailable.';
