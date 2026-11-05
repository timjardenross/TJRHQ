# Backup verification: first nightly run with the improved script (2026-11-05)

**Result: PASS.** Read-only. Nothing was changed, re-run or rolled back.

Repo: `rclone:gdrive2:starship-backups-v2`, password file `/root/.restic-pass` (the same defaults `backup.sh` uses; both set explicitly via env).
Verified 2026-11-05 about 07:45-08:30 AEDT, about 5 hours after the run.
Labels: VERIFIED = observed directly in this session. UNKNOWN = not observed or not provable from what was run.

## Results

| # | Check | Command | Result | Label |
|---|---|---|---|---|
| 1 | Run happened and succeeded | `systemctl status starship-backup.service --no-pager` | `Main PID: 711646 (code=exited, status=0/SUCCESS)`; inactive (dead) since 02:41:12; CPU 17.1s; triggered by `starship-backup.timer` (fired 02:40:06). Next run Fri 2026-11-06 02:40. | VERIFIED |
| 1b | Start / end / errors | `journalctl -u starship-backup.service --since "2026-11-05 02:30" --no-pager` | Start 02:40:06 (script `start` line 02:40:07, `dry_run=0`). End 02:41:12 (`finished OK`, `Deactivated successfully`). About 66 s wall time. `grep -i -E "error\|fail\|warn\|denied\|cannot"` over the window: **0 lines**. | VERIFIED |
| 2 | New snapshot landed | `restic snapshots --compact` | Newest: **`3ab9464e`**, 2026-11-05 02:40:28, tag `starship-nightly`, host `vmi3371936`. Journal: `snapshot 3ab9464e saved`; added 24.036 MiB (22.250 MiB stored); 245 files processed, 95.196 MiB. Repo now lists **10 snapshots, not 11** (see Deviations). | VERIFIED (snapshot exists) / UNKNOWN (which old snapshot was pruned) |
| 3 | Four new paths present | `restic ls latest > file; grep -c "^<path>"` | `/etc/systemd/system`: **275** entries. `/opt/deploy-guard`: **5** (dir + `auto-deploy-services.conf`, `repair-git-perms.sh`, `repair-tree-perms.sh`, `scoped-restart.sh`). `/etc/sysstat`: **3**. `/etc/systemd/journald.conf.d`: **3**. | VERIFIED |
| 4 | chatterbox pip freeze present | Path from `backup.sh` line 157 (`$STAGE/chatterbox-venv-freeze.txt`); `grep chatterbox` over `restic ls latest` | `/var/tmp/starship-backup.gmbAEU/chatterbox-venv-freeze.txt`, 2550 bytes, mode 0600. `restic dump` gives 129 lines, 0 lines that look like an error or warning. The two other `chatterbox` hits are the unit file and its `.wants` symlink under `/etc/systemd/system`. Contents not printed. | VERIFIED |
| 5 | Regression vs previous snapshot | `restic diff 4fb41b3e 3ab9464e`; `restic stats <id> --mode restore-size` | Previous `4fb41b3e`: 252 files, 95.124 MiB. New `3ab9464e`: 476 files, 95.196 MiB. Size flat (+0.07 MiB); file count **up** 252 to 476, from `/etc/systemd/system` entries (diff: 36 new files, 165 new "others" = symlinks, 33 new dirs). Added 24.036 MiB / removed 23.885 MiB. Removed entries are the previous run's random `/var/tmp/starship-backup.<id>/` staging dir. No unexpected drop. | VERIFIED |
| 6 | Secret-bearing path: present, mode 0640 | `restic ls -l latest /opt/deploy-guard/auto-deploy-services.conf` | In snapshot, `-rw-r-----` (0640), 3481 bytes, mtime 2026-11-03 19:37:23. Contents not read. (Owner column shows 0/0 = root.) | VERIFIED |
| 7 | Integrity spot check | `restic check --read-data-subset=1%` | `10 / 10 snapshots` checked, `read 1.0% of data packs  1 / 1 packs`, **`no errors were found`**, rc=0. | VERIFIED (1% sample only) |
| 8 | Expected gap: `/root/ollama-*` | `grep -c "ollama-0"` and `grep -c "^/root/ollama"` over `restic ls latest` | **0 / 0** in the latest snapshot. The `backup.sh` path list (lines 163-177) has no `/root/ollama-*` entry, so they could not have been selected. Older snapshots were not listed. | VERIFIED (latest + script) / UNKNOWN (older snapshots) |

## Pass criteria

| Criterion | Met |
|---|---|
| Service exited 0 | yes |
| Today's snapshot exists | yes (`3ab9464e`) |
| All four new paths present | yes |
| pip freeze present | yes |
| 1% integrity check clean | yes |

## Deviations and caveats

1. **Snapshot count is 10, not the expected 11.** The brief expected one new snapshot on top of the 10 seen earlier. The same run does `forget --keep-daily 7 --keep-weekly 4 --keep-monthly 3` plus prune (journal: `removing 3 old packs`, `repacking packs`), and the list now has gaps (Oct 10, 18, 25, 30, 31, then daily from Nov 1). A snapshot almost certainly aged out under that policy. I did not see which one was removed, so the cause is UNKNOWN. It does not affect any pass criterion.
2. **The brief's journal command failed as written.** `--since "today 02:30"` returns `Failed to parse timestamp: today 02:30` on this systemd. I used `--since "2026-11-05 02:30"`. Same data.
3. **Supabase dump was reused, not re-taken.** Journal: `1/5 supabase dump skipped: cached dump is 47h old (next due at 72h)`. This is by design (no Supabase egress), but today's snapshot carries a 47-hour-old DB dump. It is also not an error.
4. **Integrity coverage is a 1% sample.** `check --read-data-subset=1%` read one pack. It shows the repo structure and one pack are sound, not that every pack is readable.
5. **The new paths were not compared against the pre-change snapshot.** I did not list `4fb41b3e` for the four paths. The brief only asked that they exist in the latest snapshot, which they do.

## Rollback (not performed)

If the Captain wants it: copy `/root/backup-script-rollback-2026-11-04/backup.sh.orig` over `/opt/starship-backup/backup.sh`, keeping mode `-rwx------ root:root`. Not recommended by these results.
