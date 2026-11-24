# Provenance activation runbook (checklist item: Provenance and verified freshness, Partial to Operational)

Prepared 2026-11-24. NOTHING here has been applied: no migration, no flag, no deployment, no production write. Everything labelled
"expected" below was measured by SELECT against production (project `cjvrpjwewsrumnbdydgg`) on 2026-11-24 or tested on a throwaway local Postgres.

Files (all under `tools/intelligence/`): `provenance_migration_20261124.sql`, `..._ROLLBACK.sql`, `provenance_backfill_dryrun.sql` (SELECT only),
`provenance_backfill_20261124.sql` (backup table + one transaction + gate + reverse).

## Pre-checks already done

| Check | Result (live, 2026-11-24) |
|---|---|
| Name/type conflicts for the 8 new columns and 4 constraint names on `intelligence_events` | none (61 existing columns; names absent) |
| Unique index on `dedup_hash` | present: `intelligence_events_dedup_hash_key` UNIQUE (dedup_hash); 0 NULL hashes; migration does not touch it |
| Dependants | 4 views (explicit column lists), RLS on, no triggers; table 45,427 rows, 135 MB |
| Flag default | `INTEL_PROVENANCE_COLUMNS` unset and `PROVENANCE_COLUMNS_EXIST=False`: `columns_exist()` is False, `select_columns()` is empty, rows unchanged (not referenced in any deploy file) |
| SQL syntax and behaviour | migration run twice (idempotent), backfill, backfill-reverse and rollback all run on a scratch Postgres 16 with a 7-row synthetic table |

## Dry-run backfill (production counts, SELECT only)

| Rule | Rows | basis / precision / confidence | label |
|---|---|---|---|
| R1 no `published_at` | 1,764 | collected_fallback / unknown / unknown | none |
| R2 `published_at` = `collected_at` (Twilio 240, AEMO 54) | 294 | collected_fallback / unknown / unknown | none |
| R3 Google News | 826 | aggregator_claimed / second / claimed | none |
| R4 CISA KEV dateAdded | 148 | date_only / day / claimed | catalogue_addition |
| R5 AEMO notice date-only | 415 | date_only / day / claimed | publication |
| R6 `published_at` more than 1h after collection (Cloudflare, Zoom, Twilio maintenance) | 120 | unknown / unknown / unknown (+ `event_window_start`) | event |
| R7 other feeds/APIs | 41,860 | feed / unknown / feed | none |

Total 45,427 = every row. Reader freshness after backfill, collected in the last 24h: VERIFIED 360 (all R7), CLAIMED 12 (R3 7, R5 5), UNKNOWN 9 (R1 3, R2 4, R6 2),
KNOWN STALE 135 (R7 117, R3 18). Rows older than 24h are all KNOWN STALE (44,911 rows; 45,046 stale in total). Behaviour change on old rows is limited to R3 (VERIFIED to CLAIMED), R1/R2/R6
(timed by collection) and R4/R5 (day-precision CLAIMED); R7 is unchanged.

Audit sample (30 rows, stratified deterministic by `md5(event_id)`: R1 3, R2 4, R3 4, R4 4, R5 4, R6 6, R7 5, read row by row): 30/30 correctly labelled by their rule.
One caveat on R7: Geoscience Australia Earthquakes `published_at` is the quake origin time (an event time) and is labelled `feed`; this is how the live writer labels it too and it is
left as is (2,341 rows; follow-up).

## Activation sequence (each step has a gate; stop at the first failed gate)

**Step 0, approval.** Owner approves steps 1 to 4 below.

**Step 1, migration** (`provenance_migration_20261124.sql`, via `apply_migration`; 5s lock timeout, metadata-only).
Gate: `SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='intelligence_events' AND column_name IN ('publisher_domain','publisher_family','published_at_basis','published_at_precision','published_at_confidence','published_at_label','event_window_start','event_window_end');` = 8;
`SELECT count(*) FROM pg_constraint WHERE conrelid='public.intelligence_events'::regclass AND conname LIKE 'intelligence_events\_pub\_%\_chk';` = 4;
`SELECT count(*) FROM intelligence_events;` unchanged (within new arrivals); flag still OFF so nothing reads or writes the columns. Rollback: `..._ROLLBACK.sql`.

**Step 2, flag on for the writer.** Set `INTEL_PROVENANCE_COLUMNS=1` in the `intelligence-scheduler` environment (Infisical) and restart it. The brief reader
(`brief_evidence.load_events`) reads the same flag; the brief runs from the same environment, so it switches at the same time, which is safe once step 1 is applied
(old rows read as NULL provenance, identical to today).
Gate, after at least one full collection cycle: new rows carry provenance.
`SELECT count(*) FILTER (WHERE published_at_basis IS NOT NULL) AS with_prov, count(*) AS total FROM intelligence_events WHERE collected_at > '<flag-on time>';` with_prov = total (0 failures);
`SELECT published_at_basis, published_at_confidence, published_at_label, count(*) FROM intelligence_events WHERE collected_at > '<flag-on time>' GROUP BY 1,2,3 ORDER BY 4 DESC;`
expect Google News = aggregator_claimed/claimed, KEV = date_only/verified/catalogue_addition, AEMO = date_only|feed_corrected_utc, no row with `published_at_confidence='verified'` and `published_at_precision<>'day'`.
Also check the scheduler journal for zero PostgREST 400/PGRST204 errors on `intelligence_events` since restart. Rollback: unset the flag and restart (columns can stay).

**Step 3, verify consumers on live new rows (read-only).**
(a) Brief: the evidence layer is gated by `BRIEF_EVIDENCE_V1*`. Replay the last 24h through `brief_evidence.build_evidence` in a scratch process with the flag on and confirm every incident has `freshness` in {VERIFIED, CLAIMED, UNKNOWN, KNOWN STALE}, that incidents whose only reports are Google News show CLAIMED, and that none is described as confirmed current. Code paths are covered by `tests/test_provenance_v1.py` and `tests/test_brief_evidence.py`.
(b) Portal: the workbench routes under `lcars-portal/src/app/api/intelligence-workbench/` select explicit column lists and do not read the new columns, so they are unaffected (no breakage), but they do not yet display claimed or unknown states and present `published_at ?? collected_at` as the time. Surfacing the states in the portal is NOT part of this package and is the remaining gap for a fully "Operational" portal view; confirm with the owner whether the portal view is required for the checklist item.
Gate: (a) passes; (b) route responses unchanged (HTTP 200, same fields) after step 1.

**Step 4, backfill** (`provenance_backfill_20261124.sql`, one transaction, creates `intelligence_events_provenance_bak_20261124`).
Immediately before: re-run Q1 of `provenance_backfill_dryrun.sql`; counts should match the table above plus recent arrivals (R7 grows fastest; R1 to R6 should move only slightly). A large shift in R2 or R6 means a source behaviour changed: stop and re-audit.
Gate (inside the script, aborts and rolls back on failure): every backed-up row labelled, none left NULL.
After: `SELECT count(*) FROM intelligence_events WHERE published_at_basis IS NULL;` = 0;
`SELECT published_at_label, count(*) FROM intelligence_events GROUP BY 1;` catalogue_addition = R4 count, event = R6 count (+ any new), publication = R5 count (+ new);
`SELECT count(*) FROM intelligence_events e JOIN intelligence_events_provenance_bak_20261124 b USING (event_id);` = backup rows;
`SELECT count(*) FROM intelligence_events WHERE published_at_confidence='verified' AND event_id IN (SELECT event_id FROM intelligence_events_provenance_bak_20261124);` = 0 (backfill never promotes).
Then validate the four constraints (commented block at the end of the script) and confirm `convalidated = true` for all four. Reverse: block at the end of the script.

## Done means

Step 4 gates pass, new rows keep arriving with provenance for 48h with zero write errors, and the owner has decided on the portal display gap. Drop the backup table once accepted.

## Risks

- Backfill labels are inferences (least-trusting); R3 rows older than 24h are KNOWN STALE anyway, so the visible change is small.
- Flag and brief reader share one process: on a bad step 2, unset the flag and restart; no schema change is needed.
- R7 `feed` rows keep VERIFIED even where the source's `published_at` is an event time (earthquake origin time); unchanged from today.
- Portal does not show the new states (see step 3b).
- Pre-existing, unrelated: 5 failing tests on `origin/main` (`test_intelligence_brief_generator` Mistral stages x3, `test_xo_brief_html_escape` x2) and 4 collection errors needing `flask`.
