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

## Step 2: bulk-exclude the 760 awaiting-review documents (NOT RUN: blocked, needs a decision)

Scope check (MEASURED): `status='awaiting_review' AND review_status IS NULL AND memory_document_id IS NULL`
= **760 documents holding 18,503 chunks**, exactly as expected. Untouched by design: 33 promoted
documents (14 with no review status + 19 `resolved`), 3 `awaiting_followup`, 54 already excluded.

Blockers found before running anything:
1. A CHECK constraint, `processing_documents_exclusion_reason_check`, allows only NULL,
   `recreational_content`, `unsupported_media` or `temporary_document`. The requested free-text
   reason would be rejected, and the portal's `ExclusionReason` type has the same three values.
2. All 54 existing excluded documents have `chunk_count = 0`. The 760 carry their original counts, which
   would go stale after the chunk rows are deleted. The knowledge workbench displays `chunk_count`
   ("Chunk preview (N of chunk_count)"), so it would read "0 of 27".
3. Worker check: `list_excluded` is report-only, so excluded documents are never re-activated and the
   chunks will not come back on their own. Once deleted, promoting one of these documents later would
   need re-processing (the decide flow copies existing chunk rows).

## Step 3: weekly size line and 450 MB warning (CODE DONE, migration 0230 NOT YET APPLIED)

* `intelligence/db_size.py`: weekly line "Supabase DB: X MB of 500 MB (Y%)" in `generate_weekly_report()`;
  a once-a-day guard on the morning brief in `send_brief()` that sends one WARNING through the existing
  `notify()` path at 450 MB or more, with a 24h cooldown. No new scheduler.
* Size source: new read-only RPC `public.get_db_size_bytes()` (migration 0230, `service_role` only), because
  `pg_database_size()` is not reachable through PostgREST tables. Until it is applied the weekly line reads
  "size unavailable" and the guard stays quiet.
* 14 new tests; verified they fail with the two `captains_brief.py` hooks removed.

## Follow-ups
* Decide the step 2 approach (see the options in the session report) and run it with the row-count gate.
* Apply migration 0230 once reviewed.
* `VACUUM FULL public.processing_chunks` after step 2 (the table shrinks only after a rewrite).
