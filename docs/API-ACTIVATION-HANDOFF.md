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
