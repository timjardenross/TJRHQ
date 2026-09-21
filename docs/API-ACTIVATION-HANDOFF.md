# TJR HQ — API Activation Handoff

This document is the boundary between the completed portal UI and the VM-side API activation work. The portal keeps its existing Supabase and API connection methods; Claude CLI on the VM can activate or repair the upstream services without redesigning the frontend.

## Portal readiness

- All operational workbench routes are present and use the Endeavour 27 dark command system.
- Loading, unavailable and degraded states are rendered without implying that missing data means “nothing changed”.
- Affected-data notices link to `/agent-status-workbench` for operational follow-through.
- No API route, Supabase client, authentication flow or connection method was replaced by the visual/capability pass.
- Production build and typecheck must remain green after VM-side activation.

## Activation queue observed locally

These endpoints returned upstream failures during the authenticated local sweep. They are activation/configuration targets, not frontend redesign targets:

| Surface | Endpoint or dependency | Expected activation check |
|---|---|---|
| LifeOS Hub | `/api/calendar/today` | Calendar credentials, callback and read scope; return a governed empty state when no events exist |
| LifeOS Hub | `/api/calendar/upcoming` | Same calendar connection; verify the `days` parameter and stale handling |
| LifeOS Hub / Mission Workbench | `/api/captain-brief` | Brief provider/service reachable; return structured `warnings` and `interruptNow` fields |
| Weekly Review | `/api/health-adjusted-queue` | Health data service and permissions; preserve fail-closed semantics |
| Weekly Review | `/api/number-one-brief` | Number One service reachable; return a typed empty result when no item is ready |
| Advisory | `/api/recommendations` | Recommendation service/API key and timeout; do not fabricate recommendations on failure |
| Engineering Handoffs | `/api/self-improvement/findings` | HQ Evolution data source and auth; verify read permissions |
| Engineering Handoffs | `/api/self-improvement/opportunities` | HQ Evolution opportunity source and auth; verify read permissions |

## VM activation checklist

1. Confirm production environment variables exist in the VM/Vercel target without printing secret values.
2. Confirm Supabase migrations, RLS policies and authenticated-user access are current.
3. Activate one upstream integration at a time and record its health response.
4. Verify the API returns the documented shape, including explicit empty and unavailable states.
5. Run authenticated browser smoke tests for Hub, Captain’s Chair, Mission Workbench, Weekly Review, Advisory and Engineering Handoffs.
6. Run `npm run typecheck`, `npm run test`, `npm run build`.
7. Only then promote a deployment.

## Deferred VM implementation — Shopping List saved views

The portal UI may expose saved-view affordances, but persistence must be completed server-side before this capability is treated as production-ready.

Claude CLI on the VM is to:

1. Define the authenticated saved-view contract for Shopping List: create, rename, update filters/sort, select, duplicate, and delete.
2. Persist views in Supabase with an owner/user key, stable identifier, display name, filter payload, sort payload, default-view flag, and created/updated timestamps.
3. Add RLS so a user can only read and mutate their own views; do not use localStorage as the source of truth.
4. Add the existing API boundary for list/create/update/delete operations, preserving the portal's current Supabase/auth connection method and returning typed `ok`, `data`, `empty`, and `unavailable` outcomes.
5. Make the selected view reload-safe and validate malformed or obsolete filter payloads without silently falling back to a misleading result.
6. Add regression coverage for ownership isolation, CRUD, default selection, unavailable backend, and stale/invalid view state.
7. Run the authenticated Shopping List smoke test, `npm run typecheck`, `npm test`, and `npm run build`; record the endpoint status and migration/RLS revision in the completion report.

This item remains **deferred / not activated** until the migration, RLS policies, API contract, and authenticated smoke test are complete. Do not mark it healthy based on a client-only or localStorage implementation.

## Delivered bundle status — navigation and workflow improvements

The following items were delivered in commit `c81a279` on `main`:

| Item | Status | Evidence / handoff condition |
|---|---|---|
| Reduce the 21-workbench navigation model to four family-level entry points | Implemented | `/workbenches` family navigation is in the local bundle; verify route reachability after deployment. |
| Canonical “What needs me now” pattern for Hub, Captain’s Chair, Ready Room, and Briefs | Implemented | Shared component is integrated across all four surfaces; run authenticated smoke checks after deployment. |
| Separate action-required, watch, informational, stale, and unavailable states | Implemented locally | Semantic regions and state markers are present; verify populated, stale, and failed-source states with real data. |
| End-to-end screen-reader and zoom testing | Partially verified locally | Local accessibility-tree and browser zoom checks passed, plus regression contracts. VM must run the full authenticated six-flow screen-reader/zoom sweep and record results. |
| Explicit lifecycle filters: blocked, overdue, stale, awaiting-owner | Implemented locally | Shared contract is used by Search and Timeline; verify real records expose each state before production sign-off. |
| Standard action outcome, retry, undo, and recovery patterns | Implemented locally | Shared outcome component and retry/recovery affordances are present; VM must verify consequential actions against server-backed history. |
| Server-backed saved views for Shopping List | Deferred to VM | Complete the migration, RLS, API, reload safety, and authenticated smoke test in the section above. |
| Progressive disclosure for dense OSINT and Human Systems views | Implemented | Review queues, capacity trends, recovery trajectory, medical details, and pattern details use accessible disclosures. |

The UI and automated verification gates passed before the push: full suite `71 files / 731 tests`, typecheck, diff validation, and production build. Do not treat the partially verified accessibility item or deferred Shopping List item as production-complete until the VM checks below pass.

## VM verification for delivered workflow improvements

After deploying commit `c81a279`, Claude CLI on the VM must:

1. Confirm task telemetry writes authenticated `task_started`, `task_completed`, and retry events to the existing server-backed action-history path, including viewport and coarse-pointer context; do not log content or credentials.
2. Run six high-risk mobile workflows and report start, completion, retry, abandonment, and time-to-completion observations from the server history.
3. Keyboard-tab through the global shell on desktop and mobile/tablet widths: skip link, home, settings, workbench/family switcher, tabs, back link, primary action, mobile Command Bar, More sheet, Quick Capture, and Number One.
4. Confirm client-side navigation places focus on `#wb-main`, the new page heading/content is announced, no control disappears with focus, and focus-visible indicators remain visible at 200% zoom.
5. Complete the full authenticated screen-reader/zoom sweep and record route, viewport, browser/reader, result, and any remediation.

## Safety boundary

Do not add service-role keys to client bundles, replace existing adapters with mock data, or convert an upstream failure into a reassuring “clear” state. The portal is designed to remain useful and honest while the VM activates the real services.

## VM execution runbook

Run this after the GitHub commit has been deployed to the target environment. Work from the repository root and keep a timestamped activation log. Never paste secret values into the log or terminal transcript.

### 1. Preflight

```bash
git fetch origin
git checkout main
git pull --ff-only origin main
cd lcars-portal
node --version
npm --version
```

Confirm the checked-out revision is `f4f75b6` or a later `main` revision. Confirm the expected production environment variables are present by checking names only; do not print values. The VM must use the existing `.env`/Vercel environment configuration and existing adapters.

### 2. Validate the deployed application

Check the deployment URL first:

```bash
curl -fsS "$PORTAL_URL/login" >/dev/null
```

Then authenticate through the browser test flow and check these routes:

```text
/hub
/captains-chair-workbench
/mission-workbench
/weekly-review
/advisory-workbench
/engineering-handoffs
/agent-status-workbench
```

For each route verify: the page loads, the heading is present, no horizontal overflow is introduced, unavailable upstream data is labelled honestly, and actions do not silently succeed when their API is unavailable.

### 3. Activate and verify integrations

Use the existing API routes in this order so failures are isolated:

1. Calendar: `/api/calendar/today`, then `/api/calendar/upcoming`.
2. Captain’s Brief: `/api/captain-brief`.
3. Weekly Review dependencies: `/api/health-adjusted-queue`, then `/api/number-one-brief`.
4. Advisory recommendations: `/api/recommendations`.
5. HQ Evolution: `/api/self-improvement/findings`, then `/api/self-improvement/opportunities`.

For every endpoint record only: HTTP status, latency, response shape, and whether the result is populated, explicitly empty, degraded, or unavailable. Do not record tokens, cookies, personal data, or full payloads.

An endpoint is considered healthy only when it returns its expected typed shape using real upstream data or an explicit governed empty result. HTTP success with fabricated, stale, or missing required fields is not healthy.

### 4. Repair rules

- If credentials or permissions are missing, repair the VM/Vercel environment configuration and retry; do not alter the frontend connection method.
- If Supabase access fails, inspect URL, anon-key configuration, authentication session, RLS, and migrations in that order.
- If an upstream provider times out, preserve the existing timeout and fail-closed behavior; do not substitute fixture data.
- If an API shape differs from the portal contract, fix the adapter or upstream response at the existing boundary and add a regression test.
- If a migration or RLS change is required, review it separately before applying it to production.

### 5. Final gates

From `lcars-portal`, run:

```bash
npm run typecheck
npm test
npm run build
```

The handoff is complete only when all three commands pass, the seven routes above have been smoke-tested with the authenticated account, and each activation target has a recorded status. If any target remains unavailable, leave it unavailable and report the exact endpoint and dependency; do not mark it healthy.

### 6. Completion report

Return a short report containing:

- deployed commit and deployment URL;
- each activation target with status: healthy, explicitly empty, degraded, or unavailable;
- any environment, permission, migration, or provider changes made;
- typecheck/test/build results;
- remaining blockers and the exact next action.
