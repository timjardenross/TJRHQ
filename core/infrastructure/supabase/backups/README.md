# Supabase pre-drop backups

Row-data snapshots taken immediately before a `DROP TABLE` migration, kept
here as the actual safety net for tables retired from the live Supabase
project (`USSTJR`, id `cjvrpjwewsrumnbdydgg`). Table *schema* is not
duplicated here — it's already versioned in `../migrations/` and can be
replayed from there; these files only hold the row data, which isn't
tracked anywhere else once the table is gone.

To restore a table from one of these snapshots: re-run its original
`CREATE TABLE` migration (or reconstruct it from `information_schema` if
the migration itself was superseded), then bulk-insert the corresponding
array from the JSON file.

## 2026-09-01-dead-tables-pre-drop.json

Snapshot taken before `0183_drop_retired_dead_tables.sql`. Covers 13
tables identified as having zero live code readers/writers (see that
migration's header comment for the evidence per table). Row counts at
snapshot time:

| Table | Rows |
|---|---|
| `temporal_entities_archived_2026` | 88 |
| `temporal_episodes_archived_2026` | 78 |
| `temporal_facts_archived_2026` | 118 |
| `decision_outcomes` | 6 |
| `command_memory` | 4 |
| `research_input_archived_2026` | 0 |
| `captured_item_links` | 0 |
| `captured_item_text` | 0 |
| `quality_scores` | 0 |
| `feedback_signals` | 0 |
| `provider_quality_history` | 0 |
| `quality_forecasts` | 0 |
| `quality_anomalies` | 0 |
