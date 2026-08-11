# Captain's Chair fix — 2026-08-09

**Attestation:** Chief Engineer persona (USS-TJR-003, Advisory authority), routine web-app bug fix, no security/destructive action.

## Problem

`lcars-portal/src/app/api/captain-intelligence/generate/route.ts` (MSN-0329 Phase 5, "Generate New Insights" action on Captain's Chair) shelled out via `execFile('python3', ['-m', 'core.platform.captain_brief_cli', '--evolved', ...])`. Vercel's Node.js serverless runtime has no `python3` binary and cannot spawn arbitrary child processes, so this route was broken in production — clicking "Generate New Insights" almost certainly failed every time it was deployed.

## Prior fix found (the pattern to mirror)

Commit `3386940` (2026-07-10, "fix(starship): replace broken python3 subprocess bridge with an HTTP service") hit and fixed the identical problem for two sibling routes:

- `lcars-portal/src/app/api/captain-brief/route.ts`
- `lcars-portal/src/app/api/recommendations/route.ts`

Both used to `execFile` a local Python CLI; both were switched to `fetch()` against `core/context-assembly/context_service.py`'s Flask HTTP service (`GET /brief/full`, `GET /recommendations/full`), reusing the same underlying assembly functions verbatim. Shared config lives in `lcars-portal/src/lib/contextService.ts` (`contextServiceUrl()` / `contextServiceHeaders()`, `CONTEXT_SERVICE_URL` + `CONTEXT_SERVICE_SECRET`). The service runs under `deploy/context-service.service`, bound to `127.0.0.1:5001`, fronted by Caddy in production.

The commit note flagged that the fix "is not yet deployed" pending VM access (systemd install, Caddy route, Vercel env var) — those steps are outside this repo and were not re-verified this pass.

## Fix applied

Found the equivalent fix **already present, uncommitted, in the working tree** when this task started — apparently done by a concurrent/prior session working the same problem (near-identical to the change I was about to make independently). Verified it rather than re-doing it or overwriting it:

1. **`core/context-assembly/context_service.py`** — added `POST /brief/evolved`, calling `assemble_evolved_captain_brief(poll_events(limit))` from `core.platform.captain_brief_evolution` (the exact function `captain_brief_cli.py --evolved` called), returned via the same `dataclasses.asdict(..., dict_factory=_str_default_asdict)` pattern `/brief/full` already uses. Kept as `POST` (matching the Next.js route's own reasoning: this triggers real LLM calls and persists to `insight_outcomes` on every call — a side effect, not an idempotent read). Also added `threaded=True` to the dev server's `flask_app.run(...)` — `/brief/evolved` runs 50-260s per the MSN-0329 Phase 3 measured latency; without threading, one in-flight evolved call would stall every other route on the service, including `/health` and `/brief/full`, which Captain's Chair polls on every page load.

2. **`lcars-portal/src/app/api/captain-intelligence/generate/route.ts`** — replaced the `execFile('python3', ...)` call with `fetch(`${contextServiceUrl()}/brief/evolved?limit=200`, { method: 'POST', headers: contextServiceHeaders(), signal: AbortSignal.timeout(290000) })`, using the same shared `lib/contextService.ts` helpers the sibling routes use. Kept the existing 290s client-side timeout ceiling (just under the model router's 300s server-side `TASK_POLICY` timeout). Response shape unchanged (`{ insights, recommendations }` parsed from the returned document) — no downstream consumers needed to change.

No new backend infrastructure was needed: `context_service.py` already runs as a persistent Flask process with the auth/secret pattern in place; this only added one route to it.

## Verification

- `python3 -m py_compile core/context-assembly/context_service.py` — clean.
- `npx tsc --noEmit` (lcars-portal) — clean, no errors.
- `npx eslint src/app/api/captain-intelligence/generate/route.ts` — clean.
- Confirmed no remaining `execFile`/subprocess `python3` calls anywhere in `lcars-portal/src/` (grep) — only historical comments referencing the old pattern remain, in this file and the two sibling routes' own header comments.
- No dedicated test file exists for this specific route; did not run the full vitest suite this pass.

## Not addressed (disclosed, matches the 2026-07-10 fix's own caveat)

- Whether `deploy/context-service.service` is actually running on the target VM with the new endpoint live, whether Caddy is routing to it publicly, and whether `CONTEXT_SERVICE_URL`/`CONTEXT_SERVICE_SECRET` are set correctly in Vercel's project env vars were **not re-verified this pass** — this repo has no SSH access to the VM. If the underlying service isn't actually running/reachable in production, this route will now fail with a clean `502` (`Failed to reach the Captain Brief service`) instead of the previous subprocess-spawn failure — a real improvement (honest error vs. silent failure) but not proof the feature works end-to-end in production.
- Unrelated pending changes were found sitting uncommitted in the same working tree during this task (RLS-tightening migrations, `telegram-bots/xo/app.py`, a workbench-review doc) — left untouched and **not** included in this commit; they belong to other in-flight work, not this fix.

## Files touched

- `/opt/starship-endeavour/core/context-assembly/context_service.py`
- `/opt/starship-endeavour/lcars-portal/src/app/api/captain-intelligence/generate/route.ts`

**Mission Status:** Fix applied and verified (compile-clean). Advisory-only assessment of production reachability — needs VM/Vercel-side confirmation from someone with access, not re-verifiable from this repo alone.
