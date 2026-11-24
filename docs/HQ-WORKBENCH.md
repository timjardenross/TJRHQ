# HQ Workbench (`/hq`)

A separate, parallel presentation layer over existing capabilities. It does not replace, redirect or modify
any existing workbench, route, API, table or approval mechanism. Default landing is unchanged.

## Switching it on and off

- `HQ_WORKBENCH_ENABLED` (server-side environment variable, **default off**). Accepted on-values:
  `1`, `true`, `yes`, `on`. Anything else, or unset, is off.
- Off: every `/hq/*` route returns the standard 404. Nothing else reads the flag.
- The `/hq` layout is `force-dynamic`: the flag is read per request, so changing it needs no rebuild.
- The existing workbench header shows an `HQ` link only when the flag is on (it asks `GET /api/hq/status`; any failure means no link).
- Authentication is inherited from `src/middleware.ts` (every non-public path needs a signed-in session).
- Rollback is unsetting the variable.

## What it is made of

| Place | Reads from (existing) | Writes through (existing) |
|---|---|---|
| Home | `/api/briefs`, `buildNeedsYouItems` inputs (emergency, briefing, Number One, content, capture, HQ status), missions | none |
| Intelligence | `/api/intelligence-workbench/{today,watching}`, `/api/emergency-alerts`, `/api/health-osint/today`, `/api/briefs[/id]` | brief gate via `/api/intelligence-workbench/action`; "Start mission" via capture + `promote-mission` |
| Decisions | `fetchDecideQueue`, `/api/briefs`, `/api/knowledge-library/documents`, `/api/self-improvement/opportunities` | `approveDecideItem` / `holdDecideItem` / `undoDecideItem`, the approve-action route, brief gate, knowledge `decide`, improvements `decide` |
| Work | `/api/missions`, `/api/engineering-handoffs` | none (status changes stay in Missions) |
| Library | `/api/knowledge-library/{documents,memory}`, `/api/intelligence-workbench/library`, `/api/briefs`, `/api/content-workbench` | none |
| New | existing capture pipeline (`captureItem`, `promoteCaptureToMission`) | capture / mission candidate |
| System | `/api/agent-status-workbench/overview` | none (repairs stay in HQ Status) |

HQ owns no table and stores no record. The code is in `src/app/hq/` and `src/lib/hq/`.

## One decision, one effect

Where HQ and an existing workbench act on the same item:

- **Build requests (server-side).** `POST /api/hq/decisions/build-request/[id]` applies approve, decline or undo as ONE
  conditional `UPDATE ... WHERE status = <status the caller saw>`, which the database applies atomically: of two
  concurrent requests exactly one changes the row and the other gets 409. Approve is restricted to plain build requests
  (`action_type IS NULL`); an AI-proposed action must go through `approve-action`, which executes it. The route is
  flag-gated (404 off), requires a session, and writes the audit trail and the existing `decide_ledger`.
- **AI proposals:** approved through the existing `approve-action` route (409 unless `awaiting_review`).
- **Brief gate:** HQ re-reads the brief and never publishes unless it is still `QA_PASSED`.
- **Knowledge review:** the route returns 409 once decided. **Improvements:** HQ re-checks `proposed` just before deciding.
- A second click on the same item inside HQ is ignored while the first is in flight.

## Existing safety gaps that materially affect HQ (recorded, not changed here)

1. The existing `/decisions` page still updates `build_request_inbox` straight from the browser with no status check,
   so it can overwrite a decision HQ just made. Closing this needs a database-level rule (a trigger or policy that
   refuses a status change out of a decided state). That is a migration and needs approval.
2. `approve-action` reads the row, executes, then marks it approved. Two simultaneous approvals could both execute
   (two missions). Fix: claim the row atomically before executing.
3. Publishing a brief that is already published is a silent no-op upstream that re-sends the publish notification.
   Owned by the Intelligence workflow.
4. The improvements `decide` route has no state guard: it re-decides freely.
5. `promote-mission` has no guard against promoting the same capture twice. HQ promotes a capture it has just created,
   once, and disables the control after the first click, but another caller could still duplicate.

## Research

HQ can only **capture a research request** (an item in Capture marked "Research request:"). Nothing executes it: no
research runner exists. HQ lists captured requests in Work under "not running" and never shows a running state.

## Capability status

See `docs/HQ-CAPABILITY-CHECKLIST.md`, the single record of what is Operational, Partial or Outstanding.

## Tests

`npx vitest run src/lib/hq src/app/hq src/app/api/hq src/components src/lib/__tests__/decide.test.ts` covers the flag, vocabulary,
adapters, the server decision route, the double-approval guards, the contextual actions, research labelling, the switcher
entry and the dialog focus trap. The full suite also passes.
