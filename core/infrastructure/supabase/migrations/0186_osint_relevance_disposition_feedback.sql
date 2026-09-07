-- 0186_osint_relevance_disposition_feedback.sql
-- OSINT Ingestion Quality & Relevance Mission — Phases 3-9 conceptual signal
-- model (mission doc §23). Additive only: nullable columns, no backfill, no
-- rewrite of existing rows, no change to existing disposition semantics
-- (signal_status/suppressed on intelligence_events, auto_ingested/
-- auto_ingest_reviewed/suppressed on health_signals stay authoritative for
-- visibility until Phase 12 activation, per mission §33 shadow-mode
-- requirement). These columns are populated going forward by the new
-- relevance-gate/disposition-mapping code; existing rows stay NULL until an
-- explicit, bounded Phase 13 reprocessing pass (not run by this migration).
--
-- disposition/human_feedback_reason share one vocabulary across both tables
-- per mission §2 ("disposition enums" and "feedback reason structures" are
-- explicitly allowed as shared components) — domain models otherwise stay
-- fully separate; no FK or join is introduced between the two tables.

-- ── intelligence_events (Technical OSINT) ──────────────────────────────────

alter table intelligence_events
  add column if not exists mission_relevance text
    check (mission_relevance in ('RELEVANT', 'LOW_CONFIDENCE', 'NOT_RELEVANT')),
  add column if not exists relevance_reason text,
  add column if not exists novelty text
    check (novelty in ('NEW_DEVELOPMENT', 'UPDATE', 'DUPLICATE', 'COMMENTARY', 'BACKGROUND')),
  add column if not exists disposition text
    check (disposition in ('ESCALATE', 'BRIEF', 'WATCH', 'REFERENCE', 'SUPPRESS')),
  add column if not exists disposition_reason text,
  add column if not exists human_feedback_reason text
    check (human_feedback_reason in (
      'IRRELEVANT_TOPIC', 'WRONG_POPULATION', 'WRONG_GEOGRAPHY',
      'NO_OPERATIONAL_RELEVANCE', 'TOO_GENERIC', 'DUPLICATE', 'ALREADY_KNOWN',
      'COMMENTARY_ONLY', 'MARKETING_COMMERCIAL', 'WEAK_EVIDENCE',
      'LOW_INFORMATION_VALUE', 'OUT_OF_SCOPE', 'OTHER'
    )),
  add column if not exists human_feedback_note text,
  add column if not exists mission_config_version integer;

comment on column intelligence_events.mission_relevance is
  'OSINT mission Phase 4 relevance gate outcome. Distinct from confidence_level: an item can be RELEVANT + LOW confidence, or NOT_RELEVANT despite a credible source.';
comment on column intelligence_events.disposition is
  'Canonical cross-pipeline disposition (mission §17). Computed from existing signal_status/suppressed/rank_score — does not replace them. Shadow-mode only until Phase 12 activation: does not yet gate visibility.';
comment on column intelligence_events.human_feedback_reason is
  'Structured reason captured on human rejection/suppression (mission §19). Shared vocabulary with health_signals.human_feedback_reason; free text goes in human_feedback_note.';

create index if not exists idx_intelligence_events_disposition
  on intelligence_events (disposition) where disposition is not null;

create index if not exists idx_intelligence_events_mission_relevance
  on intelligence_events (mission_relevance) where mission_relevance is not null;

-- ── health_signals (Health OSINT) ───────────────────────────────────────────

alter table health_signals
  add column if not exists mission_relevance text
    check (mission_relevance in ('RELEVANT', 'LOW_CONFIDENCE', 'NOT_RELEVANT')),
  add column if not exists relevance_reason text,
  add column if not exists evidence_contribution text
    check (evidence_contribution in (
      'CONFIRMS', 'CHALLENGES', 'EXTENDS', 'REPLICATION',
      'SAFETY', 'BACKGROUND', 'UNRESOLVED'
    )),
  add column if not exists population_fit text,
  add column if not exists safety_relevance boolean not null default false,
  add column if not exists disposition text
    check (disposition in ('ESCALATE', 'BRIEF', 'WATCH', 'REFERENCE', 'SUPPRESS')),
  add column if not exists disposition_reason text,
  add column if not exists human_feedback_reason text
    check (human_feedback_reason in (
      'IRRELEVANT_TOPIC', 'WRONG_POPULATION', 'WRONG_GEOGRAPHY',
      'NO_OPERATIONAL_RELEVANCE', 'TOO_GENERIC', 'DUPLICATE', 'ALREADY_KNOWN',
      'COMMENTARY_ONLY', 'MARKETING_COMMERCIAL', 'WEAK_EVIDENCE',
      'LOW_INFORMATION_VALUE', 'OUT_OF_SCOPE', 'OTHER'
    )),
  add column if not exists human_feedback_note text,
  add column if not exists mission_config_version integer;

comment on column health_signals.evidence_contribution is
  'Mission Phase 7 classification, separate from confidence_level. A HIGH-confidence study can still be BACKGROUND; a MEDIUM-confidence study can be an important CHALLENGE.';
comment on column health_signals.safety_relevance is
  'True if this signal carries a plausible adverse-event/safety implication for an actively-monitored intervention/exposure (mission §28) — allows bypassing ordinary topic filtering regardless of mission_relevance/disposition.';
comment on column health_signals.disposition is
  'Canonical cross-pipeline disposition (mission §17), mapped from the existing PUBLISH/REJECT/ESCALATE curation outcome plus auto_ingested/auto_ingest_reviewed/suppressed. Does not replace the existing curation gate.';

create index if not exists idx_health_signals_disposition
  on health_signals (disposition) where disposition is not null;

create index if not exists idx_health_signals_evidence_contribution
  on health_signals (evidence_contribution) where evidence_contribution is not null;
