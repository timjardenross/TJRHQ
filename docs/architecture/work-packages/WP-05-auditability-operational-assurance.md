# WP-05 — Auditability & Operational Assurance

**Status:** DRAFT FOR OWNER REVIEW — lightweight planning and closeout record  
**Baseline:** PR #611  
**Evidence:** PR #610  
**Scope:** Existing audit, journal, deployment and owner-decision evidence only

## Purpose

Provide enough operational traceability for a single-owner project to answer: what changed, when did it change, who/what initiated it, and what was the result? This package introduces no new audit platform, dashboard, approval board or enterprise retention process.

## Existing controls

- auditd rules for Git execution, SSH execution and login records were installed and enabled on the VM during WP-01 work.
- systemd journals record auto-deploy, service starts/stops, timer runs and failures.
- GitHub PRs record implementation decisions, CI results, approvals and merge commits.
- The production checkout and deployment SHA provide a current-state reference.
- Owner decisions are recorded in the relevant work-package PR conversation and documentation.

## Minimal operational review

1. Confirm auditd is active and enabled.
2. Confirm Git, SSH and login rule categories are loaded.
3. Confirm a Git execution event is searchable.
4. Confirm auto-deploy journal entries show pull result, service result and failures.
5. Confirm key service and timer journals are readable.
6. Confirm WP-01 through WP-04 decisions and merge commits are recorded.
7. Record production checkout status without modifying it.
8. Record audit coverage start time and preserve UNKNOWN for earlier events.

## Evidence table

| Control | Evidence source | Status | Limitation |
|---|---|---|---|
| Git execution audit | auditd rule/search | Pending VM discovery | No historical coverage before auditd installation |
| SSH/login audit | auditd and login records | Pending VM discovery | Rules may have no post-install event yet |
| Deployment history | auto-deploy journal and Git commits | Partially established | Attribution before auditd may remain UNKNOWN |
| Service history | systemd journals | Partially established | Journal retention is host-dependent |
| Owner decisions | WP-01–WP-04 PRs/docs | PASS for recorded decisions | Informal decisions outside repository may be absent |
| Checkout state | read-only Git status | Pending VM discovery | Preserved dirty/untracked entries may remain |

## Closeout rule

WP-05 closes when the read-only VM discovery confirms the existing audit and journal controls are usable, owner decisions are traceable in GitHub, and all historical coverage limits are documented. Any un-attributed event remains UNKNOWN; it is not converted into a claim.

## Owner decision convention

For this single-owner project, an owner decision is recorded in the relevant PR or work-package document with the decision, scope, date, and whether it authorizes planning, merge, deployment or production execution. No additional approval system is required.

## Known limitations

- Audit coverage begins when auditd rules were installed; earlier activity may be un-attributable.
- Journal retention and completeness depend on the VM's systemd journal configuration.
- GitHub records repository changes but cannot prove who performed an unlogged VM action.
- The process does not establish compliance certification or immutable audit storage.

## Safety

This is documentation and read-only verification only. It authorizes no audit-rule change, service restart, deployment, credential action, database change, backup/restore operation or production modification.
