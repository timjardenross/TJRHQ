# WP-01 — API Security & Credential Protection

**Status:** DRAFT FOR OWNER APPROVAL — NOT AUTHORIZED FOR EXECUTION  
**Baseline:** [PR #611](https://github.com/timjardenross/TJRHQ/pull/611) (`014ba427a`)  
**Evidence:** [PR #610](https://github.com/timjardenross/TJRHQ/pull/610) (`e61abcffc5b01cf9875697e27acd3e907d7a21d8`)

## Background

The four-agent investigation reported unauthenticated disclosure of a Command Centre API key, query-string credential acceptance, Infisical machine credentials in process arguments and a Redis credential disclosed during diagnostics. Firewall restrictions reduce external exposure of the key-disclosure endpoint but do not enforce authorization for local callers. This document proposes future remediation without authorizing it.

## Findings and confidence

| ID | Finding | Confidence | Priority |
|---|---|---|---|
| WP01-01 | `app.js:81,106–108`: `/api/config` is auth-exempt and returns API key with `/api/v1` write capability | VERIFIED in reported code review | Critical |
| WP01-02 | `app.js:88`: API key accepted via query parameter | VERIFIED in reported code review | High |
| WP01-03 | `lib-infisical.sh:60–62`: client secret passed as process argument | VERIFIED in reported code review | High |
| WP01-04 | SEC-DR-01: Redis password exposed in diagnostic output | VERIFIED recorded event | High |
| WP01-05 | SEC-DR-02: Coolify `.env` copies mode 0644 under directory mode 0700 | VERIFIED recorded permissions | Context-dependent |
| WP01-06 | Independent custody of Infisical/recovery secrets | UNKNOWN | High dependency |

**Existing future-action references:** FA-01 (key disclosure), FA-18 (credential custody), FA-19 (Redis credential response), as reported. Validate the full mapping against PR #610 before publishing; do not invent action IDs.

## Requirements (MoSCoW)

### Must
- Never return reusable API credentials to unauthenticated clients.
- Require authenticated, owner-authorized server-side checks for every mutation.
- Remove URL-query credential acceptance after legitimate callers are migrated.
- Keep credentials out of process arguments, logs, responses and PR evidence.
- Preserve legitimate owner access and provide tested rollback and negative authorization tests.
- Require explicit owner approval for any credential rotation or production action.

### Should
- Inventory consumers, scopes, storage and recovery dependencies without reading credential values.
- Record access-denied events without sensitive payloads.
- Minimize scope and lifetime of privileged credentials.

### Could
- Introduce narrower service credentials where the current application supports them.

### Won't
- Replace the identity platform wholesale or redesign deployment governance (WP-02).
- Execute changes as part of this documentation task.

## Proposed method

### API boundary

**Target contract, subject to validation against real callers:**

- `GET /api/config`: non-secret UI configuration only; no API key or token.
- Authenticated identity/session endpoint, **only if required by existing architecture**: non-secret identity and capability information.
- `/api/v1` mutation routes: validate identity and operation-specific owner permission server-side.
- Return `401` for missing/invalid authentication and `403` for insufficient authorization.
- Reject API keys supplied via URL query parameters after migration.
- Do not treat localhost, firewall rules or Caddy alone as authorization.

```mermaid
flowchart TD
    A[Incoming API request] --> B{Authenticated?}
    B -- No --> C[401; no secret]
    B -- Yes --> D{Owner authorized for operation?}
    D -- No --> E[403; redact audit event]
    D -- Yes --> F[Execute permitted operation]
    F --> G[Non-secret response]
```

### Secret handling

- Enumerate clients using `/api/config`, `/api/v1` and query-string keys before choosing the replacement flow.
- Use an existing supported header/session mechanism, with application-level authorization.
- For Infisical, verify the **installed CLI version and official supported secret-input mechanisms** before choosing a non-argv approach. Do not invent flags.
- Maintain a **metadata-only** inventory: credential purpose, consumer, scope, storage location class, rotation dependencies and recovery custodian. Never capture values, hashes, environment dumps or token fragments.
- Treat Redis credential validity as UNKNOWN until an owner-approved non-disclosing check. Any rotation requires separate approval, coordinated client updates and rollback.
- Assess historical logs and encrypted backups as possible locations of previously exposed credentials, without accessing or publishing values.

## Proposed implementation stages — NOT AUTHORIZED

| Stage | Deliverable | Gate |
|---|---|---|
| A | Read-only caller inventory and auth-flow map | Scope confirmed |
| B | Detailed API contract and migration design | Owner design approval |
| C | Isolated code changes and unit/integration tests | Separate implementation approval |
| D | Secret transport changes | Supported CLI/API confirmed |
| E | Redis incident disposition and rotation plan | Separate owner decision |
| F | Controlled deployment and monitoring | Explicit production approval |
| G | Redacted acceptance evidence | Independent review |

## Acceptance criteria

1. Anonymous `/api/config` never returns reusable credentials.
2. Anonymous, invalid-credential and non-owner mutation attempts fail across all supported entry points.
3. Legitimate owner and service clients continue to work.
4. URL query-string API keys are rejected after migration; request logs contain no credentials.
5. Infisical secret is absent from process arguments in controlled testing.
6. Source diffs, CI output, test fixtures and diagnostic logs contain no credential values.
7. Redis exposure disposition and recovery credential custody are explicitly recorded, with UNKNOWN preserved until verified.
8. Rollback does not silently reinstate unauthenticated key disclosure.
9. Relevant CI and controlled verification pass before production acceptance.

## Dependencies and risks

- **WP-02:** owner identity, role checks, Supabase service-role boundary, LCARS and messaging authorization.
- **WP-03:** reliable alerting without logging secrets.
- **WP-04:** recovery custody and consequences of credential rotation.
- **Compatibility:** removing `/api/config` key before migrating consumers could break authorized clients.
- **Live exposure:** external reachability is constrained by reported firewall state, not independently reverified here.


## Approval-ready implementation package

This section converts the planning draft into an implementation decision package. It is still design-only; no code, credential, deployment or production action is authorized.

### Validated source references

The cited production commit is `9b7e35c9c7469215e98641685951a5dc34eec81b`.

- [`app.js:81`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/core/command-centre/backend/app.js#L81) leaves `/api/config` outside authentication.
- [`app.js:88-89`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/core/command-centre/backend/app.js#L88-L89) accepts either the `x-api-key` header or `api_key` query parameter.
- [`app.js:106-107`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/core/command-centre/backend/app.js#L106-L107) returns the configured API key from `/api/config`.
- [`lib-infisical.sh:60-63`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/platform-runtime/lib-infisical.sh#L60-L63) passes the machine client secret to the Infisical CLI login command.
- The evidence register in [PR #610 at commit `e61abcffc5b01cf9875697e27acd3e907d7a21d8`](https://github.com/timjardenross/TJRHQ/blob/e61abcffc5b01cf9875697e27acd3e907d7a21d8/docs/operations/disaster-recovery-gap-assessment-2026-11-08.md) contains FA-01, FA-02, FA-04, FA-18 and FA-19. No new FA identifiers are proposed here.
- The planning baseline is [PR #611 at commit `014ba427ae84405c88df7f5d46756d9a4b149625`](https://github.com/timjardenross/TJRHQ/blob/014ba427ae84405c88df7f5d46756d9a4b149625/docs/architecture/TJRHQ-architecture-code-review-baseline-v1.0.md).

### Consumer and dependency inventory

Before implementation, produce a metadata-only inventory with one row per caller or route:

| Field | Required content |
|---|---|
| Consumer | UI, service, script, test or external integration name |
| Entry point | URL path, module, unit or script |
| Current credential path | Header, query string, config bootstrap or service environment; never the value |
| Required capability | Read, write, owner action or service action |
| Replacement path | Session, scoped service credential or approved alternative |
| Migration order | Consumer migration before enforcement |
| Verification | Positive test and negative authorization test |
| Owner | Person accountable for sign-off |

The inventory must be built from repository search, route/client references and unit definitions. Do not inspect environment values, print command lines, or test against production.

### Proposed authentication and authorization contract

- Remove reusable credentials from `GET /api/config`; it may return non-secret UI configuration only.
- Migrate callers to an authenticated session or explicitly scoped service credential approved by the owner.
- Enforce authentication centrally for every protected route.
- Enforce operation-specific authorization at each mutation boundary:
  - anonymous or invalid identity: `401`;
  - authenticated but insufficient permission: `403`;
  - owner-authorized mutation: proceed;
  - read-only service identity: read-only routes only.
- Reject query-string API keys after all legitimate callers have migrated.
- Redact credentials from request logs, error responses, test fixtures and evidence.
- Treat localhost, firewall rules and Caddy as exposure controls, not authorization.

### Infisical decision preparation

The repository’s current helper uses universal-auth with `--client-id` and `--client-secret` at [`lib-infisical.sh:60-63`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/platform-runtime/lib-infisical.sh#L60-L63). Before implementation:

1. Record the installed CLI version using a non-secret version command.
2. Consult the matching official CLI documentation for supported non-argv secret input.
3. Select only a documented mechanism; do not invent flags or infer support from unrelated versions.
4. Validate the replacement in an isolated test environment with synthetic credentials.
5. Confirm process listings, logs and failure output contain no secret values.

### Implementation sequence and rollback

1. Complete the metadata-only caller inventory and owner review.
2. Implement the replacement authentication/session path behind tests.
3. Migrate callers one group at a time; retain a measured rollback switch only if it cannot re-enable unauthenticated disclosure.
4. Enforce route authorization and remove the query-string fallback.
5. Change the Infisical transport after supported CLI/API behavior is confirmed.
6. Perform controlled verification and independent review.
7. Deploy only under a separate production approval.

Rollback must restore service compatibility without restoring public key disclosure, query-string credentials, or secret-bearing process arguments. A rollback that reintroduces any of those conditions is prohibited.

### Approval test matrix

| Scenario | Expected result |
|---|---|
| Anonymous `/api/config` | No reusable credential; non-secret response only |
| Missing or invalid authentication | `401`, no sensitive response |
| Authenticated non-owner mutation | `403`, redacted audit event |
| Authorized owner mutation | Succeeds and emits no sensitive payload |
| Read-only service identity on mutation | `403` |
| Query-string API key | Rejected after migration |
| Header/session credential | Accepted only for the approved capability |
| Request and error logs | No credential values or URL secrets |
| Infisical process inspection in isolated test | Client secret absent from argv |
| Rollback verification | No unauthenticated disclosure or query-string fallback |
| Redis disposition | Remains `UNKNOWN` until separately owner-approved |

### Approval gates requested

Approval should be recorded separately for:

- design and consumer inventory;
- implementation and test changes;
- Infisical transport change;
- any Redis credential decision or rotation;
- production deployment and monitoring.


## Owner decisions still open

1. Which legitimate clients depend on the existing key bootstrap, and what replacement authentication design should they use?
2. Should a separately authorized credential-response plan be prepared for Redis and any other affected secrets?

**No production changes, credential inspection/rotation, deployments, backup/restore, merges or service restarts are authorized by this plan.**

## PR publication checklist

- [x] Confirm exact source permalinks and FA mapping against PR #610.
- [x] Check document for sensitive values.
- [x] Define the metadata-only consumer inventory and approval-ready implementation package.
- [x] Define authentication, authorization, sequencing, rollback and test requirements.
- [ ] Complete the inventory against all repository callers.
- [ ] Record CI and independent Mac/VM access status.
- [ ] Obtain separate owner approval before implementation or production action.
- [ ] Leave PR unmerged pending explicit owner approval.
