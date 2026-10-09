# USS-TJR-MSN-0412 Stream 4: Supabase headroom (knowledge record)

2026-10-09. Labels: MEASURED / INFERENCE / TO BE VERIFIED. Counts and sizes only.
Goal: bring the database from 419 MB (83.8% of the Free plan's 500 MB limit) to 75% or less.

## Safety net first
A restic snapshot taken the same day (5b741a9c, 17:22) holds the full Supabase dump. Verified by
restoring that one file and listing it: it contains `processing_chunks` (table, index definition,
and 19,441 data rows). Both steps below are recoverable from it.

## Step 1: drop the unused vector index (APPLIED)

| | Before | After |
|---|---|---|
| Database size | 419 MB (83.8%) | **350 MB (70.0%)** |
| `processing_chunks` total | 173 MB (indexes 71 MB) | 104 MB (indexes 2 MB) |

Evidence the index was unused (MEASURED): `idx_scan = 0` and `idx_tup_read = 0` since the stats reset on
2026-05-22; 69 MB. No function, view, materialised view, policy or trigger references the table, and
no constraint depends on the index. No repo code runs a similarity query on `processing_chunks`: the
portal reads it by `document_id`, the knowledge-library decide flow copies already-embedded rows into
`document_chunks`, and the similarity RPC `match_document_chunks` searches `document_chunks`.

Applied as migration `0229_drop_unused_processing_chunks_hnsw` (recorded in
`supabase_migrations.schema_migrations`). The rollback is in the file header.

Stream 4's acceptance target (75% or less) is met by this step alone.

## Step 2: bulk-exclude the 760 awaiting-review documents (DONE, Option A)

The first design hit three blockers (see "Findings"), so the Captain chose Option A: keep to the values the
schema allows and record the decision in `metadata`.

Scope (MEASURED): `status='awaiting_review' AND review_status IS NULL AND memory_document_id IS NULL`
= **760 documents holding 18,503 chunks**. Untouched by design: 33 promoted documents (14 with no review
status + 19 `resolved`), 3 `awaiting_followup`, 54 already excluded.

Run as one `DO` block (one transaction) that raises and rolls back unless exactly 760 documents and 18,503
chunks are in scope and exactly those were updated and deleted:

```sql
-- scope snapshot, then (abort unless docs = 760 and chunks = 18503):
update public.processing_documents d
   set status = 'excluded', exclusion_reason = null, chunk_count = 0, updated_at = now(),
       metadata = coalesce(d.metadata, '{}'::jsonb) || jsonb_build_object('bulk_exclusion', jsonb_build_object(
         'by', 'Captain', 'at', now(), 'mission', 'USS-TJR-MSN-0412 Stream 4',
         'reason', 'Bulk-excluded by Captain 2026-10-09 (USS-TJR-MSN-0412 Stream 4)',
         'previous_status', 'awaiting_review', 'previous_chunk_count', s.chunk_count))
  from _scope s where d.id = s.id
   and d.status = 'awaiting_review' and d.review_status is null and d.memory_document_id is null;
delete from public.processing_chunks where document_id in (select id from _scope);
-- abort unless updated = 760 and deleted = 18503
```

Then `VACUUM (FULL, VERBOSE) public.processing_chunks` (cannot run in a transaction; run through psql).

Result (MEASURED, queried afterwards):
* 814 excluded documents (54 + 760); 33 promoted and 3 `awaiting_followup` unchanged.
* 760 carry `metadata.bulk_exclusion`; their `previous_chunk_count` values sum to exactly 18,503.
* 938 chunks remain, all on the 36 protected documents; 0 orphans; 0 chunks on any excluded document.
* 0 excluded documents have a non-zero `chunk_count` or a reason set.

Rollback: the 5b741a9c snapshot's dump holds every deleted chunk row; restore only that table's data with
`pg_restore -a -t processing_chunks`, then reset the 760 documents from `metadata.bulk_exclusion`
(`previous_status`, `previous_chunk_count`).

## Sizes

| After | Database | Of the 500 MB limit |
|---|---|---|
| Before Stream 4 | 419 MB | 83.8% |
| Step 1: drop the index | 350 MB | 70.0% |
| Step 2: delete (plain DELETE frees nothing yet) | 352 MB | 70.4% |
| Step 2: `VACUUM FULL processing_chunks` (104 MB -> 5.2 MB) | **252 MB** | **50.5%** |

Acceptance target (75% or less): met, with margin.

## Knowledge library check
The portal needs a login, which was not available, so the page was not rendered. Verified instead:
* The list route's exact query replayed against live data: 850 documents; `status=excluded` returns 814
  with 0 non-zero `chunk_count`; `awaiting_review` returns 36; search still works.
* The detail route's chunk query: a bulk-excluded document returns an empty preview; a promoted document
  still returns its 5 chunks (matching its stored `chunk_count`).
* RLS policies unchanged (`authenticated_read` is true on both tables). The portal service is active with no
  error lines after the change; unauthenticated requests redirect to login.
* To eyeball: open the knowledge workbench and filter on Excluded.

## Step 3: weekly size line and 450 MB warning (DONE, migration 0230 APPLIED)

* `intelligence/db_size.py`: weekly line "Supabase DB: X MB of 500 MB (Y%)" in `generate_weekly_report()`;
  a once-a-day guard on the morning brief in `send_brief()` that sends one WARNING through the existing
  `notify()` path at 450 MB or more, with a 24h cooldown. No new scheduler.
* Size source: read-only RPC `public.get_db_size_bytes()` (migration 0230), `security definer`, empty
  `search_path`, executable by `service_role` only. Verified: service key gets HTTP 200; the anon key is
  refused; `anon` and `authenticated` cannot execute it.
* Real weekly line, from the real module and RPC: `Supabase DB: 252 MB of 500 MB (50%)`. The guard sent
  nothing at this size.
* 14 new tests; they fail with the two `captains_brief.py` hooks removed.

## Findings
1. `processing_documents_exclusion_reason_check` allows only NULL, `recreational_content`,
   `unsupported_media`, `temporary_document`, and the portal's `ExclusionReason` type matches. Free text is
   rejected, so the decision is recorded in `metadata` instead.
2. All 54 existing excluded documents have `chunk_count = 0`; the workbench shows `chunk_count`, so it was
   zeroed to match.
3. The worker's `list_excluded` is report-only: excluded documents are never re-activated.
4. The 760 documents' chunks are gone. Promoting one later would need re-processing by the vm-processing
   worker.

## Follow-ups
* `intelligence_events` (about 11k rows per 28 days, no retention) is the main remaining grower; set a
  retention window only if the database trends back above 80%.
* The Contabo and Supabase work for the weekly line is in place; confirm the first real weekly report shows it.
