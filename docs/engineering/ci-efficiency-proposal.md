# CI Efficiency Proposal

**Status:** DRAFT FOR OWNER REVIEW — proposal only  
**Scope:** Reduce unnecessary CI runtime without weakening security or merge protection.

## Current state

The repository runs a broad Python workflow containing path selection, code tests, root tests, static analysis, dependency audit, prompt evaluation, secret/security scans, workflow linting and a merge gate. The former LCARS portal is no longer the active frontend; current UI work is organised into workbenches. Any LCARS workflow is therefore legacy coverage unless a change still touches `lcars-portal` or its dependencies. The merge gate already treats a smaller set as required, but unrelated jobs still run on many pull requests.

## Proposed policy

### Documentation-only pull requests

Required:

- changes/path classification;
- pre-commit secrets;
- pre-commit security;
- merge-gate.

Run only when relevant:

- actionlint, if workflow files change;
- documentation/Markdown validation, if available.

Do not run unrelated Python, workbench, promptfoo or dependency tests.

### Small configuration or service-unit pull requests

Required:

- changes/path classification;
- pre-commit secrets;
- pre-commit security;
- pre-commit lint;
- root tests;
- actionlint if workflow files change;
- relevant focused tests.

### Python/application pull requests

Required:

- changes/path classification;
- pre-commit secrets;
- pre-commit security;
- pre-commit lint;
- root tests;
- affected test matrix;
- relevant static checks.

Advisory or scheduled:

- vulture;
- pip-audit;
- promptfoo;
- full semgrep scan where the changed paths do not require it.

### Workbench-only pull requests

Run the workbench registry gate and tests for the affected workbench(s), plus the shared security checks. Include shared frontend checks only when shared frontend code or dependencies changed. Do not run unrelated Python suites.

Do not run the legacy LCARS portal workflow for workbench-only changes. Run it only if files under `lcars-portal` are changed or an explicit dependency review shows that the legacy portal is affected.

## Safety rules

- Keep secret scanning and security scanning mandatory for every PR.
- Keep the merge gate mandatory.
- Never remove a check from branch protection in the same PR that changes its workflow behavior.
- Any required-check rename requires a staged change: workflow update, successful CI, then separate owner-approved branch-protection update.
- Do not rely on skipped required checks unless the merge gate explicitly treats legitimate path-based skips as success.
- Keep full security/dependency checks available through scheduled runs or manual dispatch.
- Treat the LCARS workflow as legacy until the repository owner confirms it can be retired; this proposal does not retire or modify it.

## Acceptance criteria

1. Documentation-only PRs complete without unrelated application test suites.
2. Python code PRs still run root and affected tests.
3. Workbench PRs run the registry gate and affected workbench tests.
4. Security and secret checks remain mandatory.
5. Merge-gate behavior remains green for legitimate path-based skips.
6. Required-check names remain stable until branch protection is deliberately updated.
7. A sample documentation PR, workbench PR and Python PR demonstrate the reduced job sets.
8. No production, VM or deployment behavior changes.

## Rollback

Revert the workflow-only change if a required security check is skipped, a legitimate code path is not tested, or merge-gate behavior becomes ambiguous. Branch-protection changes are separate and reversible.
