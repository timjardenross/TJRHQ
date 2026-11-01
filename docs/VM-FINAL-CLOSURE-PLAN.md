# VM Handoff — Final Immediate-Item Closure

This document covers the remaining backend/API work required to close the
USSTJR immediate UI/UX remediation list. Do not place passwords, tokens, or
Infisical secrets in this file, shell history, logs, or committed code.

## Current portal state

The portal already contains:

- Four shared data states: `empty`, `no-action`, `unavailable`, `stale`.
- One-primary-action registry enforcement for every live workbench.
- Search and Timeline attention filters using structured UI fields rather than
  arbitrary prose matching.
- Evidence metadata on Search and Timeline summaries and key detail routes.
- HQ Status recovery mappings for every declared capability.
- Server-backed `/api/action-history` and UI outcome recording.
- Explicit Engineering Handoff queue handling (`review`, `delivery`, `blocked`).
- Incomplete-source messaging on the major aggregate workbenches.
- Authenticated route and keyboard smoke checks completed locally.

## VM/API work still required

### 1. Persist the command model

Add explicit fields to the canonical backend read models or API response
contracts. The minimum fields are:

```text
attention_state: needs-action | normal
importance: important | normal
owner: string | null
freshness_state: current | stale | unavailable
source: string | null
observed_at: timestamptz | null
```

Apply these fields to the records consumed by Search and Timeline. Do not
derive attention or importance from title/detail keyword matching.

Required acceptance checks:

- Search `Needs action` returns only records with explicit
  `attention_state = needs-action`.
- Search `Important only` returns only records with explicit
  `importance = important`.
- Timeline uses the same fields and produces the same result for the same
  record.
- Unknown/null metadata is shown as normal or unknown, never promoted to
  urgent by inference.
- RLS and authenticated access remain unchanged and are tested.

### 2. Complete server-backed action history

Audit every consequential mutation endpoint used by the portal. Each must
append to `audit_events` through the authenticated action-history contract:

```text
category: user_action
actor: authenticated user/service identity
action: stable action name
outcome: in-progress | success | failed | cancelled
details: structured JSON including record/workbench identifiers
mission_id: optional
```

Prioritise mutations for:

- Ready Room task state changes
- Mission state changes
- Emergency alert silences
- Shopping List create/update/delete/reorder
- Content research, draft, QA, approval, scheduling, and publishing
- Advisory decisions and outcomes
- Knowledge triage and document decisions
- Intelligence escalation/watch actions
- HQ Evolution decisions
- Engineering handoff state changes

Required acceptance checks:

- Successful mutation creates exactly one audit row.
- Failed mutation creates a failed outcome where the request reached the
  mutation boundary.
- Audit details contain a stable record identifier and workbench name.
- No secrets or full user-entered sensitive text are written to details.
- Repeated retries are distinguishable by timestamp/request identifier.
- Existing RLS/service-role behaviour is preserved.

### 3. Complete EvidenceMeta source coverage

For every data-bearing summary and detail response consumed by the portal,
return real values for source, observed time, confidence/coverage, and state
where available. Do not fabricate timestamps or confidence values.

Priority routes:

- Hub and Captain’s Chair aggregate cards
- Weekly Review synthesis sections
- Emergency Alerts and source coverage
- Human Systems capacity/recovery summaries
- Physical Readiness history/readiness records
- Shopping List externally sourced or synchronised records
- Content Workbench research and QA evidence
- Advisory outputs
- Knowledge document/memory detail
- HQ Status capability and source rows
- HQ Evolution findings
- Engineering Handoffs artifacts and status

Required acceptance checks:

- Every material claim has a nearby source and observed time.
- Unavailable sources use `unavailable`, not an empty-state message.
- Old but present sources use `stale`.
- No-action is used only when the source is available and no action is
  required.
- The portal route audit has no uncovered data-bearing detail route.

### 4. Enforce the four states at API boundaries

Where APIs currently return ad hoc `error`, `loading`, or empty payloads,
normalise the response or adapter to one of the shared states. Preserve the
actual error detail for diagnostics, but expose a user-safe recovery action.

Required acceptance checks:

- Empty data is not reported as unavailable.
- Failed source is not reported as no action.
- Stale source includes freshness age or last observed timestamp.
- Aggregate responses identify which source/workbench is affected.

## Deployment and verification sequence

1. Apply schema/API changes in a migration or reviewed backend deployment.
2. Run Supabase security/RLS checks and confirm authenticated access.
3. Rebuild the portal with production Infisical environment injection.
4. Restart the service to avoid stale `.next` output.
5. Run typecheck, unit tests, and production build.
6. Run authenticated route checks for the protected workbenches.
7. Run keyboard-only checks for Captain’s Chair, Hub, Ready Room, Search,
   Timeline, and Emergency Alerts.
8. Verify Search/Timeline attention filters against records with explicit
   metadata.
9. Verify action-history rows for one successful and one failed mutation per
   priority domain.
10. Confirm no credentials, tokens, or secret values appear in build logs,
    browser URLs, audit details, or Git history.

## Evidence to return from the VM

Return:

- deployed commit SHA
- migration names and status
- API contract/schema diff summary
- typecheck/test/build results
- authenticated route results
- keyboard smoke results
- action-history sample counts by domain (identifiers redacted)
- Search/Timeline metadata filter results
- any remaining blocked item with the exact dependency

Do not report these items complete based only on a successful build. They are
complete only when backend data, authenticated UI, and audit evidence agree.
