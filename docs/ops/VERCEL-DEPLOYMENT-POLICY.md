# Vercel deployment policy and quota containment (2026-11-24)

## What happened (evidence, read-only)
- Project `usstjros` (root `lcars-portal`) hit `api-deployments-free-per-day` (100/day, Hobby) at about 05:37Z on 2026-11-24.
- The 100 most recent deployments span 2026-11-23 08:21Z to 2026-11-24 05:44Z, and a further 31 earlier in the same trailing 24 h were listed, so at least 131 were created in 24 h. Peaks: 29 in the 08:00Z hour (23 Nov), 15 at 22:00Z, 12 at 03:00Z, 16 at 05:00Z.
- **92 of the 100 listed were CANCELED, only 3 READY.** The existing `ignoreCommand` in `lcars-portal/vercel.json` cancels builds for commits that do not touch the portal, but a canceled (ignored) deployment is still a created deployment and still counts. So the guard cannot protect the quota.
- Triggers found: (1) Vercel Git integration on every push to every branch, 95 of 100 attributed to the connected GitHub user: agent branches `claude/**` (rem-669-*, supabase-ro-access, provenance, brief-reliability, ...), merge commits, draft PRs; (2) production deployments on every merge to `main` (20 canceled + 3 ready in the window), including Python/SQL/docs-only merges. No `.github` workflow, deploy hook or retry mechanism references Vercel (`git grep` of `.github`), and only 1 duplicate commit SHA was seen.

## Quota accounting and reset (verified vs not)
- Verified: canceled and ignored deployments count toward the daily allowance; previews and production share the allowance.
- Not verified: whether the 24 h window is rolling or fixed. The error says "try again in 24 hours / 1 day". Do not assume a fixed reset time. Plan: once per hour, count deployments created in the trailing 24 h with `tools/ops/vercel_deploy_budget.py` (read-only; no retries, nothing is created) and make the first explicit deployment only when the count is well under the internal budget. If the allowance frees gradually as the early-window deployments age out (first at about 08:21Z), that confirms a rolling window.

## Operating model
1. **No automatic previews.** Agent branches, worktrees, draft PRs and routine commits create no Vercel deployment. GitHub CI, tests, lint and builds run unchanged (they are GitHub Actions, not Vercel).
2. **Portal-only production.** A merge to `main` creates a production deployment only when the portal root changed (`enableAffectedProjectsDeployments`); Python, SQL and docs merges create none.
3. **Explicit previews.** A preview is created on request for frontend acceptance (Vercel `create_deployment` with the branch and SHA, the CLI, or a deploy hook), never by a push.
4. **Governed production.** Production follows the existing release process: portal changes are consolidated into one release PR/merge, and a deployment of the same commit and target is not repeated (do not use `forceNew`).
5. **Internal budget (not targets):** at most 10 previews and 10 routine production deployments per rolling 24 h, leaving capacity for emergency release and recovery. `tools/ops/vercel_deploy_budget.py <list-deployments.json> --target preview|production [--emergency]` returns exit 3 when the budget is reached; non-essential deployments stop at that point. Emergency releases may use the platform allowance until it is exhausted.
6. **Rollback is unchanged:** Vercel instant rollback to a previous production deployment (a promotion, no new build) stays available.

## Required project settings (needs authorisation; not applied)
Native project settings, applied by `update_project` on `prj_4wr0sCWTYuPWbs4K0ijW49NBoMgi`:
```json
{
  "deploymentPolicy": {
    "deploymentSources": [
      {"enabled": false, "environments": [{"type": "system", "target": "preview"}], "sources": ["git"]}
    ]
  },
  "enableAffectedProjectsDeployments": true
}
```
- The first entry turns off Git-triggered preview deployments for the whole project. Because it is a project setting, an old branch that lacks the repository `vercel.json` change cannot bypass it (a `vercel.json` setting is read per commit and can be). CLI, REST and deploy-hook previews remain enabled.
- `enableAffectedProjectsDeployments` skips deployments when nothing under the project root or its dependencies changed. Caveat: `ignoreCommand` also watches `../config/osint_intelligence_missions.json`, which is outside the root and not a package dependency; a change only to that file would no longer trigger a portal deployment. Say if that file must keep triggering one.
- Defence in depth in this change: `lcars-portal/vercel.json` now also disables Git deployments for `claude/**`, `worktree-*` and `archive/**`.
- Rollback of the settings: set `deploymentSources[0].enabled` to `true` and `enableAffectedProjectsDeployments` to `false`.

## Verification
Done now (no deployments created): project settings and `vercel.json` inspected; deployment history analysed; budget tests (`tests/test_vercel_deploy_budget.py`) pass; CI and build validation are GitHub Actions and are unaffected.
After the settings are applied and capacity returns (needs live capacity): (a) a commit on a `claude/*` branch and a draft PR create no deployment; (b) a Python-only merge to `main` creates none; (c) an explicitly requested preview deploys; (d) a portal release merge deploys to production once; (e) rollback to the previous production deployment works. Record each with the deployment list.
