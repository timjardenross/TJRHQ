# WP-02 — Deployment Governance & Owner Authorization

**Status:** DRAFT FOR OWNER REVIEW — NOT AUTHORIZED FOR EXECUTION  
**Baseline:** [PR #611](https://github.com/timjardenross/TJRHQ/pull/611) at commit `014ba427ae84405c88df7f5d46756d9a4b149625`  
**Evidence:** [PR #610](https://github.com/timjardenross/TJRHQ/pull/610) at commit `e61abcffc5b01cf9875697e27acd3e907d7a21d8`  
**Dependency:** WP-01 implementation and acceptance

## Scope

WP-02 addresses deployment governance, owner authorization, route-level authorization dependencies and production change control. It remains a planning document; it authorizes no deployment, database change, service restart or credential action.

## Findings and traceability

- **ARCH-02 / FA-05:** `main` commits can reach the VM through the pull-based auto-deploy path without an independently verified CI or owner-approval gate.
- **ARCH-08 / FA-09:** the backend uses Supabase service-role access broadly; route-level least privilege is not established.
- **ARCH-16 / FA-11:** LCARS mutating routes require explicit Captain/owner authorization design.
- **ARCH-17 / FA-10:** live RLS and sign-up posture require owner verification.
- **ARCH-18 / FA-14:** live SEC-01 Caddy state requires owner verification.
- **FA-12 / FA-13:** Slack research and Telegram per-user authorization remain in scope.

Source references:

- [`deploy/auto-deploy.sh`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/auto-deploy.sh) pulls `main` and controls the restart path.
- [`deploy/auto-deploy.service`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/auto-deploy.service) runs the deploy mechanism as the `deploy` user.
- [`core/command-centre/backend/app.js`](https://github.com/timjardenross/TJRHQ/blob/40b45b5cc8324123ca25f489cd177aced745facf/core/command-centre/backend/app.js) is the WP-01 implementation baseline.

## Proposed controls

### GitHub and deployment

1. Protect `main` with required review count, required CI checks and restrictions on direct pushes.
2. Require a production environment approval before a commit can deploy.
3. Make the VM pull path consume only an approved commit or protected branch state.
4. Record commit SHA, approver identity, deployment start/end, service restart result and rollback result.
5. Keep deployment credentials read-only against GitHub; no VM-side push.
6. Define an emergency bypass with explicit owner identity, reason, expiry and retrospective review.

### Authorization boundaries

1. Define owner/Captain, operator, service and read-only identities.
2. Map each mutating route to the minimum role and capability.
3. Keep authorization server-side; never trust a browser-supplied role.
4. Use least-privilege database clients per route where feasible.
5. Verify Telegram user IDs and Slack research authorization against an owner-approved allowlist.
6. Preserve `UNKNOWN` for live RLS, sign-up and Caddy state until read-only owner verification is recorded.

## Implementation sequence

| Stage | Deliverable | Approval gate |
|---|---|---|
| A | Read-only GitHub branch/ruleset and deployment-path inventory | Owner scope approval |
| B | Protected-branch and environment design | Owner governance approval |
| C | CI/deploy gate implementation in an isolated branch | Implementation approval |
| D | Route authorization matrix and least-privilege design | Security review |
| E | Non-production verification and rollback rehearsal | Verification approval |
| F | Production enablement and monitoring | Explicit production approval |

## Acceptance criteria

1. Direct pushes to `main` are restricted.
2. Required CI checks are enforced before merge.
3. Production deployment requires an explicit environment approval.
4. A deployment record links commit, approval identity, checks, service results and rollback outcome.
5. Emergency bypasses are attributable and time-bounded.
6. Every mutating route has a documented server-side authorization rule.
7. Browser-provided roles cannot elevate privileges.
8. RLS, sign-up and live Caddy claims are either verified or explicitly marked UNKNOWN.
9. Rollback restores the prior approved version without bypassing authorization gates.
10. No deployment or production change occurs as part of this planning PR.

## Owner decisions required

1. Required review count and required status checks for `main`.
2. Who may approve production deployments.
3. Whether emergency bypass is permitted, and its expiry/review rules.
4. Approved owner/Captain, operator, service and read-only role definitions.
5. Whether WP-02 should include Telegram/Slack authorization implementation or track it as separate sub-work.

**No production changes, branch-protection changes, deployments, service restarts, database changes or credential actions are authorized by this plan.**


## Bulk preparation completed

The following artifacts are prepared for owner review. They are designs and checklists only; none changes live GitHub settings, deployment behavior or production state.

### Read-only inventory to capture before implementation

| Area | Evidence to record | Unknown that must remain explicit |
|---|---|---|
| Repository governance | Default branch, protection/ruleset state, required checks, direct-push permissions | Whether current settings are enforced for all actors |
| CI | Workflow names, trigger events, protected-branch status, artifact retention | Whether every deployable commit has a successful immutable result |
| VM deploy path | Deployed SHA, pull source, deploy user, timer/service unit, restart inventory | Who initiated unexplained pulls and whether the path is owner-authorized |
| Authorization | Route inventory, mutating verbs, identity source, capability mapping | Live Telegram, Slack, Supabase RLS and sign-up posture |
| Recovery | Previous approved SHA, rollback command/runbook, approval record | Whether rollback has been rehearsed end-to-end |

### Proposed approval record

Every production deployment should create an append-only record containing:

- repository and target environment;
- commit SHA and release/reference identifier;
- CI run/check identifiers and result;
- approver identity, approval timestamp and stated scope;
- operator identity and deployment start/end;
- services restarted and health-check results;
- rollback decision, if any, including prior approved SHA;
- links to logs and post-deployment verification.

The record is not valid if approval is inferred from a chat message, a successful CI run alone, or an unprotected branch state.

### Proposed rollback record

A rollback is complete only when the record identifies:

1. the failed release and reason;
2. the last approved known-good SHA;
3. the approving owner;
4. the operator and execution time;
5. service health and route checks after rollback;
6. follow-up action and expiry for any emergency bypass.

### Service inventory acceptance

The implementation inventory must include `command-centre.service`, because its backend serves port 5000 and requires a restart for backend changes. PR #616 is the current isolated implementation candidate. Acceptance requires a configuration review plus a non-production or explicitly approved verification; this document does not authorize a production restart.

### CI and failure-mode test matrix

| Test | Expected result |
|---|---|
| Pull request without required CI | Cannot merge |
| Direct push to protected `main` | Rejected or attributable emergency bypass |
| CI passes but environment approval is absent | No production deployment |
| Deployment SHA differs from approved SHA | Deployment stops |
| Service restart fails | Deployment fails and records the failure |
| Health check fails after restart | Rollback decision is required; no success recorded |
| Emergency bypass lacks owner, reason or expiry | Rejected |
| Browser submits an elevated role | Server ignores client role and authorizes from trusted identity |
| Rollback targets an unapproved SHA | Rejected |
| Required production evidence is missing | Work package remains open |

### Route authorization decision matrix

Before implementation, fill one row per mutating route:

| Surface | Route/action | Trusted identity | Required capability | Data/database scope | Negative test |
|---|---|---|---|---|---|
| Command Centre | Each mutating API route | Server-authenticated principal | Owner/operator capability as approved | Minimum required tables/operations | Unauthenticated and read-only principal rejected |
| LCARS | Each mutating API route | Server-side session/token | Captain/owner capability as approved | Minimum required mutation | Browser-supplied role rejected |
| Telegram | Each mutating command | Verified Telegram user ID | Approved operator/owner capability | Command-specific scope | Unlisted user rejected |
| Slack | Research/escalation actions | Verified Slack identity | Approved research capability | Minimum event/data scope | Unapproved workspace/user rejected |
| Supabase | Sign-up/RLS-sensitive operations | Trusted service or user identity | Policy-specific capability | Explicit RLS scope | Cross-tenant or unauthorized row rejected |

### Remaining owner decisions

- Required review count and exact CI checks for protected `main`.
- Production approver(s) and whether two-person approval is required.
- Emergency bypass allowed or prohibited; if allowed, expiry and retrospective-review period.
- Canonical approval-record store and retention period.
- Whether Telegram/Slack authorization remains in WP-02 or becomes a separately approved package.
- Whether rollback rehearsal must precede the first governed production deployment.
- Whether PR #616 should be merged independently or included in the WP-02 implementation sequence.

### Evidence status

This preparation references PR #610 evidence commit `e61abcffc5b01cf9875697e27acd3e907d7a21d8`, PR #611 baseline commit `014ba427a` as previously recorded, merged WP-01 implementation commit `40b45b5cc8324123ca25f489cd177aced745facf`, and draft PR #616. Live settings and VM state remain unverified in this documentation branch.
