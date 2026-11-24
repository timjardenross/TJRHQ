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
| Work | `/api/missions`, `/api/engineering-handoffs`, capture inbox, mission changes and execution events | capture inbox actions (existing capture functions); status changes stay in Missions |
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

## Shared decision integrity

Enforced in the shared backend, not only in HQ:

1. **Database (migration 0261, written and tested, NOT applied).** A trigger on `build_request_inbox` refuses
   `approved -> rejected` and `rejected -> approved` (case-insensitive). Every valid transition stays legal:
   decide from awaiting/pending, Undo (`approved -> awaiting_review`), engineering lifecycle statuses, updates that
   leave status unchanged, and inserts. To change a decision, undo first. Tested on a local Postgres
   (`tests/test_build_request_decision_guard.py`). Rollback is in the file header. Applying it is a production change.
2. **AI proposals.** `approve-action` claims the row with one conditional update before executing, so simultaneous
   approvals execute once (the loser gets 409 and nothing runs). A recorded failure or a claim older than 5 minutes can
   be retried. No schema change: the claim lives in `action_result`.
3. **Improvements.** The decide handler (`scripts/self_improvement/dashboard.py`) serialises read-check-write with a lock,
   treats a repeat as an idempotent no-op (200, `unchanged`), and refuses contradicting or regressing decisions (409).
   Every transition the portal uses stays legal. It takes effect when the service is restarted.
4. **Build requests via HQ.** The server route applies each decision as one conditional update (see above).

Still open, owned elsewhere:

- **Brief re-publication.** Publishing an already-published brief is a silent no-op upstream that re-sends the publish
  notification. The fix belongs in the Intelligence workflow (`intelligence/workflow`): a repeat publish should return
  without notifying. To be agreed with the Intelligence agent; HQ already refuses to publish a brief that is not QA-passed.
- `promote-mission` (Command Centre, outside this repo) has no guard against promoting one capture twice. HQ marks a
  capture reviewed after promoting it and disables the control, but another caller could still duplicate.

## Intelligence item to decision

A person explicitly asks for a decision on one intelligence item. `POST /api/hq/decisions/request` creates ONE
`build_request_inbox` row through the existing `proposeAction()` (action_type `log_decision`, source
`hq-intelligence-decision-request`). The request id is derived from the item and `request_id` is UNIQUE, so one item
can only ever have one request; a repeat returns the existing one. The payload keeps the original item (id, title, link,
lens), the reason, 2 to 5 options, an optional recommendation (blank means "no recommendation", shown as unknown) and
the evidence. Approving records the chosen option as a decision through the existing `logDecision`; it does not start
any work. Nothing creates requests automatically.

## Ask

Retrieval over HQ data first (`lib/ask.ts`, no model). Otherwise the existing AI Console (`POST /api/ai/chat`, role
`general`, streaming), which has its own personal-health veto and queues any proposed action for approval in Decisions.
Advice mode uses the existing Advisory service. HQ sends no system prompt, model, local-only role or personal data, and
adds no AI backend or context store. It needs the AI Console switched on in the environment (otherwise HQ says Ask is
unavailable). The AI Console's context covers missions, decisions, the build queue and knowledge titles, not intelligence
feeds; retrieval covers intelligence, briefs and lessons.

## Research

Research is a type of work: a mission created through the existing missions API with the title prefix `Research:` and
status `Idea`. Work shows it with the mission's real status. No research runner reads research missions (the one live
mission dispatcher turns approved missions into code-change hand-offs, which is wrong for research), so a new item reads
"Requested, not running", and HQ never shows "running" or "findings ready" unless a status on the mission says so.
A worker that executes research missions would be new infrastructure and has not been built.

## Capability status

See `docs/HQ-CAPABILITY-CHECKLIST.md`, the single record of what is Operational, Partial or Outstanding.

## Tests

`npx vitest run src/lib/hq src/app/hq src/app/api/hq src/components src/lib/__tests__/decide.test.ts` covers the flag, vocabulary,
adapters, the server decision route, the double-approval guards, the contextual actions, research labelling, the switcher
entry and the dialog focus trap. The full suite also passes.
