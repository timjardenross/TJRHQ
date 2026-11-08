# WP-04 — Backup Completeness & Disaster Recovery

**Status:** DRAFT FOR OWNER REVIEW — lightweight closeout plan  
**Baseline:** [PR #611](https://github.com/timjardenross/TJRHQ/pull/611)  
**Evidence:** [PR #610](https://github.com/timjardenross/TJRHQ/pull/610)

## Scope

Confirm that the existing nightly Google Drive backup is operating and that a bounded restore is possible. This package does not introduce a new backup system, retention redesign, replacement-VM rehearsal, or large evidence archive.

## Current evidence

- Nightly backup: starship-backup.service and .timer, scheduled for 02:40 AEDT.
- Weekly integrity check: starship-backup-integrity.service and .timer, scheduled for Sunday 11:30 AEDT.
- Destination: rclone:gdrive2:starship-backups-v2.
- Latest reported nightly snapshot: 625051d6, exit 0.
- Latest weekly integrity check: exit 0; sampled 1/20 data-pack read.
- Existing restore drill: three small files restored; two byte-identical and one size/mtime matched.
- Failure handler: both units have OnFailure=alert-on-failure@%n.service; end-to-end alert delivery has not yet been exercised.

## Minimal acceptance checks

1. Confirm the backup and integrity timers are enabled and scheduled.
2. Confirm the latest backup completed successfully.
3. Confirm the Google Drive/restic repository is readable and has current snapshots.
4. Restore only the latest Supabase dump and Git bundle into a root-only temporary directory.
5. Validate the dump with pg_restore --list.
6. Validate the Git bundle with git bundle verify.
7. Remove the temporary restore directory and confirm no production data changed.
8. Exercise the existing failure-alert path through a safe supported test, without failing a real backup unit if no fixture mode exists.

## Closeout rule

WP-04 closes when checks 1–7 pass and check 8 either passes or is explicitly recorded as an accepted limitation by the owner. No full restore, replacement-VM rehearsal, retention change, or backup-system redesign is required for this lightweight package.

## Known limitations

- The integrity check reads a 1/20 sample, not the full repository.
- Google Drive snapshot immutability has not been established.
- The backup source list excludes knowledge/, deploy/, and uncommitted changes outside the listed paths; committed recovery is represented by the Git bundle.
- The cached Supabase dump may lag the latest nightly run until the next scheduled backup.
- The backup credential and restic password remain root-managed and are not documented here.

## Rollback and safety

The closeout checks are read-only or bounded temporary restores. They must not modify Supabase, the production checkout, backup retention, repository credentials, or timers. Any future backup implementation change requires a separate implementation PR and owner approval.
