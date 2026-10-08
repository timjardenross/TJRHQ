-- 0228_intelligence_quality_dedup_processed.sql
-- HQ Status false positive (2026-10-08): Technical Intelligence read
-- "degraded — Discovery flowed (83 items today) but Deduplication shows
-- zero". Live check: all 83 rows were signal_status='SCORED', i.e. every
-- one went through phase_a_enrichment.enrich_and_save's dedup clustering
-- and simply came out canonical. `deduplicated` (0187) only counts
-- near-duplicate cluster MEMBERS (signal_status='DUPLICATE') — zero of
-- those is a normal outcome early in the UTC day, not a stall.
--
-- dedup_processed counts rows that actually went through the dedup stage
-- (anything past TO_COLLECT — canonical SCORED/onward, or DUPLICATE). A
-- row still TO_COLLECT means the scheduler's plain-save fallback ran
-- (enrichment threw) — that IS a real dedup stall, and it's what the
-- overview route's Deduplication stage now watches (live: 2026-10-05 had
-- 195 TO_COLLECT rows, 2026-10-06 had 80, and the old check never saw them).
--
-- Column appended at the end so CREATE OR REPLACE VIEW is legal; same
-- definer semantics and grants as 0187.

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
  count(*) filter (where human_feedback_reason is not null) as human_overrides,
  count(*) filter (where signal_status <> 'TO_COLLECT') as dedup_processed
from intelligence_events
group by 1
order by 1 desc;
