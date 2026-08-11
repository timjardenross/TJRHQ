-- 0006 — ORI GitHub Briefs Source: additive schema (USS-TJR-MSN-0074 / WP5)
-- USS Starship Endeavour NCC-170230
-- Builds on 0004_intelligence_platform.sql. ADDITIVE and non-breaking; safe to
-- run repeatedly. Adds github_markdown source_type, resilience_brief category,
-- ori_source_documents table, ORI columns on intelligence_events, seed row, views.
--
-- Reuses intelligence_events / intelligence_briefs / intelligence_source_registry.
-- Adds:
--   1. a new source_type value           'github_markdown'
--   2. a new source category value        'resilience_brief'
--   3. ori_source_documents               (preserve raw briefs — WP3/WP5)
--   4. nullable ORI columns on intelligence_events (WP4 extraction fields)
--   5. one seed source row                (the briefs repository)
--   6. retrieval/trend views              (WP6/WP8)

-- ─── 1+2. Extend enum-style CHECK constraints (additive) ─────────────────────
-- PostgreSQL CHECK constraints are dropped & re-created to widen the allowed set.

alter table intelligence_source_registry
  drop constraint if exists intelligence_source_registry_source_type_check;
alter table intelligence_source_registry
  add  constraint intelligence_source_registry_source_type_check
  check (source_type in ('rss','api','scrape','manual','github_markdown'));

alter table intelligence_source_registry
  drop constraint if exists intelligence_source_registry_category_check;
alter table intelligence_source_registry
  add  constraint intelligence_source_registry_category_check
  check (category in (
    'regulatory','emergency_management','critical_infrastructure',
    'cloud_technology','banking_payments','transport','media',
    'resilience_brief'
  ));

-- ─── 3. Source document preservation ─────────────────────────────────────────
create table if not exists ori_source_documents (
  document_id        uuid primary key default gen_random_uuid(),
  source_id          uuid not null references intelligence_source_registry(source_id),
  file_name          text not null,                 -- 2026-06-19-daily-operational-resilience-brief.md
  file_path          text not null,                 -- USSTJROS/2026-06-19-...md
  blob_url           text not null,                 -- canonical GitHub URL (explainability)
  brief_date         date not null,                 -- canonical date (filename-authoritative)
  content_sha        text not null,                 -- git blob/commit sha of this version
  format_version     text not null default '0',     -- detected: 0 | 1 | 1.0
  region             text not null default 'Australia',
  classification     text not null default 'public'
                       check (classification in ('public','internal','restricted')),
  raw_front_matter   jsonb,                          -- parsed YAML (or {} if none)
  raw_markdown       text not null,                  -- full original document, preserved
  parse_warnings     jsonb,                          -- e.g. ["date_mismatch","no_events"]
  superseded_by      uuid references ori_source_documents(document_id),
  ingested_at        timestamptz not null default now(),
  ingested_by        text not null default 'ORI-GitHub-Adapter',
  unique (file_path, content_sha)                    -- dedup Gate 1 (WP3 §2)
);

create index if not exists idx_osd_source_id  on ori_source_documents(source_id);
create index if not exists idx_osd_brief_date on ori_source_documents(brief_date desc);
create index if not exists idx_osd_sha        on ori_source_documents(content_sha);

comment on table ori_source_documents is
  'Raw Daily Operational Resilience Briefs preserved verbatim with full GitHub '
  'attribution (blob_url, content_sha). One row per file version. Extracted '
  'records live in intelligence_events and reference document_id.';

-- ─── 4. ORI extraction columns on the existing events table (all nullable) ───
alter table intelligence_events
  add column if not exists source_document_id uuid references ori_source_documents(document_id),
  add column if not exists source_ref         text,        -- file_path for traceability
  add column if not exists brief_date          date,        -- date of the originating brief
  add column if not exists organisation        text,        -- e.g. 'Vodafone', 'APRA'
  add column if not exists regulatory_topic    text,        -- CPS230 | SOCI_Act | CIRMP | ...
  add column if not exists resilience_themes   jsonb,       -- ["third_party_risk", ...]
  add column if not exists watch_item_status   text
                            check (watch_item_status in
                              ('active_incident','emerging','monitoring',
                               'regulatory_horizon','closed')),
  add column if not exists executive_relevance text
                            check (executive_relevance in ('high','medium','low'));

create index if not exists idx_ie_source_document on intelligence_events(source_document_id);
create index if not exists idx_ie_brief_date      on intelligence_events(brief_date desc);
create index if not exists idx_ie_reg_topic       on intelligence_events(regulatory_topic);
create index if not exists idx_ie_exec_rel        on intelligence_events(executive_relevance);
-- GIN index for theme containment queries (?| , @>)
create index if not exists idx_ie_themes_gin      on intelligence_events using gin (resilience_themes);

-- ─── 5. Seed the briefs repository as a single governed source ───────────────
insert into intelligence_source_registry
  (source_name, category, priority_rank, url, source_type, jurisdiction,
   confidence_weight, active, notes, added_by)
select
  'Daily Operational Resilience Briefs (GitHub)',
  'resilience_brief', 2,
  'https://github.com/timjardenross/daily-operational-resilience-briefs',
  'github_markdown', 'AU',
  0.75, true,
  'Curated daily OR digest. Supplement only — regulators stay priority 1. MSN-0074.',
  'USS-TJR-MSN-0074'
where not exists (
  select 1 from intelligence_source_registry
  where url = 'https://github.com/timjardenross/daily-operational-resilience-briefs'
);

-- ─── 6. Retrieval / trend views (WP6 / WP8) ──────────────────────────────────

-- Theme frequency over a rolling window (unnests jsonb theme arrays).
create or replace view ori_theme_frequency as
select
  theme,
  count(*)                              as mentions,
  count(distinct e.brief_date)          as days_seen,
  min(e.brief_date)                     as first_seen,
  max(e.brief_date)                     as last_seen
from intelligence_events e
cross join lateral jsonb_array_elements_text(coalesce(e.resilience_themes,'[]'::jsonb)) as theme
where e.source_document_id is not null
  and e.suppressed = false
group by theme;

-- Sector activity for digest-sourced events.
create or replace view ori_sector_activity as
select sector,
       count(*)                         as events,
       count(distinct brief_date)       as days_seen,
       max(brief_date)                  as last_seen
from intelligence_events
where source_document_id is not null and suppressed = false
group by sector;

-- Current watch items (active/emerging/regulatory horizon), highest relevance first.
create or replace view ori_watch_items as
select event_id, brief_date, raw_title, event_type, sector, organisation,
       regulatory_topic, resilience_themes, watch_item_status,
       executive_relevance, canonical_url, source_ref
from intelligence_events
where source_document_id is not null
  and suppressed = false
  and watch_item_status in ('active_incident','emerging','regulatory_horizon')
order by
  case executive_relevance when 'high' then 0 when 'medium' then 1 else 2 end,
  brief_date desc;

comment on view ori_theme_frequency is 'WP8 trend input — recurring resilience themes from the briefs digest.';
