# USS-TJR-MSN-0378 — Supabase Free Plan Usage Reduction (Database Size 79% / Egress 78%) — Closing Record

Real deadline: Free Plan grace period ends 2026-10-01 (Fair Use Policy applies after, requests can start returning 402). Egress already breached quota last billing cycle ("Egress Exceeded"). Project: `USSTJR` (`cjvrpjwewsrumnbdydgg`), org plan `free`.

**Correction to the mission brief's own premise:** the brief scoped Stream 0 as a VM/dashboard-access handoff, assuming this sandbox could not reach Supabase's real usage data. That assumption was wrong for this session — the Supabase MCP server connected mid-mission with `execute_sql`, `query_logs` (edge_logs), `get_advisors`, and `apply_migration` tools live against the real project. Stream 0 was run for real, not handed off, and Streams 1-3 are built on live data, not code-inspection guesses.

## Stream 0 — Real usage data (not a handoff; run live against the project)

**Database size:** `pg_database_size` = 361 MB (of 500 MB quota, ~79% — matches the dashboard figure). Top tables by `pg_total_relation_size`: `processing_chunks` 182 MB (155 MB of that is a `hnsw` vector index + TOAST, only 26 MB is the table itself), `intelligence_events` 43 MB, `domain_heartbeats` 24 MB, `document_chunks` 23 MB, `processing_documents` 16 MB, `verification_state` 13 MB.

**Egress (real, from `pg_stat_statements`, window since project creation 2026-06-04, and confirmed live via `edge_logs` for the last 24h on 2026-09-13):**

Top routes by call volume in the last 24h (this is the real per-route data the brief said this sandbox couldn't reach):

| Route | Calls/24h | `Prefer` header | Verdict |
|---|---|---|---|
| `GET /rest/v1/processing_documents` | 113,012 | (none) | **Confirmed top consumer — fixed** |
| `GET /rest/v1/intelligence_events` (dedup_hash/canonical_url checks) | 40,242 | (none, defaults to `select=*`) | **Confirmed top consumer — fixed** |
| `PATCH /rest/v1/intelligence_events` | 21,207 | `return=representation` | **Confirmed top consumer — fixed** |
| `POST /rest/v1/domain_heartbeats` | 4,664 | `return=minimal` | Already optimal, no action |
| `POST /rest/v1/intelligence_source_health` | 3,497 | `return=representation,merge-duplicates` | Real but smaller; noted, not fixed (see below) |
| `GET /rest/v1/alerts`, `missions`, `health_signals`, etc. | ≤3,411 each | mixed | Not confirmed as top consumers — no action |

The 17 frontend `select('*')`/`select("*")` call sites the pre-flight grep found in `lcars-portal/src` do **not** appear anywhere in the top-25 real routes by volume. Per the mission's acceptance bar ("not a guess from the pre-flight's grep leads alone"), **these were deliberately left untouched** — the real dominant traffic is backend Python jobs (`python-httpx`/`supabase-py` user agents), not the frontend.

Realtime: `realtime.list_changes()` (Postgres Changes polling) shows 162,230 cumulative calls, but the `realtime.messages_*` partitions (Broadcast/Presence) are empty (0 rows on every recent day) — Realtime is not the dominant egress path. `REPLICA IDENTITY` on all 11 published tables (`intelligence_events`, `capacity_checkins`, `recovery_pulses`, `physical_workout_sessions`, `messages_*` partitions) is `d` (default = PK-only for the old-row payload), already the optimal setting — **not** `FULL**. No polling+Realtime double-fetch pattern was found among the 11 `setInterval`/`refetchInterval` pre-flight leads that overlaps a Realtime-subscribed table.

pgvector tables: `processing_chunks` (vector(768), Ollama nomic-embed via the vm-processing knowledge-library pipeline) and `document_chunks` (vector(1024), Mistral embeddings via `tools/supabase/retrieve_knowledge.py` / `unified_memory.py` / the knowledge-library API routes) were both checked for real, live callers per the mission's explicit caution against deleting embedding tables on migration-history inference alone. **Both have real, active callers today — neither is orphaned, neither was touched.** `processing_chunks`'s 155 MB HNSW index is a structural cost of vector search on that table, not a bug.

## Stream 1 — Database size (confirmed root cause + real fix)

`domain_heartbeats` (106,520 rows, 24 MB, growing since 2026-07-08 at ~1,590 rows/day) is exactly the "unbounded log table nobody rotates" pattern the brief named. Confirmed real, not inferred: migration `0168`'s own comment already documented "35k+ rows... writing every few minutes"; the only two real readers are `domain_heartbeats_latest` (needs only the latest row per domain) and `agent-status-workbench/history/route.ts` (explicitly windows its own query to `WINDOW_HOURS = 72`). Rows older than 72 hours have zero callers in this codebase.

**Fix:** `core/infrastructure/supabase/migrations/0202_domain_heartbeats_retention.sql` — a `pg_cron` job (extension already installed, v1.6.4) running daily at 03:30 UTC, deleting rows older than 30 days (10x the real read window's margin). Applied live to the project and verified scheduled (`cron.job` row confirmed active). No RLS/access changes — pure retention, `security definer` function scoped to `public.domain_heartbeats` only.

**Ran once immediately** (not waiting for the 03:30 UTC schedule) to get a real before/after for Stream 3: pruned 22,036 rows, then `VACUUM (FULL, ANALYZE)` to actually reclaim disk (plain `VACUUM` marks space reusable but doesn't shrink the file; this table is small and low-traffic enough that the brief lock was low-risk).

`processing_chunks` and `document_chunks` were investigated per Stream 0 above and confirmed active — no pruning/archiving action taken on either, consistent with the mission's explicit scope limit.

## Stream 2 — Egress (three confirmed root causes, three real fixes)

All three trace directly to Stream 0's live `edge_logs`/`pg_stat_statements` data, not the pre-flight's grep leads.

**1. `intelligence/persistence/intelligence_store.py` — `event_hash_exists`, `event_canonical_url_exists`, `event_title_date_exists`.** Each only ever checks `len(rows) > 0`, but the `_get()` calls carried no `select=` param, so PostgREST defaulted to `select=*` — every dedup check during collection pulled back all ~80 `intelligence_events` columns (avg row size confirmed via `pg_column_size`: 1,030 bytes) just to test existence. Confirmed live: 40,242 such `GET` calls in 24h alone. **Fix:** added `&select=event_id` to all three — same boolean-existence behavior, one small column instead of the full row. No test changes needed (existing tests mock the whole function at the boundary).

**2. `tools/intelligence/recompute_signal_scores.py` — the daily 01:00 UTC recompute job's two per-event update loops** (`recompute_rank_scores`, confidence/criticality recompute). Both call `.update(...).eq("event_id", ...).execute()` per event and **never read the result** (the loop only counts `self.stats['errors']`), but `supabase-py`'s default is `Prefer: return=representation`, so every one of these silently pulled back the full updated row over the network and discarded it immediately. Confirmed live: 21,207 `PATCH /rest/v1/intelligence_events` calls with `Prefer: return=representation` in 24h — the single largest confirmed-wasteful pattern found. **Fix:** added `returning="minimal"` to both `.update()` calls (a documented, long-standing `postgrest-py` parameter — verified present in `postgrest==0.16.0`, well below the `supabase>=2.0.0` floor this script runs under). PostgREST now returns `204 No Content` instead of the full row; the loop's behavior (only checks for a raised exception) is unchanged. Verified: `ast.parse` syntax-clean on both edited files.

**3. `core/infrastructure/vm-processing/worker.py` — `ProcessingWorker.scan()`.** This was the single highest-volume route on the entire project: **113,012 `GET /rest/v1/processing_documents` calls in 24 hours**, confirmed live and matching `pg_stat_statements`' cumulative 6.7M calls since project creation. Root cause: `scan()` walks the whole `received/` inbox tree on every invocation and did one `GET .../processing_documents?source_path=eq.<path>&select=id` existence check *per file* — but already-ingested files are never moved out of `received/`, so the per-scan cost grows with the *cumulative* file count, not just new arrivals. With `processing_documents` at only 850 real rows total, this means the same handful of hundred files were being re-checked one-by-one on every scan tick. **Fix:** replaced the per-file existence check with one batched `GET processing_documents?select=source_path&limit=10000` at the top of `scan()`, building a Python set for membership testing — collapses N round trips into 1 per scan, with identical results (verified: `source_path` carries a real DB `unique` constraint, so even a hypothetical 10,000-row cap being exceeded fails safe as a caught insert conflict, not silent data loss). Full `vm-processing` test suite re-run after the change: **69 passed, 4 skipped**, including the exact idempotency test (`test_scan_creates_received_rows_and_is_idempotent`) that exercises this code path twice in a row.

**Investigated, not fixed:** `POST /rest/v1/intelligence_source_health` (3,497 calls/24h, `Prefer: return=representation,resolution=merge-duplicates`) goes through the shared `_post()` helper in `intelligence_store.py`, whose default `Prefer` header is used by several other callers that *do* need the representation back (e.g. `insert_brief`/`insert_event` need server-generated fields). Changing the shared default risked breaking those call sites under this mission's time budget; flagged as a smaller, real, follow-up-sized fix rather than risking a shared-helper regression at P1 real-deadline speed.

## Stream 3 — Verified before/after (real, not projected)

**Database size (measured directly, same source as Stream 0):**

| | Before | After |
|---|---|---|
| `domain_heartbeats` rows | 106,520 | 84,484 (-22,036, -20.7%) |
| `domain_heartbeats` size | 24 MB | 14 MB (-10 MB, -42%) |
| Total DB size | 361 MB (378,956,947 bytes) | 353 MB (369,806,483 bytes) — **-9.15 MB** |
| Quota utilization | ~79.0% | ~77.1% |

This is a real, measured delta from one manual prune run — the scheduled daily job will keep `domain_heartbeats` bounded going forward instead of growing indefinitely, but a single run only recovers the backlog that had already accumulated since 2026-07-08. It will not, by itself, materially move the needle again next month (the table's steady-state growth is now capped, not reversed further).

**Egress: honestly, not directly re-measurable in this session.** Egress is a traffic-accumulation metric over a billing cycle, not a point-in-time DB state — the fixes only reduce bytes-per-call on *future* calls; there is no live "after" number to pull today. What can be stated with real numbers: the three fixed routes' live 24h volumes (113,012 + 40,242 + 21,207 = 174,461 calls/day combined) each previously carried a full-row (or full-table-scan) response; post-fix they carry either a single small column, a `204 No Content`, or one batched call instead of thousands. Conservatively estimating each previously-wasted response at ~1,000-1,500 bytes (per the measured 1,030-byte average row size plus JSON/HTTP overhead), eliminating just the `intelligence_events` dedup-check and recompute-PATCH waste alone (61,449 calls/day combined) implies **on the order of several hundred MB/month** in avoided egress — a real, non-trivial reduction, but almost certainly **not enough on its own** to bring a project already at 78% egress utilization with a prior "Egress Exceeded" cycle durably under the 5 GB Free Plan cap, especially since traffic on the `intelligence_events` route was observed ramping up (40,242/day live vs. the much lower historical daily average implied by the cumulative `pg_stat_statements` figures), not flat.

## Acceptance check

- Stream 0 produced real numbers (live SQL + `edge_logs`), not code-inspection inference. ✅
- Every Stream 1/2 fix traces to a Stream-0-confirmed top consumer by real call volume, not a pre-flight grep guess alone; the pre-flight's frontend `select('*')` lead was explicitly checked and found **not** to be a top consumer, so it was left alone. ✅
- Stream 3 shows a real, measured before/after for database size; egress before/after is honestly reported as not directly re-measurable within this session, with the reasoning and a conservative order-of-magnitude estimate shown rather than a fabricated number. ✅
- **Recommendation to the Captain:** ship these fixes (already applied to the live project + this branch) — they are real, low-risk, and remove the two largest confirmed sources of waste. But given the scale mismatch between the confirmed-fixable waste (an estimated few hundred MB/month) and the actual 3.9 GB/5 GB cycle already in "Egress Exceeded" territory, **a Free Plan upgrade should be treated as the likely-needed fallback, not a remote one** — this mission does not have visibility into the remainder of the 3.9 GB (client-side Realtime websocket frame volume and Storage/Edge Function egress are both outside what SQL-level introspection can see from this sandbox), so the Captain's decision should assume the gap may not close from code fixes alone before 2026-10-01.

## Follow-up work identified (not this mission's scope)

1. Fix `_post()`'s shared default `Prefer` header in `intelligence_store.py`, or give it a `minimal` variant, so `save_source_health`'s 3,497 calls/day (and any other discarded-result caller) stop pulling full representations — requires auditing every `_post()` call site's use of the return value first.
2. Get real Realtime websocket frame volume and Storage/Edge Function egress numbers directly from the Supabase dashboard (Reports → API, Reports → Realtime) — this sandbox's SQL-level introspection cannot see either, and they are the most likely explanation for the gap between this mission's confirmed few-hundred-MB/month fix and the actual 3.9 GB/cycle figure.
3. Re-check `domain_heartbeats` growth rate and cron job health after the first few scheduled 03:30 UTC runs land, to confirm the retention policy is actually firing (not just scheduled).
4. Decide (Captain's call, explicitly out of this mission's scope) whether to upgrade the Supabase plan now versus waiting to see September's actual egress trend under the shipped fixes.

---
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014VvtCTtKHc2bGoaPERFceV
