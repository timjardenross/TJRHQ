-- 0187_osint_ingestion_quality_observability.sql
-- OSINT Ingestion Quality & Relevance Mission, Phase 26 (observability).
-- Two read-only views, one per pipeline, answering the mission's own
-- funnel questions (discovered / suppressed-by-relevance / deduplicated /
-- watch / brief / escalate) from the columns Phase 3-8 added. Views only
-- — no new writes, no change to any existing table's semantics. Intended
-- for debugging/quality tracking (mission §26: "do not necessarily make
-- all of these numbers prominent in the user-facing workbench"), not a
-- new workbench page.

create or replace view intelligence_ingestion_quality_daily as
select
  date_trunc('day', collected_at) as day,
  count(*) as discovered,
  count(*) filter (where suppressed) as suppressed,
  count(*) filter (where signal_status = 'DUPLICATE') as deduplicated,
  count(*) filter (where mission_relevance = 'NOT_RELEVANT') as not_relevant,
  count(*) filter (where mission_relevance = 'LOW_CONFIDENCE') as low_confidence,
  count(*) filter (where mission_relevance = 'RELEVANT') as relevant,
  count(*) filter (where disposition = 'ESCALATE') as escalate,
  count(*) filter (where disposition = 'BRIEF') as brief,
  count(*) filter (where disposition = 'WATCH') as watch,
  count(*) filter (where disposition = 'REFERENCE') as reference,
  count(*) filter (where disposition = 'SUPPRESS') as suppress,
  count(*) filter (where human_feedback_reason is not null) as human_overrides
from intelligence_events
group by 1
order by 1 desc;

comment on view intelligence_ingestion_quality_daily is
  'OSINT mission Phase 26 observability. mission_relevance/disposition are populated only for rows scored after the 2026-09-05 Phase 4/6/8 rollout — older rows show NULL in those columns, not zero, until an explicit Phase 13 reprocessing pass (not yet run).';

create or replace view health_ingestion_quality_daily as
select
  date_trunc('day', collected_at) as day,
  count(*) as discovered,
  count(*) filter (where suppressed) as suppressed,
  count(*) filter (where auto_ingested and not auto_ingest_reviewed) as pending_curation,
  count(*) filter (where mission_relevance = 'NOT_RELEVANT') as not_relevant,
  count(*) filter (where mission_relevance = 'LOW_CONFIDENCE') as low_confidence,
  count(*) filter (where mission_relevance = 'RELEVANT') as relevant,
  count(*) filter (where evidence_contribution is not null) as evidence_contribution_scored,
  count(*) filter (where safety_relevance) as safety_flagged,
  count(*) filter (where disposition = 'ESCALATE') as escalate,
  count(*) filter (where disposition = 'BRIEF') as brief,
  count(*) filter (where disposition = 'WATCH') as watch,
  count(*) filter (where disposition = 'REFERENCE') as reference,
  count(*) filter (where disposition = 'SUPPRESS') as suppress,
  count(*) filter (where human_feedback_reason is not null) as human_overrides
from health_signals
group by 1
order by 1 desc;

comment on view health_ingestion_quality_daily is
  'OSINT mission Phase 26 observability. mission_relevance/evidence_contribution/disposition populated only for signals curated after the 2026-09-05 Phase 4/7/9 rollout.';
