-- Briefs canonical uplift (BRIEFS_CANONICAL_UPLIFT.md).
--
-- Additive only — every column here is nullable with no backfill, so every
-- historical intelligence_briefs row remains exactly what it was (Section
-- 22: a brief represents what HQ assessed AT THAT TIME; older rows simply
-- have no morning_cycle_id/coverage/comparison/domain_picture/
-- known_unknowns, which the UI treats as "not available for this brief"
-- rather than fabricating a value for history).
--
-- morning_cycle_id: the local (AEST) calendar date this brief's morning
-- collection cycle belongs to (e.g. '2026-09-06') — see
-- intelligence/brief/morning_cycle.py. Lets the scheduler check "has today's
-- cycle already produced a brief?" without an ad hoc timestamp-range query,
-- and lets a future brief look up "the prior canonical brief for
-- comparison" unambiguously even if generation time drifts day to day.
--
-- coverage: structured collection-coverage/degraded-cutoff record — e.g.
--   {"expected": 34, "completed": 33, "failed": 1, "missing_sources": [...],
--    "degraded": true, "cutoff_reached": false,
--    "collection_status": "ok", "collection_checked_at": "...",
--    "latest_included_at": "..."}
-- Populated by BriefGenerator from the same sources_checked/available/
-- failed counts it already computed, plus the morning_cycle readiness
-- check — see Section 6/11/27/28 of the mission doc.
--
-- comparison: deterministic current-vs-prior-brief diff —
--   {"new": [...], "escalated": [...], "improved": [...],
--    "unchanged_but_material": [...], "no_longer_material": [...]}
-- Computed by intelligence/brief/comparison.py from stored top_events only
-- (title-similarity + risk_rating deltas) — never LLM-invented history
-- (Section 13/22).
--
-- domain_picture: deterministic grouping of this brief's top_events by
-- domain bucket (technical/regulatory/environmental/payments/other) — see
-- intelligence/brief/domain_picture.py. Evidence-grounded cross-domain
-- synthesis (Section 12) over the domains the OSINT collector actually
-- covers; does NOT include Health OSINT or Emergency Alert Hub content,
-- which are not yet fused into this brief's evidence base (documented as
-- FUTURE work in BRIEFS_CANONICAL_UPLIFT.md, not silently implied).
--
-- known_unknowns: LLM-identified evidence gaps/uncertainty about today's
-- top events (small additive key on the existing narrative prompt) — a
-- plain list of strings, empty when the LLM found nothing to flag.

alter table intelligence_briefs
  add column if not exists morning_cycle_id text,
  add column if not exists coverage         jsonb,
  add column if not exists comparison       jsonb,
  add column if not exists domain_picture   jsonb,
  add column if not exists known_unknowns   jsonb;

create index if not exists idx_intelligence_briefs_morning_cycle_id
  on intelligence_briefs(morning_cycle_id);

comment on column intelligence_briefs.morning_cycle_id is
  'AEST calendar date (YYYY-MM-DD) of the morning collection cycle this brief represents. Null for briefs generated before this uplift.';
comment on column intelligence_briefs.coverage is
  'Structured collection coverage / degraded-cutoff record for this brief''s morning cycle. Null for briefs generated before this uplift.';
comment on column intelligence_briefs.comparison is
  'Deterministic new/escalated/improved/unchanged/no-longer-material diff against the prior canonical brief. Null when there was no prior brief to compare against, or for briefs generated before this uplift.';
comment on column intelligence_briefs.domain_picture is
  'Deterministic grouping of this brief''s top_events by domain bucket. Null for briefs generated before this uplift.';
comment on column intelligence_briefs.known_unknowns is
  'LLM-identified evidence gaps/uncertainty about this brief''s top events. Null (not fabricated as empty) when narrative generation did not run.';

-- Rollback:
-- DROP INDEX IF EXISTS idx_intelligence_briefs_morning_cycle_id;
-- ALTER TABLE intelligence_briefs
--   DROP COLUMN IF EXISTS morning_cycle_id,
--   DROP COLUMN IF EXISTS coverage,
--   DROP COLUMN IF EXISTS comparison,
--   DROP COLUMN IF EXISTS domain_picture,
--   DROP COLUMN IF EXISTS known_unknowns;
