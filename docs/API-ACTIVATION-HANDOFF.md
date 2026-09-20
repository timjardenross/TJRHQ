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
