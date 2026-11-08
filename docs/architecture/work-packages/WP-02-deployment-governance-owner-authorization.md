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
