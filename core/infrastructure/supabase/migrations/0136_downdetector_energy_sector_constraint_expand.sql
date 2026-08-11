-- 0136_downdetector_energy_sector_constraint_expand.sql
--
-- 2026-08-10 (Downdetector coverage expansion round 2, see
-- .claude/skills/bot-reviews/fixes-2026-08-09/downdetector-coverage-expansion-round2.md):
-- adds Origin Energy, AGL, and EnergyAustralia to Downdetector AU coverage
-- (source_type='downdetector', category='critical_infrastructure' -- same
-- pattern as the original 19 telecom/banking/government sources).
--
-- Both threshold-learning tables from migration 0121
-- (downdetector_baseline_history, downdetector_learned_thresholds) have a
-- CHECK constraint on `sector` limited to
-- ('telecom','banking','government','other'). Widened here to add
-- 'energy' -- additive, non-breaking, same safe pattern already used
-- repeatedly tonight for other CHECK-constraint widenings on this schema
-- (source_type, jurisdiction, category on intelligence_source_registry).
-- No existing rows/values affected.
--
-- Applied live via Supabase MCP (mcp__plugin_supabase_supabase__apply_migration,
-- name "downdetector_energy_sector_constraint_expand") -- this file is the
-- repo-tracked mirror, matching this directory's established
-- migrations-as-source-of-truth convention (see migration 0121's own header
-- for the same note).

alter table downdetector_baseline_history
  drop constraint downdetector_baseline_history_sector_check;
alter table downdetector_baseline_history
  add constraint downdetector_baseline_history_sector_check
  check (sector = any (array['telecom', 'banking', 'government', 'other', 'energy']));

alter table downdetector_learned_thresholds
  drop constraint downdetector_learned_thresholds_sector_check;
alter table downdetector_learned_thresholds
  add constraint downdetector_learned_thresholds_sector_check
  check (sector = any (array['telecom', 'banking', 'government', 'other', 'energy']));
