# HQ Workbench (`/hq`)

A separate, parallel presentation layer over existing capabilities. It does not replace, redirect or modify
any existing workbench, route, API, table or approval mechanism. Default landing is unchanged.

## Switching it on and off

- `HQ_WORKBENCH_ENABLED` (server-side environment variable, **default off**). Accepted on-values:
  `1`, `true`, `yes`, `on`. Anything else, or unset, is off.
- Off: every `/hq/*` route returns the standard 404. Nothing else reads the flag.
- The `/hq` layout is `force-dynamic`: the flag is read per request, so changing it needs no rebuild.
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

Where HQ and an existing workbench act on the same item, HQ re-checks the item's state first:

- Build requests: `approveDecideItem(item, { guardStatus: true })` and `setQueueItemStatus(..., expectedStatus)` apply the
  change only if the row is still in the status HQ loaded (compare-and-set). Both parameters are optional and
  off by default, so every existing caller makes exactly the same call as before. AI-proposed actions are
  already guarded server-side (409 unless `awaiting_review`).
- Brief gate: HQ re-reads the brief and never publishes unless it is still `QA_PASSED` (a repeat publish upstream is a
  silent no-op that would re-send the notification).
- Knowledge review: the route returns 409 once decided. Improvements: HQ re-checks `proposed` immediately before deciding.
- A second click on the same item inside HQ is ignored while the first is in flight.

Known gap, not changed here: the existing Decisions page and the Improvements route can still re-decide an
item without a state check. HQ does not make them stricter.

## Not yet operational (shown as such in the UI)

| Capability | State |
|---|---|
| Ask a question (New) | Not connected. No safe existing service. Control is shown disabled. |
| Start research (New) | Filed as a research request in Capture for review. No automatic research runner exists. |
| Incident clustering, provider disruption, systemic view, forward watch, source coverage | Depend on open PRs #711, #712, #713. Isolated in `src/lib/hq/intelDependencies.ts`; flip `connected` when merged. |
| Intelligence to a new decision ("Ask me to decide") | Not built. No governed way to add an item to the decision inbox exists. |
| Mission deliverables / outputs | Missions do not record outputs. Engineering hand-offs show PR and artifact links. |
| Status changes on missions, repairs on sources | Stay in Missions / HQ Status so there is one place that records them. |
| Optional entry in the existing workbench switcher | Not added. It would need the flag plumbed into the shared client list. |
| Personal health, Pain Recovery Studio, personal tasks | Deliberately absent (TJR Life boundary). Home drops Number One's personal-task items. |

## Tests

`npx vitest run src/lib/hq src/app/hq src/lib/__tests__/decide.test.ts` covers the flag, vocabulary, adapters, the
double-approval guards, the contextual actions and the dialog focus trap. The full suite also passes.
