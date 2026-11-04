# Ollama backup/staging directory clean-up: 2026-11-04

**Outcome: GATE FAILED. STOPPED. Nothing removed, nothing tarred, no state changed.** Part 1 was read-only.

Targets: `/root/ollama-0.30.10-backup` (2.1G), `/root/ollama-0.35.1-staging` (3.5G).

## Evidence

| # | Step | Command | Result | Label |
|---|------|---------|--------|-------|
| 1 | Version | `ollama --version` | 0.30.10 | VERIFIED |
| 2 | Unit | `systemctl cat ollama` | `ExecStart=/usr/local/bin/ollama serve`, `OLLAMA_KEEP_ALIVE=0` | VERIFIED |
| 3 | Active | `systemctl is-active ollama` | active | VERIFIED |
| 4 | Sizes | `du -sh` | backup 2.1G, staging 3.5G | VERIFIED |
| 5 | Backup contents | `ls -la` | `ollama` binary (0.30.10), `RESTORE.sh`, `SHA256SUMS`, `etc-systemd-system/`, `usr-local-lib/` (dated Oct 4) | VERIFIED |
| 6 | Staging contents | `ls -la` | `ollama-linux-amd64.tar.zst` (1.4G), `x/{bin,lib}` extracted (Oct 4) | VERIFIED |
| 7 | References | `grep -rIl ...` | **2 hits**: `reports/vm-audit/vm-evidence-20261103-110813.md` in `/opt/starship-endeavour` and `/opt/starship-endeavour-self-improvement`. Lines 150 and 212 only list the dirs as disk consumers | VERIFIED |
| 8 | Cron | `crontab -l` | only `draft_worker` job. No reference | VERIFIED |
| 9 | Open handles | `lsof +D` on each | none | VERIFIED |
| 10 | Live binary | `readlink -f $(command -v ollama)`, `systemctl show -p ExecStart` | `/usr/local/bin/ollama`, outside both targets | VERIFIED |
| 11 | Restic repo | `restic snapshots --latest 1` | Bare `restic` has no repo configured (`Fatal: Please specify repository location`). Repo found in `/opt/starship-backup/backup.sh`: `rclone:gdrive2:starship-backups-v2`. Queried with that: 10 snapshots | VERIFIED |
| 12 | In last snapshot? | `restic ls latest \| grep -c ollama-0` | The bare command gave 0, but it failed (no repo), so that 0 is **not evidence**. `backup.sh` uses `--files-from` with an explicit include list (no `/root/ollama-*`). The dirs are not selected, so they are **not backed up**. This is by omission, not an exclude rule. I did not re-run `restic ls` against the real repo | UNKNOWN (ls count) / VERIFIED (not in include list) |
| 13 | Models dir | `du -sh /usr/share/ollama/.ollama/models` | 55G, 15 models listed by `ollama list` | VERIFIED |
| 14 | Blobs in targets | `find <t> -name '*.gguf' -o -name blobs` | none in either | VERIFIED |

## Gate

| Condition | Result |
|---|---|
| Ollama active on a version whose files are not in either target | PASS. Active, 0.30.10, binary at `/usr/local/bin` |
| Zero references and zero open handles | **FAIL**. Zero open handles, but 2 reference hits |
| Live binary not inside either target | PASS |
| No model blobs only in targets | PASS |

**Gate = FAIL, strictly.** The 2 hits are the VM-audit evidence report (and its worktree copy) that lists the dirs as disk consumers. No unit, script or cron uses them, so they are almost certainly benign. The gate said zero, so I stopped and did not judge it myself.

## Things the Captain should know before re-releasing

1. **Backup dir is the rollback for the live version.** Live is 0.30.10. `/root/ollama-0.30.10-backup/RESTORE.sh` reinstalls that binary, lib and unit, with a SHA256 check. Removing it removes the only scripted rollback if 0.35.1 was ever installed.
2. **Staging is an upgrade that was never applied.** Live is still 0.30.10, so 0.35.1 was never installed. UNKNOWN whether it is abandoned or pending. Removing it discards the downloaded 1.4G tarball and the extracted copy, which would need re-downloading.
3. **Neither dir is in restic.** If removed, the tar rollback copy from Part 2 is required. The backup dir (2.1G) is the smaller one. The copy would need 2.1G of free space (248G free; `/` is 37% used).
4. Space that would be reclaimed: about 5.6G (`df -h /` now: 141G used, 248G avail).

## Decision needed

- (a) Accept the 2 report references as benign and re-run Part 2, or
- (b) Edit the evidence report to drop the paths, then re-run.

Nothing was removed, so `/usr/local/bin/ollama`, `/usr/share/ollama` and the models directory are untouched.

---

# Part 2: removal (Captain approved, 2026-11-04)

Captain's decisions: 0.35.1 upgrade abandoned; removal of both dirs approved; the 2 reference hits in `vm-evidence-20261103-110813.md` accepted as benign (that report was not edited). Gate cleared by the Captain's decision, not by the original criteria.

| # | Step | Command | Result | Label |
|---|------|---------|--------|-------|
| 1 | Pre-check | `systemctl is-active ollama`; `ollama --version`; `readlink -f $(command -v ollama)` | `active`; `0.30.10`; `/usr/local/bin/ollama` | VERIFIED |
| 2 | Space before | `df -h /` | 140G used, 249G avail | VERIFIED |
| 3 | Safety copy | `mkdir -p /root/ollama-dirs-removed-2026-11-04 && tar -C /root -cf .../ollama-dirs.tar ollama-0.30.10-backup ollama-0.35.1-staging` | 5,927,475,200 bytes (5.5G). `df`: 145G used while the tar existed | VERIFIED |
| 4 | Verify tar | `tar -tf` and compare to `find` | `tar -tf` OK. Entries (incl. dirs): backup 63 vs 63, staging 71 vs 71. Non-dir entries: 55 vs 55 (38 files + 17 symlinks) and 63 vs 63 (46 + 17). Content was not extracted or checksummed | VERIFIED (listing); UNKNOWN (byte-level content) |
| 5 | Remove staging | `rm -rf /root/ollama-0.35.1-staging` | rc=0; `is-active` = `active`; `ollama list` = 15 models | VERIFIED |
| 6 | Remove backup | `rm -rf /root/ollama-0.30.10-backup` | rc=0; `is-active` = `active`; `ollama list` = 15 models; `ollama --version` = 0.30.10; `ls /root/ollama-0*` = no such file | VERIFIED |
| 7 | Space after | `df -h /` | 140G used, 249G avail | VERIFIED |
| 8 | Schedule cleanup | `systemd-run --on-calendar='2026-11-11 03:00' rm -rf /root/ollama-dirs-removed-2026-11-04` | Timer `run-rbe4844dbf16a467daf9c0cf0aa6cf94e.timer`, service `run-rbe4844dbf16a467daf9c0cf0aa6cf94e.service` | VERIFIED (created); fire not yet observed |

## Result

- **Removed:** `/root/ollama-0.35.1-staging` (3.5G) and `/root/ollama-0.30.10-backup` (2.1G).
- **Space:** about 5.6G freed from the dirs, and about 5.5G taken by the safety tar, so `df` shows 140G used before and after (net zero until the tar is deleted). After deletion on 2026-11-11, about 5.6G is net reclaimed.
- **Ollama:** active, 0.30.10, 15 models after each removal. `/usr/local/bin/ollama`, `/usr/share/ollama` and the models dir were not touched.
- **Rollback:** `/root/ollama-dirs-removed-2026-11-04/ollama-dirs.tar`. Restore with `tar -C /root -xf /root/ollama-dirs-removed-2026-11-04/ollama-dirs.tar`. It is deleted automatically on 2026-11-11 03:00 by the timer above. To cancel: `systemctl stop run-rbe4844dbf16a467daf9c0cf0aa6cf94e.timer`.
- **Not in restic:** the tar is local only (same disk), so it protects against a mistaken removal but not disk loss.
- **Note:** `RESTORE.sh` and the 0.30.10 backup are gone from `/root` unless the tar is extracted. The tar is the only copy for 7 days.
