# Restic backup integrity: weekly check, lock contention and recovery evidence

Scope: off-box repository `rclone:gdrive2:starship-backups-v2`, written nightly at 02:40
Australia/Melbourne by `starship-backup.service` (source of truth: `deploy/starship-backup.sh`).
Runs as root. The restic password is read from `/root/.restic-pass` (root-only) and is never
placed in unit files, arguments or logs.

## Components

| File | Role |
|---|---|
| `deploy/starship-backup.sh` | Nightly backup. Lock contention now exits 75 (non-zero), so `OnFailure=` pages. |
| `deploy/starship-backup-integrity.service` | Weekly `restic check --read-data-subset=1/20` under `flock -n` on the shared lock. |
| `deploy/starship-backup-integrity.timer` | Sunday 11:30 Australia/Melbourne. `Persistent=false`. |

## Locking

- Both jobs use `/run/starship-backup.lock`.
- The nightly script takes it with `exec 9>` and `flock -n 9` and holds it for the whole run.
- The weekly unit runs `flock -n` on the same file. Overlap in either direction is caught.
- Lock held, nightly: logs "another run holds the lock", exits 75, unit fails, `OnFailure` pages.
- Lock held, weekly: `flock` exits 1, unit fails, `OnFailure` pages.
- Previously the nightly exited 0 on lock contention, with no backup and no alert. This change
  removes that silent skip. A night skipped because of contention now needs a manual rerun.
- Restic's own repository locks still apply to any other restic process.

## Evidence recorded, 2026-11-08 (manual, read-only)

- Repository check: `restic check --read-data-subset=1/20` against
  `rclone:gdrive2:starship-backups-v2`. Exit 0, "no errors were found". All 12 snapshots, all trees
  and blobs checked for metadata; 4 of 52 data packs read. Took about 10 seconds. No stale lock
  remained afterwards.
- Restore drill: three files restored from snapshot `625051d6` into a new root-only scratch
  directory, then removed.
  - `/etc/systemd/journald.conf.d/starship-endeavour.conf`: byte-identical to the live file.
  - `/etc/sysstat/sysstat.ioconf`: byte-identical to the live file (live mtime predates the snapshot).
  - `outputs/delivery_ledger.txt`: size and mtime match the snapshot. Not byte-compared, because the
    live file changed after the snapshot.

## Limitations

- The check is sampled (1 in 20 data packs). A full `--read-data` pass has not been run.
- The drill covered three small files. No full restore has been tested.
- Google Drive cannot make snapshots immutable. The repository credential can delete snapshots.
- Encryption at rest is restic's design. It has not been verified against the remote.
- The backup file list does not cover `knowledge/`, `deploy/`, or uncommitted changes outside the
  listed paths. Those are recoverable only through the git bundle, which contains committed branches.
- The weekly check does not alert on success. Its results are visible in the journal only.

## Installation (after merge, separate authorisation)

1. Save the current live script: `install -m 700 /opt/starship-backup/backup.sh /opt/starship-backup/backup.sh.pre-lockfix-<date>`.
2. Copy the repo script over: `install -m 700 deploy/starship-backup.sh /opt/starship-backup/backup.sh`.
3. Copy the units: `install -m 644 deploy/starship-backup-integrity.service deploy/starship-backup-integrity.timer /etc/systemd/system/`.
4. `systemd-analyze verify /etc/systemd/system/starship-backup-integrity.{service,timer}`.
5. `systemctl daemon-reload`.
6. `systemctl enable --now starship-backup-integrity.timer`. The first run is the next Sunday at 11:30.

## Verification

    systemd-analyze calendar 'Sun *-*-* 11:30:00 Australia/Melbourne' --iterations=2
    systemctl list-timers starship-backup-integrity.timer --no-pager
    systemctl status starship-backup-integrity.service --no-pager
    journalctl -u starship-backup-integrity.service --since '-14 days' --no-pager -o cat | tail -20
    grep -n 'exit 75' /opt/starship-backup/backup.sh

Lock-contention tests change alert behaviour (each failure pages). Run them only with explicit
authorisation, and not back to back, because of the per-unit alert cooldown.

## Rollback

    systemctl disable --now starship-backup-integrity.timer
    rm -f /etc/systemd/system/starship-backup-integrity.service /etc/systemd/system/starship-backup-integrity.timer
    systemctl daemon-reload
    install -m 700 /opt/starship-backup/backup.sh.pre-lockfix-<date> /opt/starship-backup/backup.sh

Nothing else changes: schedule, retention, repository, remote credentials and the failure handler
are untouched.
