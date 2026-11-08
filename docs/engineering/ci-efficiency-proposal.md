# CI Efficiency Proposal

**Status:** DRAFT FOR OWNER REVIEW — proposal only  
**Scope:** Reduce unnecessary CI runtime without weakening security or merge protection.

## Current state

The repository runs a broad Python workflow containing path selection, code tests, root tests, static analysis, dependency audit, prompt evaluation, secret/security scans, workflow linting and a merge gate. LCARS has a separate workflow. The merge gate already treats a smaller set as required, but unrelated jobs still run on many pull requests.

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

Do not run unrelated Python, Storybook, promptfoo or dependency tests.

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

### LCARS-only pull requests

Run the LCARS workflow and the shared security checks. Do not run unrelated Python suites.

## Safety rules

- Keep secret scanning and security scanning mandatory for every PR.
- Keep the merge gate mandatory.
- Never remove a check from branch protection in the same PR that changes its workflow behavior.
- Any required-check rename requires a staged change: workflow update, successful CI, then separate owner-approved branch-protection update.
- Do not rely on skipped required checks unless the merge gate explicitly treats legitimate path-based skips as success.
- Keep full security/dependency checks available through scheduled runs or manual dispatch.

## Acceptance criteria

1. Documentation-only PRs complete without unrelated application test suites.
2. Python code PRs still run root and affected tests.
3. Security and secret checks remain mandatory.
4. Merge-gate behavior remains green for legitimate path-based skips.
5. Required-check names remain stable until branch protection is deliberately updated.
6. A sample documentation PR and a sample Python PR demonstrate the reduced job sets.
7. No production, VM or deployment behavior changes.

## Rollback

Revert the workflow-only change if a required security check is skipped, a legitimate code path is not tested, or merge-gate behavior becomes ambiguous. Branch-protection changes are separate and reversible.
