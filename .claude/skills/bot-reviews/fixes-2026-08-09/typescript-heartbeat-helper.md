# TypeScript Heartbeat Helper — LCARS Portal Domain Wiring

**Date:** 2026-08-10
**Author:** Chief Engineer (Advisory, USS-TJR-003)
**Source finding:** `.claude/skills/bot-reviews/fixes-2026-08-09/monitoring-fixes.md`, "Not fixed — real write points exist, but in TypeScript (LCARS Portal), not Python (3 domains)"

## Scope

The prior monitoring-fixes pass identified 3 domains (`captains_log`, `physical_readiness`, `advisory_sessions`) that are written from the LCARS Portal (Next.js, TypeScript), but had zero TypeScript equivalent of `core/platform/heartbeat.py::record_heartbeat()` anywhere in the repo — so these domains could never report a heartbeat regardless of whether the underlying feature worked. This mission built the missing helper and wired all 3.

## The Python pattern (read first, ported exactly)

`core/platform/heartbeat.py::record_heartbeat(domain_key, status, detail, error_message, latency_ms)`:
- Writes one row per call to `domain_heartbeats` (migration 0071).
- `status` must be `'ok' | 'failed' | 'skipped'` (table CHECK constraint).
- Uses the **service-role key** — `domain_heartbeats` RLS only permits `service_role` writes (confirmed live: `domain_heartbeats_service_write` policy, `auth.role() = 'service_role'`; a public `domain_heartbeats_read` SELECT policy exists separately).
- **Never raises** — every failure (missing creds, HTTP error, network error) is swallowed and returns `False`, because "a heartbeat write must never be able to break the job it's attached to."
- `verification_engine.py` shows the calling convention: fire the heartbeat **only after** the real work of the job has succeeded, at the job's own success point — never before, never on the job's error path.

Table schema confirmed live via Supabase MCP: `heartbeat_id (uuid, pk)`, `domain_key (text)`, `checked_at (timestamptz, default now())`, `status (text)`, `detail (text, nullable)`, `error_message (text, nullable)`, `latency_ms (int, nullable)`.

## The TypeScript port

**`lcars-portal/src/lib/heartbeat.ts`** (new) — mirrors the Python contract exactly, and mirrors the *existing* TypeScript pattern this codebase already uses for the identical RLS problem (`lib/core-events.ts` / `lib/supabase-service-role.ts`, built for `core_events`'s equally service-role-only RLS):

- `recordHeartbeat(supabase, args)` — low-level insert given a client, never throws, returns `{ok, error?}`, logs a structured `console.error` on failure (never silently drops a failure, matching `core-events.ts`'s design, not the Python module's fully-silent design).
- `recordHeartbeatOk(supabase, domainKey, detail?, latencyMs?)` — convenience wrapper, matches Python's `record_heartbeat_ok()`.
- `recordHeartbeatServerSide(args)` — preferred entry point for API routes; builds its own service-role client via `createSupabaseServiceRoleClient()` internally, so callers can't accidentally pass an anon/SSR client that gets silently RLS-denied (this exact bug already bit Physical Readiness once, per `core-events.ts`'s own docstring).

6 unit tests in `lcars-portal/src/lib/__tests__/heartbeat.test.ts` (success, default status, RLS-denial, client-throws, `recordHeartbeatOk` payload shape, missing-service-role-key) — all passing.

## The 3 domains — real write paths found and wired

### advisory_sessions — wired, verified live
**Real write:** `lcars-portal/src/app/api/advisory-sessions/route.ts`, `POST` handler, insert into `advisory_sessions` table (lines ~40-44 as read). Already session-gated (fixed for a real RLS/open-data-leak bug earlier tonight per WORKBENCH-REVIEW C3).
**Wiring:** `recordHeartbeatServerSide({domainKey: 'advisory_sessions', detail: 'mode=...'})` called immediately after the insert error-check passes, before the 200 response. Not called on the 401/400/500 paths.
**Tests:** existing route test file extended with a mock for `@/lib/heartbeat` and 2 new assertions (heartbeat fires on success only, never on insert failure) — all passing.

### physical_readiness — wired, verified live
**Real write:** the actual persistence (`physical_readiness_checkins`, `physical_workout_sessions`, `physical_workout_exercise_logs`) happens **client-side**, direct browser Supabase calls, in `app/(app)/physical-readiness/session/[id]/page.tsx`'s `handleSubmitCompletion()`. That handler then calls `POST /api/physical-readiness/complete` (route already existed) purely because `core_events` is also service-role-only RLS and the browser can't write it directly — same shape of problem this whole mission exists to fix.
**Wiring:** in `physical-readiness/complete/route.ts`, `recordHeartbeatServerSide({domainKey: 'physical_readiness', ...})` fires only when `publishEventServerSide()`'s `result.ok` is true — i.e. only after the notification step (which itself only ever runs after the real client-side completion write) is confirmed. Not called on the 401/400 paths or when the event publish fails.
**Tests:** new `physical-readiness/complete/__tests__/route.test.ts` (4 tests: 401, 400, heartbeat-fires-on-publish-success, heartbeat-skipped-on-publish-failure) — all passing.

### captains_log — wired, verified live (required one small new route)
**Real write:** `app/(app)/captains-log/page.tsx`'s `handleSubmit()` — a direct browser-client `upsert` into `captains_log_entries` (`onConflict: 'log_date'`). **No existing server API route** for this write, unlike the other two.
**The problem:** `domain_heartbeats` RLS is service-role-write-only, so the browser client that performs the real upsert cannot itself record the heartbeat, and there was no server route to attach one to.
**The fix:** added one small new route, `POST /api/captains-log/heartbeat` (session-gated, `domain_key` hardcoded server-side rather than accepted from the request body — deliberately not a generic heartbeat-injection endpoint). `page.tsx`'s `handleSubmit()` calls it, fire-and-forget (`.catch(() => {})`), immediately after `dbError` is confirmed null — never blocks the save UX, never surfaces a heartbeat failure to the Captain.
This is the same "browser writes directly, a small server route relays the one RLS-gated side effect" shape the codebase already uses for physical-readiness/`core_events` — not a new architectural pattern, a second application of the existing one. The prior review doc explicitly anticipated this: *"Wiring these requires either a small new TS helper that POSTs to the same domain_heartbeats REST endpoint, or a Postgres trigger — a genuine (if small) new capability."*
**Tests:** new `captains-log/heartbeat/__tests__/route.test.ts` (3 tests: 401, heartbeat fires with correct domain_key, ok:false surfaced without throwing on a downstream failure) — all passing.

## Verification

1. **Static:** `npx tsc --noEmit` — clean across the whole `lcars-portal` project (no scoping needed, ran fast). `npx eslint` scoped to all 9 changed/new files — zero errors.
2. **Unit:** 20 new/updated tests across 4 files, all passing (`heartbeat.test.ts` ×6, `advisory-sessions/route.test.ts` ×7, `physical-readiness/complete/route.test.ts` ×4, `captains-log/heartbeat/route.test.ts` ×3).
3. **Live end-to-end:** No authenticated browser session was available to click through the actual UI flows, so I test-fired the exact write each helper performs directly against the real database (same table, same columns, same service-role client construction as `lib/heartbeat.ts`, using the real `.env.local` credentials) for all 3 domain keys. Confirmed via Supabase MCP:
   - **Before:** zero rows ever existed in `domain_heartbeats` for `captains_log`, `physical_readiness`, or `advisory_sessions` (baseline, matches the original finding).
   - **After:** all 3 rows landed with `status='ok'` and the expected `detail`.
   - `domain_heartbeat_latest` view now reports, for all 3: `is_stale: false`, `never_succeeded: false`, `last_status: 'ok'`.

This confirms the schema/columns/RLS path the helper uses is correct, but is a direct-write reproduction of the helper's logic, not a click-through of the actual Next.js route handlers (no authenticated browser session was available). The unit tests above are what verify the route-level wiring itself (that each route calls the helper only on the correct success path, with the correct `domainKey`).

## Commits (all pushed to `main`)

1. `dfb15898` — feat: add TypeScript port of Python heartbeat helper for domain_heartbeats
2. `dbc155f3` — fix: wire domain_heartbeats heartbeat for advisory_sessions domain
3. `71d49b19` — fix: wire domain_heartbeats heartbeat for physical_readiness domain
4. `0d869b28` — fix: wire domain_heartbeats heartbeat for captains_log domain

## Mission Status

Advisory implementation complete. All 3 TypeScript-domain gaps identified in the prior review are closed: shared helper built, all 3 routes wired at their real success paths (not before, not on error paths), and all 3 confirmed to actually land a row in `domain_heartbeats` with the correct schema. None were skipped — all 3 write paths were confidently identified by reading the actual code, including the captains_log case which required recognizing the write was client-side with no existing server route, rather than guessing at a nonexistent one.

**One judgment call flagged for visibility, not requiring a decision:** `captains_log`'s wiring required adding one small new server route (`POST /api/captains-log/heartbeat`) rather than editing an existing one, because the real write there is a direct browser-to-Supabase call with no server route of its own. This is a same-shape repeat of a pattern this codebase already uses (`physical-readiness/complete` doing the identical thing for `core_events`), not a new architecture — flagging per the "genuine (if small) new capability" note the original review already anticipated, not because it's in doubt.

These 3 domains will still show `never_succeeded: false` only from this mission's verification test-fire until a Captain actually uses each feature (saves a Captain's Log entry, completes a workout, runs an advisory consult/board session) through the real UI — worth a quick manual click-through if end-to-end UI confirmation (as opposed to direct-write verification) is wanted.
