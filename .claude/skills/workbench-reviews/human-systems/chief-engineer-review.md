# Chief Engineer Architecture Review — Human Systems Workbench

USS TJR · Registry USS-TJR-003 · Engineering Division · Advisory authority
Reviewer: Chief Engineer persona · Date: 2026-08-09

## Mission Summary

Real architecture review of the Human Systems Workbench (`/human-systems-workbench`), live on the platform and listed in the canonical workbench registry (`lcars-portal/src/lib/workbenches.ts:37-40`) as: "Recovery posture, medical tracking, and physical readiness in one collection - live from the recovery-pulse signal." Specifically tasked with grounding every claim in the real code and — given this domain's prior RLS leak history in this repo (`physical_exercises`, migration 0099, found 2026-08-08) — re-verifying the *current* live RLS/auth state directly, not trusting code comments that assert it.

## Assessment

### What the workbench actually is

Confirmed by reading `lcars-portal/src/app/human-systems-workbench/page.tsx`, its `_components/{KpiDashboard,RecoveryView,MedicalView,ReadinessView}.tsx`, every sub-route under `medical/` and `readiness/`, and the full API surface: `api/human-systems/route.ts` (unified GET, domain-aware), `api/human-systems/{check-in,pulse,activity}/route.ts`, `api/human-systems/readiness/exercise-log/route.ts`, `api/human-systems/readiness/session/[id]/complete/route.ts`, and `api/physical-readiness/complete/route.ts`.

One page (`page.tsx`), three domain tabs (Recovery / Medical / Readiness) via `DomainToggle`, all backed by a single `GET /api/human-systems?domain=…` route that shares one `loadCtx()` fetch (posture RPC + `analytics_health_daily` + `recovery_pulses` + `recovery_confidence_today` + a `physical_workout_sessions` count, `route.ts:176-201`) across all three domains rather than three separate round-trips. No mock or stubbed data anywhere in the read or write paths — every table/view/RPC cited in the route's own header comment (`route.ts:1-19`) is real and checked against the live schema below. `computeLifeParticipation`/`computeRecoveryIndexes` (`route.ts:113-164`) are explicitly documented as mirrors of the canonical `src/lib/ros-data.ts` / `compute_life_participation` SQL logic — composition over reinvention, consistent with platform convention.

Auth: `GET /api/human-systems` and 5 of the 7 write endpoints (`check-in`, `pulse`, `activity`, `readiness/exercise-log`, `readiness/session/[id]/complete`) call `requireSession()` and return 401 with no session (`route.ts:340-343`; same pattern in each POST handler). `requireSession()` and every server-side Supabase client in this route family go through `createSupabaseServerClient()` (`lib/supabase-server.ts:6-27`) — the cookie-based, session-aware `@supabase/ssr` client, used consistently for both reads and writes. This is the correct pattern; it does **not** reproduce the dual-client (anon-key vs. session-aware) mismatch previously found in `ros-data.ts`/`human-systems.ts` (memory: `ros-data-401-regression-2026-07-18.md`) — checked specifically because that bug class originated in this same domain.

### RLS — verified live against production, not trusted from comments

Every write route's header comment makes a claim like *"recovery_pulses' own RLS already requires authenticated for INSERT"* (`pulse/route.ts:3-6`) or *"physical_workout_sessions… (tightened from role=public the same session this route was built)"* (`readiness/exercise-log/route.ts:5-8`). Given this repo's history of exactly this kind of claim going stale (`physical_exercises` was still `public`-writable after its siblings were fixed, per migration 0099's own postmortem comment), I queried the live production database (`cjvrpjwewsrumnbdydgg`) directly rather than accept the comments.

`pg_policies` for every table this workbench reads or writes — `health_daily_logs`, `recovery_pulses`, `activity_logs`, `physical_workout_exercise_logs`, `physical_workout_sessions`, `physical_readiness_checkins`, `physical_exercises`, `captains_log_entries`, `health_insights`:

- All SELECT/INSERT/UPDATE policies are scoped to role `authenticated` only. No `anon`/`public` policy exists on any of them.
- `recovery_pulses` additionally has a `service_role`-only INSERT policy (`service_insert`) alongside the `authenticated` one — consistent with it also being written by a Telegram-bot backend, not just the UI.
- `get_advisors(type=security)` (Supabase's own linter, which specifically flags `rls_enabled_no_policy` and similar gaps) returns **zero** findings for any of these nine tables. The tables it does flag as RLS-enabled-with-zero-policies (`human_systems_feedback`, `human_systems_friction`, `human_systems_patterns`, `human_systems_recommendations`) are not read or written anywhere in this workbench (only `lib/command-centre.ts` references them) — out of scope here, noted only so it isn't mistaken for a workbench-adjacent gap.

**Conclusion: the current live RLS state for this workbench is correctly locked down.** The `physical_exercises` leak (migration 0099) is confirmed closed and does not appear to have recurred elsewhere in this domain.

### Real gap: the RLS fixes that make this true today aren't in the repo's migration files

`list_migrations` against the live project shows applied migrations named `tighten_advisory_sessions_and_health_daily_logs_rls` (2026-07-17), `tighten_physical_readiness_workout_rls` (2026-07-17), `security_phase1_enable_rls_unprotected` / `security_phase2_replace_permissive_policies` (2026-06-20), and `allow_anon_writes_activity_weight_logs` (2026-06-20, later reversed by phase 2) — these are exactly the migrations responsible for the `authenticated`-only state confirmed above. None of them exist as files under `core/infrastructure/supabase/migrations/` (`find`/`grep` across the directory and the whole repo turns up nothing matching any of those names). They were applied directly to production (dashboard SQL or an unpushed local run) and never committed.

This isn't a live problem today — the database itself is correct. It's a reproducibility/disaster-recovery problem: if this schema were ever rebuilt from the repo's migration files (a fresh environment, a declarative reset, restoring from the tracked history), the tables this workbench depends on for health data would come back in whatever state the *tracked* migrations leave them — some of which (`0068_physical_readiness.sql:24-28,60-63,86-89,117-120,145-148`) still create `physical_readiness_profiles`/`physical_exercises`/`physical_readiness_checkins`/`physical_workout_sessions`/`physical_workout_exercise_logs` with `USING (true)` policies open to any role, and `0005_captains_log_entries.sql` creates `captains_log_entries` with **no RLS at all**. The safety this review just confirmed exists only in the live database, not in version control.

### Real gap: a stale migration file that, if replayed, would silently break the Medical tab

`0091_intelligence_workbench_phase_b.sql` (repo file) has a step 6 that does `CREATE OR REPLACE VIEW analytics_health_daily AS …` with only five columns (`log_date, physical_capacity, sleep_hours, pain_score, overall_note`) — far narrower than the columns `buildMedical()`/`buildRecovery()` select from that view (`route.ts:182-184`: `sleep_quality, cpap_status, nervous_system_state, energy, movement_notes, pleasure_creativity_marker, what_happened, sitting_tolerance_minutes, workload_constraint, captain_capacity_rating`). Checked live: `information_schema.columns` for `analytics_health_daily` shows the full 34-column definition from `0082_recovery_pulses_daily_view.sql` (applied 2026-07-17) is what's actually live — the applied migration is literally named `0091_intelligence_workbench_phase_b_steps_1_5`, i.e. step 6 was deliberately not applied. So there is no live bug. But the file on disk still contains that step, undated and unmarked as skipped/superseded — a future `supabase db push` or migration replay that doesn't know to skip it would silently regress every "Sleep last night" / "Nervous system" / "Energy" field on the Recovery tab and the entire Life Participation score on the Medical tab back to "Not recorded", with no error (the Supabase client would just return `null` for the missing columns, not throw).

### Real gap: the "governed write" pattern is only 5/7 complete

`WORKBENCH-REVIEW.md C4` (2026-07-18) moved several direct-browser Supabase writes in this domain to server routes with an explicit `requireSession()` check, and the comments on `check-in/route.ts`, `pulse/route.ts`, `activity/route.ts`, `readiness/exercise-log/route.ts`, and `readiness/session/[id]/complete/route.ts` all cite it. Two write paths in this same workbench were not migrated:

- `human-systems-workbench/log/page.tsx:90-93` (Captain's Log) — direct browser `supabase.from('captains_log_entries').upsert(...)`.
- `human-systems-workbench/readiness/start/page.tsx:104-148` (readiness check-in → session generation) — direct browser inserts into `physical_readiness_checkins` and `physical_workout_sessions`.

Both are reachable only by an authenticated Captain (page-level `middleware.ts` redirects any unauthenticated request to `/login` before the page ever mounts, and the tables' own RLS — verified above — additionally rejects `anon`), so this is **not currently an exploitable gap**, just an incomplete application of the stated architecture pattern. Two concrete costs of the inconsistency: (1) no server-side input validation before the DB call, unlike the governed routes' minimal required-field checks; (2) raw Postgres error messages are surfaced straight to the UI (`log/page.tsx:97`, `readiness/start/page.tsx:122,133,152` all do `setError(dbError.message)` / `.error?.message`), which the governed routes also do (`check-in/route.ts:38`) but at least behind a server boundary rather than directly from the browser's own Postgrest client.

### Signal freshness — the registry's "live" claim doesn't match current data

The registry description leads with "live from the recovery-pulse signal." Queried live, as of 2026-08-09:

| Source | Total / recent | Latest row |
|---|---|---|
| `recovery_pulses` | 0 in last 7 days | 2026-07-26 (14 days stale) |
| `physical_workout_sessions` | 0 in last 30 days | 2026-07-07 (33 days stale) |
| `health_daily_logs` | 7 rows total | 2026-07-17 |
| `captains_log_entries` | 6 rows total | 2026-06-28 |
| `human_systems_daily` (view) | 31 rows | 2026-07-27 |

`recovery_pulses` was already documented (`0082_recovery_pulses_daily_view.sql`'s own comment) as the *only* actively-used logging surface as of mid-July, after `captains_log_entries`/`health_daily_logs` "went quiet in June." That signal has now itself gone quiet for two weeks, and the Readiness domain's underlying data is over a month old. This is not a code defect in the workbench — to its credit, the UI does not disguise this: `RecoveryView.tsx:21-26` shows an explicit "No health check-in recorded for today yet" banner rather than silently displaying stale data as current, and `ReadinessView.tsx:61-77` shows the real date of the last session (`fmtDate`) rather than hiding how old it is. The workbench is honest about staleness. But it means the registry's "live from the recovery-pulse signal" framing currently overstates what a Captain will actually see when they open this tab — there is likely a dead upstream capture pipeline (the Telegram-fed pulse bridge) behind this, consistent with other dormant-capture findings already on record for this platform (e.g. `draft_worker` cron, XO Voice Debrief). That's an ops/upstream question, not something fixable inside this workbench's own code — flagging it here because it directly undercuts the trustworthiness of what the registry tells the Captain to expect.

### Realtime wiring — verified real, not cosmetic

`page.tsx:75-90` subscribes to `recovery_pulses` (Recovery/Medical tabs) and `physical_workout_sessions` (Readiness tab) via `useRealtimeRefresh` (`lib/realtime/useRealtimeRefresh.ts`), showing a "● Live" indicator only once the channel reports `SUBSCRIBED`. Checked live: both tables are present in the `supabase_realtime` publication (`pg_publication_tables`), so the plumbing this depends on is genuinely wired, not just present in code. Given the freshness finding above, the indicator will currently spend most of its time saying "Updated HH:MM" rather than "● Live," which is accurate, not a bug.

### Test coverage

Only one of seven write endpoints has any test: `api/human-systems/check-in/__tests__/route.test.ts` (401/400/200/500 paths, well-constructed). Not covered: the main `GET /api/human-systems` route itself — which contains the only real business logic in this domain, `computeLifeParticipation`'s weighted scoring (`route.ts:115-137`: movement 0.25 / pleasure 0.2 / social 0.2 / sitting 0.2 / workload 0.15) and `computeRecoveryIndexes`'s banding (`route.ts:141-164`) — nor `pulse`, `activity`, `readiness/exercise-log`, `readiness/session/[id]/complete`, or `physical-readiness/complete`, nor any of the four view components. The route's own comment claims these functions "mirror the canonical logic in `src/lib/ros-data.ts`" — that's exactly the kind of claim that drifts silently without a test pinning the two together (the same failure mode already found once in this platform, in a different file, per the `ros-data-401-regression` memory entry).

### What's solid

- Zero mock/stub data anywhere in this workbench's read or write paths — confirmed by a direct scan for `mock|fake|hardcod|placeholder|dummy` across all five `_components` files (551 lines), none found.
- Consistent, verified-live RLS lockdown across all nine tables this workbench touches, plus `get_advisors` corroboration.
- Session-aware Supabase client used uniformly for both GET and POST — no dual-client mismatch.
- Honest degrade behavior: "no data today" and "last session was N days ago" are shown as such, never disguised as current.
- Shared single-fetch context (`loadCtx`) avoids the N-separate-queries-per-tab pattern; sensible reuse of the existing ROS-001 Posture Engine RPC and `health_insights` rather than reinventing scoring.
- Realtime refresh genuinely wired end-to-end (publication membership confirmed live), not just present in the client code.

## Recommendations

1. **P1 — Commit the RLS-tightening migrations that are currently only live, not tracked.** Write migration files reproducing the effect of `tighten_advisory_sessions_and_health_daily_logs_rls`, `tighten_physical_readiness_workout_rls`, and the `security_phase1-4` set for the tables this workbench depends on (`health_daily_logs`, `captains_log_entries`, `recovery_pulses`, `activity_logs`, `physical_readiness_checkins`, `physical_workout_sessions`, `physical_workout_exercise_logs`). Today's live data is safe; the repo's ability to reproduce that safety from a clean rebuild is not. This is the same class of gap that let `physical_exercises` sit open until an audit caught it — the fix here is to stop that from being possible for its siblings too.
2. **P2 — Fix or annotate `0091_intelligence_workbench_phase_b.sql`'s step 6.** Either delete the narrow `analytics_health_daily` redefinition (it was correctly never applied) or add an explicit comment marking it superseded by `0082` and not to be replayed. Cheap now; expensive if someone replays it during a future migration and silently regresses the Medical tab.
3. **P2 — Finish the governed-write migration.** Move `log/page.tsx`'s `captains_log_entries` upsert and `readiness/start/page.tsx`'s `physical_readiness_checkins`/`physical_workout_sessions` inserts behind server routes with `requireSession()`, matching the other five write paths in this same domain. Not an active vulnerability (RLS + middleware already cover it), but it's the same pattern the rest of this workbench already adopted, and closing it removes two remaining raw-Postgres-error-to-browser surfaces.
4. **P3 — Add route-level tests**, starting with `GET /api/human-systems` (all three domains) given it's the one place with real scoring logic, then the four untested write routes.
5. **Not an engineering fix, flagged for visibility** — the "live from the recovery-pulse signal" registry description should be checked against current data before being repeated to the Captain; the signal it names has been silent for two weeks. Worth a quick look at whatever feeds `recovery_pulses` (Telegram bridge, per the schema comments) to confirm whether that's a known pause or a quietly-dead job.

## Next Actions

Immediate, concrete: #1 and #2 are the two items with real (if currently dormant) blast radius — both are migration-file changes only, no live schema change required, and directly close the gap this review was specifically asked to re-check. I have not made any code or migration changes; this is Advisory only per my authority. #5 is a routing note, not an engineering task — Chief Engineer doesn't own the upstream capture pipeline; flagging so whoever does can look.

## Mission Status

Advisory only. No live security-severity finding — RLS is correctly locked down today, verified directly against production, not assumed from comments. The finding worth escalating clearly rather than burying: the *safety* of that live state is not currently reproducible from the repo's own migration history (#1), which is exactly the kind of gap that turns into a real incident the next time someone rebuilds this schema from what's tracked. Registry description: code is trustworthy; the "live" framing is presently ahead of what the underlying data actually shows.
