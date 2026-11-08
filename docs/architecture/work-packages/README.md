# TJRHQ Architecture Work Packages

**Status:** DRAFT — PLANNING ONLY — NOT AUTHORIZED FOR EXECUTION

**Baseline:** [PR #611](https://github.com/timjardenross/TJRHQ/pull/611), commit `014ba427a`  
**Evidence:** [PR #610](https://github.com/timjardenross/TJRHQ/pull/610), commit `e61abcffc5b01cf9875697e27acd3e907d7a21d8`

| Package | Scope | Plan | Execution |
|---|---|---|---|
| [WP-01](WP-01-api-security-credentials.md) | API security and credential protection | Draft for review | Not authorized |
| WP-02 | Deployment governance and owner authorization | Pending | Not authorized |
| WP-03 | Job reliability and alerting | Pending | Not authorized |
| WP-04 | Backup completeness and disaster recovery | Pending | Not authorized |
| WP-05 | Auditability and operational assurance | Pending | Not authorized |

## Governance

Each work package receives a separate documentation PR. PR #611 remains the planning baseline and PR #610 the detailed evidence record. All changes to plans require reviewed commits. Approval of a plan does not approve implementation, merging, deployment, service restarts, secret inspection or rotation, database changes, backup or restore activity.

## Workflow

1. Confirm the latest evidence and current repository source references.
2. Draft and review each package's requirements, design, acceptance criteria, dependencies and rollback.
3. Record owner decisions and explicit authorization separately before any execution.
4. Track implementation and verification in future, separately approved PRs.

## Publication checks

- [ ] Verify source locations and action IDs against PR #610.
- [ ] Confirm no secret values in the documents.
- [ ] Create a documentation-only PR containing this index and WP-01.
- [ ] Record CI and Mac/VM accessibility independently.
- [ ] Do not merge without owner approval.
