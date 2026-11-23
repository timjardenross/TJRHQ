# Weekly evidence snapshot — migration proposal and rollback plan (NOT APPLIED)

**Status:** prepared for review. Nothing in this folder is executed by CI, auto-deploy or any scheduler.
It is deliberately outside `core/infrastructure/supabase/migrations/`. No migration, retention deletion
or scheduled writer has been applied or enabled.

## What it adds
One new append-only table, `public.weekly_evidence_snapshot` (see `0261_weekly_evidence_snapshot.up.sql`):
weekly DB size and per-table sizes, exact universe counts, the **evidence cited by the week's brief**
(event id, title, source, URL, date) and a report hash. **No personal health data.**
Estimated growth: well under 1 MB per year (a few KB of metadata plus up to ~200 cited items per week).

## Why
1. A measured size history is the precondition for any growth forecast (`forecast_growth` refuses to
   forecast with fewer than 4 snapshots over 21 days).
2. A retention policy (e.g. 90 days) would delete the events behind older briefs. Snapshotting the cited
   evidence first keeps every published or archived brief traceable. (The validation suite already lost
   4 of 8 real cases to the 11 Oct manual prune.)

## Before applying (all must be true)
- [ ] Captain approves the schema change in writing.
- [ ] Migration number is still free (`ls core/infrastructure/supabase/migrations | tail`).
- [ ] Backups confirmed in the Supabase dashboard (plan and retention of backups are not visible from the repo).
- [ ] A read-only dry check of the SQL on a Supabase branch database (`create_branch`) passes.
- [ ] Merge sequence for #658/#659/#660/#661 agreed (the snapshot writer is a later, separate approval).

## Apply (by the Captain or with explicit approval; not by CI)
1. Apply `0261_weekly_evidence_snapshot.up.sql` (single transaction; idempotent via `IF NOT EXISTS`).
2. Verify (read-only):
   - `select count(*) from public.weekly_evidence_snapshot;`  → 0
   - `select relrowsecurity from pg_class where relname='weekly_evidence_snapshot';` → true
   - `select count(*) from pg_policies where tablename='weekly_evidence_snapshot';` → 0 (deny-all)
3. Nothing writes to it until a separate approval enables the weekly writer.

## Rollback
Run `0261_weekly_evidence_snapshot.down.sql` (drops the index and the table). Safe: new table, no dependants,
no data from other tables is modified. If rows already exist, export first (client-side) as noted in the file.
Verify: `select to_regclass('public.weekly_evidence_snapshot');` → null.

## Retention linkage (not enabled)
A retention job must NOT run until: (a) this table exists and has at least one successful snapshot of the
cited evidence for every brief that will lose its source rows; (b) the Captain approves the window; (c) the
physical-space caveat is accepted (a plain DELETE stops growth but does not shrink the files until
space is reclaimed). Estimated one-off effect of a 90-day rule: about 27–28 MB (~10% of 262 MB).

## Interim without a schema change
`SnapshotStore` in `intelligence/weekly_evidence.py` writes JSONL beside the existing alert-state files on the VM.
It is atomic and fsynced but only as durable as that disk; confirm VM backups before relying on it.
