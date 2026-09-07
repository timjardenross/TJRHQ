-- Supabase footprint/cost cleanup (2026-09-01), companion to the egress-
-- reduction work in intelligence/scheduler.py / core/platform/event_bus.py.
-- Drops 13 tables confirmed to have zero live code readers or writers.
-- Row data for every non-empty table here was snapshotted first to
-- core/infrastructure/supabase/backups/2026-09-01-dead-tables-pre-drop.json
-- (schema itself stays recoverable from this migration history) -- that
-- file is the actual safety net; this is not a same-database rename like
-- migrations 0181/0182 used for domain_registry soft-retirement.
--
-- Evidence per table (full investigation in this session's PR):
--
-- research_input_archived_2026 (0 rows) -- already renamed 2026-08-10
--   (orphaned-rls-tables-investigation.md): zero owning code anywhere in
--   the tracked repo, superseded by build_request_inbox.
-- temporal_entities_archived_2026 (88 rows), temporal_episodes_archived_2026
-- (78 rows), temporal_facts_archived_2026 (118 rows) -- already renamed
--   2026-08-10, same investigation: one-time bitemporal knowledge-graph
--   prototype (migration 0028), zero owning code after two independent
--   greps, superseded by core/knowledge_navigation/ the next day.
-- captured_item_links, captured_item_text (0 rows each) -- created by
--   tools/supabase/schema/MSN-DISCOVERY-001-CAPTAINS-INBOX-SCHEMA.sql
--   alongside the live captured_items table, but no application code
--   (Python/TS) anywhere ever selects/inserts either -- designed, never
--   wired up.
-- command_memory (4 rows, all git_commit events from 2026-06-11) -- the
--   only would-be reader/writer path runs through platform-runtime/app.py
--   ::_init_learning_loop(), which migration 0170's own note says exists
--   solely in a backup directory (not the live repo) behind
--   starfleet-slack-bot.service, disabled since 2026-07-07. Superseded by
--   commander_memory_events for live command-memory tracking.
-- quality_scores, feedback_signals, provider_quality_history,
-- quality_forecasts, quality_anomalies, decision_outcomes -- the whole
--   B1C/B1D/B1E Learning Loop chain. Migration 0117 already
--   Captain-confirmed this chain retired (all three heartbeat-wired
--   writers trace to retired Slack-era event sources with no live
--   replacement); the only instantiation path is the same disabled
--   _init_learning_loop() above. Zero hits anywhere in lcars-portal.
--
-- Dropped child-before-parent per the live FK graph (verified via
-- information_schema -- no table outside this set references any of
-- these as a foreign key target, so nothing else is affected):
--   quality_anomalies -> quality_scores
--   feedback_signals -> quality_scores, decision_records (decision_records is live, untouched)
--   quality_scores -> decision_outcomes, decision_records (untouched)
--   decision_outcomes -> commander_decisions (live, untouched)
--   temporal_facts_archived_2026 -> temporal_entities/episodes_archived_2026
--   captured_item_links / captured_item_text -> captured_items (live, untouched)
--   command_memory -> missions (live, untouched)
--   research_input_archived_2026 -> batch_jobs (live, untouched)

drop table if exists quality_anomalies;
drop table if exists feedback_signals;
drop table if exists quality_scores;
drop table if exists decision_outcomes;

-- Discovered at apply time via pg_depend / information_schema.views (full
-- dependency graph re-checked, nothing else found): two views and one
-- function over the temporal_* archived tables from the same 2026-08-10
-- archival, named with the same _archived_2026 suffix and referenced
-- nowhere but the investigation doc itself (grep-confirmed).
drop view if exists temporal_facts_current_archived_2026;
drop view if exists temporal_fact_chain_archived_2026;
drop function if exists temporal_search_episodes_archived_2026(text, integer);

drop table if exists temporal_facts_archived_2026;
drop table if exists temporal_entities_archived_2026;
drop table if exists temporal_episodes_archived_2026;
drop table if exists captured_item_links;
drop table if exists captured_item_text;
drop table if exists command_memory;
drop table if exists research_input_archived_2026;
drop table if exists provider_quality_history;
drop table if exists quality_forecasts;
