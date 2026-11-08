# WP-03 — Job Reliability & Alerting

**Status:** DRAFT FOR OWNER REVIEW — NOT AUTHORIZED FOR EXECUTION  
**Baseline:** PR #611 architecture review baseline  
**Evidence:** PR #610 discovery and evidence report  
**Dependency:** WP-01 security work and the VM runbook evidence

## Purpose

Make scheduled jobs observable and fail loudly when they do not run, fail, or produce incomplete output. This is a lightweight plan for a single-owner project; it does not authorize production changes.

## Known planning inputs

- Mission-engineering-dispatch is enabled but has had no observed dispatch since 28 October in the reviewed evidence.
- Backup checks have produced successful sampled results, but failure propagation and alerting require explicit verification.
- The weekly backup verification run passed with exit 0; a non-blocking systemd cleanup warning was recorded.
- The nightly backup is scheduled separately and must remain independently observable.
- Alert state must not create duplicate paging or cooldown entries.

## Proposed work

1. Define one success/failure contract for each timer and service.
2. Ensure failures produce non-zero exits and are visible in the journal.
3. Add a single owner-facing alert for missed schedules, failed execution, and invalid output.
4. Record the last successful run, last failure, next scheduled run, and current alert state.
5. Keep backup verification, dispatch, and nightly backup alerts separate.
6. Add a dry-run or fixture-based test path before any production enablement.
7. Preserve existing dirty working-tree entries and do not use production data in tests.

## Acceptance criteria

- A failed job exits non-zero.
- A missed timer run is detectable from one owner-facing status view.
- Alerting is deduplicated and cooldown state is visible.
- Successful backup verification does not create a false alert.
- The weekly systemd warning remains classified separately from job failure unless evidence shows impact.
- Dispatch output is validated before being marked successful.
- A rollback/removal path exists for any alerting change.
- No production job, timer, service or alert configuration is changed by this planning document.

## Owner decisions required

1. Which owner-facing alert channel should be canonical?
2. How long may a scheduled job be late before alerting?
3. Should missed dispatch alert immediately or after one full schedule interval?
4. What minimum output makes a dispatch successful?
5. Should backup verification warnings notify the owner or remain journal-only?

## Traceability

This plan is derived from PR #610 evidence and PR #611 findings. Exact finding/action mappings must be verified against those documents before publication. No new FA numbers are created here.
