# TJRHQ disaster recovery gap assessment (2026-11-08, revision 2)

Status: read-only assessment. Revision 2 adds evidence and corrects claims from revision 1. No production file, service, timer, credential, backup, restore, repository check, remote inventory, stash, branch or alert state was changed or accessed.

## Labels

- **VERIFIED**: observed directly in this session. Source is given (file path and line, command, or journal line). Metadata only: no secret values, database contents, or stash contents were read.
- **INFERRED**: follows from verified facts plus a stated rule or assumption. The assumption is named.
- **UNKNOWN**: cannot be determined from local evidence. The evidence that would settle it is listed in §10.
- **DOCUMENTED**: stated in an existing repository document or report. Not re-run here.

Paths are absolute unless shown relative to the live checkout `/opt/starship-endeavour` (`main` at `9b7e35c9c` at the time of the run). The live checkout still has one modified tracked file (`core/mission-control/registry/mission-index.txt`) and one untracked file under `data/self-improvement/review/`. Head counts drift between runs because other sessions are active (202 local branches in revision 1, 203 in revision 2).

## 1. Executive summary

**Verdict: rebuild is possible, but only with three owner-held secrets and only from a backup set narrower than the running system. Several classes of state have no backup and no verified recovery route.**

Verified strengths:

- A nightly restic snapshot to Google Drive ran successfully on every night from 2026-11-03 to 2026-11-08 (journal, `starship-backup.service`). The latest snapshot ID in the journal is `625051d6`.
- The Supabase dump is taken every 72 hours and cached between runs, so every snapshot carries a dump at most about 71 hours old. The schedule holds in the journal (dumps on 10-28, 10-31, 11-03, 11-06).
- Infisical's Postgres database is dumped logically each night. Its container definitions are captured with `docker inspect`.
- The restic repository, the Infisical recovery env file and a compose copy are under `/root/private-knowledge`, which is in the backup path list (`deploy/starship-backup.sh:217`).

Verified weaknesses:

- The restic password and rclone token are excluded by design (`deploy/starship-backup.sh:43`; runbook line 29). Their custody depends on the owner's password manager. Whether that copy exists is UNKNOWN.
- At least five classes of persistent VM state are neither in the backup path list nor in git. They are listed in §4 with consequences.
- Git coverage is partial. Stash commits (21) are unreachable from any local branch, tag or remote-tracking ref. The bundle cannot carry them, and `.git` itself is not in the backup path list.
- The Infisical compose the runbook relies on is a reconstruction. The running containers reference a compose directory that does not exist on this VM. The repo copy and the private copy differ.
- Restore evidence is sampled integrity checks, a small file drill, and documented (not re-run) Infisical and Supabase restore tests.

Corrections to revision 1 are in §11. The main ones: the Infisical uploads volume is empty (0 files), so it is not a material loss; the compose project name is already set in the repo, so the earlier "set the project name" advice was wrong; the snapshot-count discrepancy is explained by retention (INFERRED, with a consistent model); and the Supabase RPO of "up to 72 hours" is supported by schedule evidence.

## 2. Method and restrictions

- Read the backup script (`deploy/starship-backup.sh`), the systemd units, the restore runbook, the integrity doc, the 2026-11-05 verification report, the Infisical README and compose file, and `.gitignore`.
- Ran read-only commands: `git` plumbing (`ls-files`, `for-each-ref`, `stash list`, `rev-list`, `rev-parse`, `check-ignore`, `log`), `docker inspect` and `docker volume inspect` (metadata only), `ls`/`stat`/`du`/`find -type f | wc -l` (existence, size, type, count), `systemctl list-timers`, `journalctl` (read only), `cmp`/`diff -q` (identity only), `gh pr view` (metadata).
- Names of environment variables in files were listed where the question required it. Values were not read or printed. `.restic-pass`, `rclone.conf`, `infisical-recovery.env`, `.infisical-auth.env`, `auth.json` (Vercel), and `gh hosts.yml` were checked for presence and mode only.
- Stash contents were not inspected. Stash metadata (SHA, parent SHAs, reachability) was.
- No `git bundle` was created. No `restic` command was run against any repository. No database was connected. No container was started, stopped or restarted. No gc, prune, stash or branch change was made.

## 3. Evidence table (claim → source)

| # | Claim | Label | Source |
|---|---|---|---|
| E1 | Backup path list: `data/self-improvement/review`, `outputs/delivery_ledger.txt`, `Missions/Engineering-Handoffs`, `.id-counters.json`, `platform-runtime/.infisical-auth.env`, `/etc/caddy`, `/etc/systemd/system`, `/opt/deploy-guard`, `/etc/sysstat`, `/etc/systemd/journald.conf.d`, `/root/private-knowledge`, `/var/spool/cron/crontabs`, `/root/starship-branches-*.bundle`, plus the staging directory | VERIFIED | `deploy/starship-backup.sh:206-219`, `:205` |
| E2 | `.env*` files under the repo are included, excluding `node_modules`, `.venv`, `.git`, `.next`, `chatterbox-venv` | VERIFIED | `deploy/starship-backup.sh:222-224` |
| E3 | Git bundle is `git bundle create --branches`, then verify | VERIFIED | `deploy/starship-backup.sh:144-145` |
| E4 | The restic password file is `/root/.restic-pass` and is not in the path list | VERIFIED | `deploy/starship-backup.sh:43`; path list `:206-219` |
| E5 | rclone binary and `gdrive2` remote; rclone config is not in the path list | VERIFIED | `deploy/starship-backup.sh:35,42`; `/root/.config/rclone/rclone.conf` exists, mode 0600 |
| E6 | Retention is `forget --keep-daily 7 --keep-weekly 4 --keep-monthly 3 --prune`, run only after a successful backup | VERIFIED | `deploy/starship-backup.sh:241-242` |
| E7 | Supabase dump runs when cached dump age ≥ 71 h (72 h minus 1 h grace) | VERIFIED | `deploy/starship-backup.sh:56-57,103` |
| E8 | Dump validity guard: size ≥ 1 MB and ≥ 100 TOC entries | VERIFIED | `deploy/starship-backup.sh:109` |
| E9 | Four data-excluded log tables | VERIFIED | `deploy/starship-backup.sh:51` |
| E10 | Nightly runs `finished OK` 2026-11-03 to 2026-11-08 | VERIFIED | journal, `starship-backup.service` |
| E11 | Snapshot saves in the journal window: `b3aaf9d4` (10-29), `a9de41c8` (10-30), `e90137e2` (10-31), `7214ce0d` (11-01), `577289c0` (11-02), `afa14ad1` (11-03), `4fb41b3e` (11-04), `3ab9464e` (11-05), `53418bf2` (11-06), `5e34d59f` (11-07), `625051d6` (11-08) | VERIFIED | journal |
| E12 | Restic printed `11 snapshots` after the 11-07 run and `12 snapshots` after the 11-08 run | VERIFIED (log line). Meaning as restic's snapshot count: INFERRED | journal |
| E13 | 2026-11-05 verification report: 10 snapshots after its run, PASS on a 1% sample | DOCUMENTED | `reports/vm-audit/backup-verification-20261105.md` |
| E14 | Supabase dumps on 10-28, 10-31, 11-03, 11-06 at cache age 71 h, sizes 38, 39, 39, 40 MB, TOC entries 1966, 1966, 1985, 1893 | VERIFIED | journal lines `supabase dump: N MB, M table-of-contents entries` |
| E15 | Supabase cache file mtime `2026-11-06 02:41:35`, size 42.7 MB | VERIFIED | `ls -la /var/lib/starship-backup/` |
| E16 | Weekly integrity timer installed, `NEXT Sun 2026-11-08 11:30 AEDT`; no journal entries yet | VERIFIED | `systemctl list-timers`; `journalctl -u starship-backup-integrity.service` returned no entries |
| E17 | PR #609 merged 2026-11-07T23:47:52Z; checks SUCCESS | VERIFIED | `gh pr view 609` |
| E18 | PR #610 (this document) open; 20 checks SUCCESS, none failing, one unnamed rollup entry with null status | VERIFIED | `gh pr view 610` at time of revision 2 |
| E19 | Infisical README: directory "never committed", lost in a disk cleanup on 2026-09-24, recovered 2026-10-04 from an authoring transcript | DOCUMENTED | `deploy/infisical/README.md:3-6`; commit `e218bd7c2` (2026-10-04) |
| E20 | Infisical compose sets `name: infisical` and joins external network `coolify` | VERIFIED | `deploy/infisical/docker-compose.yml:12,21,52-54`; commit `846b2aa31` (2026-10-09) |
| E21 | Running Infisical containers carry `config_files=/root/TJRHQ/deploy/infisical/docker-compose.yml` and `working_dir=/root/TJRHQ/deploy/infisical` | VERIFIED | `docker inspect` labels (metadata) |
| E22 | `/root/TJRHQ/deploy/infisical` does not exist | VERIFIED | `ls` error |
| E23 | `/root/private-knowledge/infisical-compose/` contains `docker-compose.yml`, `.env`, `db.env`; the compose is **not** byte-identical to the repo copy | VERIFIED | `cmp`/`diff -q` (identity only) |
| E24 | `infisical-recovery.env` exists in `/root/private-knowledge`, mode 600, header says it contains `ENCRYPTION_KEY` and `AUTH_SECRET` | VERIFIED (presence). Values not read. | `/root/private-knowledge/infisical-recovery.env`, file header comment |
| E25 | Runbook: restore order, required secrets and tests (2026-10-09) | DOCUMENTED | `knowledge/missions/starship-backup-restore-runbook.md:31-89` |
| E26 | Restic 0.16.4, rclone v1.75.1 installed | VERIFIED | `restic version`, `rclone version` |
| E27 | 21 stash commits; none contained by any local head, remote-tracking ref or tag | VERIFIED | `git for-each-ref --contains` per stash SHA |
| E28 | 19 of 21 stashes have a first parent contained by a ref; 21 of 21 have a second parent (index) not contained by any ref; 10 of 21 have a third parent (untracked) not contained by any ref | VERIFIED | `git rev-parse` and `git for-each-ref --contains` (metadata) |
| E29 | 57 commits are reachable from stashes but from no branch, tag or remote-tracking ref | VERIFIED | `git rev-list <stashes> --not --branches --tags --remotes` |
| E30 | 153 local branches have no `refs/remotes/origin/*` counterpart; 100 remote-tracking branches have no local branch | VERIFIED | `comm` on branch names |
| E31 | `.git` directory is not in any backup path; `find` excludes `.git` | VERIFIED | `deploy/starship-backup.sh:206-224` |
| E32 | `outputs/` is gitignored; `data/memory_graph.db`, `.cortex/memory.db` are gitignored | VERIFIED | `.gitignore:51,97,163`; `git check-ignore -v` |

## 4. Verified recovery-coverage inventory (Investigation 1)

Size and type come from `du`, `stat` and `find -type f`. "In backup" means explicitly included in the restic path list. Metadata only.

| Path | Exists now | Size, type | Explicit backup status | Git or other documented source | Consequence of losing this VM | Label |
|---|---|---|---|---|---|---|
| `outputs/` (whole directory) | Yes | 36 MB, directory, 21 regular files | **Excluded**, except `outputs/delivery_ledger.txt` (E1). Gitignored (E32). | None | Loss of operational logs, reports and state, including `command_bus.db` (a `.db` file, type not checked), `deadmans_switch_state.json`, `mission_intelligence.json`, `knowledge_utilisation.json`, `operating_patterns.json`, `readiness_trend.json`, `verification_engine.log` (27 MB), `deadmans_switch.log` (2.5 MB), `delivery_apply.log` (5.8 MB and dated copies) | VERIFIED (exists, excluded). Regeneration per file UNKNOWN. |
| `outputs/delivery_ledger.txt` | Yes | 8.7 KB, file | **Included** (E1) | None | Restored from latest snapshot | VERIFIED |
| `data/memory_graph.db` | Yes | 920 KB, SQLite-named file | **Excluded** (not in list; gitignored, E32) | None | Loss of memory graph store. Rebuildability UNKNOWN. | VERIFIED (exists, excluded) |
| `.cortex/memory.db` | Yes | 30 MB, regular file | **Excluded** (not in list; gitignored, E32). Named in `.gitignore:163`. | None | Loss of the memory database. Whether it can be rebuilt from source is UNKNOWN. | VERIFIED (exists, excluded) |
| `data/alert_state/` | Yes | 8 KB, directory, 2 files | **Excluded** | None | Loss of alert dedup state. Consequence of a fresh install: alerts may re-fire. | VERIFIED (exists, excluded). Consequence INFERRED. |
| `data/resilience-crosswalk/` | Yes | 12 KB, directory, 1 file | **Excluded** | None | Loss of audit trail file. | VERIFIED |
| `data/self-improvement/review/` | Yes | Directory | **Included** (E1, line 207) | Some files gitignored; untracked file present | Restored from latest snapshot | VERIFIED |
| `/etc/self-improvement/` | Yes | 8 KB, directory, 1 file (`dashboard.env`) | **Excluded** (not in path list, lines 206-219) | None | Dashboard service config lost. Secret content not read. | VERIFIED (exists, excluded) |
| `/data/coolify/` | Yes | 6.5 MB, directory, 59 files, subdirectories `applications`, `backups`, `databases`, `images`, `proxy`, `sentinel`, `services`, `source`, `ssh`, `ssl` | **Excluded** | None. Contains `source/.env` and dated copies (names only checked; contents not read). | Coolify configuration and any key material it holds are lost. The `coolify` Docker network (external to the Infisical compose, E20) is created by Coolify. | VERIFIED (exists, excluded). Role and key material UNKNOWN. |
| Docker volume `coolify-db` | Yes | 100 MB | **Excluded** (no Docker volume is in the path list) | None | Coolify database lost | VERIFIED (exists, excluded) |
| Docker volume `coolify-redis` | Yes | 492 KB | **Excluded** | None | Redis data lost | VERIFIED (exists, excluded) |
| Docker volume `infisical_infisical-db` | Yes | 84 MB, mounted at `/var/lib/postgresql/data` | **Excluded as a volume**. Logical dump included (`deploy/starship-backup.sh:130`). | Logical dump restore (runbook §4) | Physical volume lost. Logical dump is the recovery route. | VERIFIED |
| Docker volume `infisical_infisical-uploads` | Yes | **0 regular files**, 4 KB directory | **Excluded** | None | Negligible. No uploads present. | VERIFIED (metadata: file count 0). Revision 1 overstated this. |
| Docker volume `infisical_infisical-redis` | Yes | 12 MB, mounted at `/data` | **Excluded** | None | Redis contents lost. Whether it holds state that matters is UNKNOWN. | VERIFIED (exists, excluded). Role UNKNOWN. |
| Caddy ACME storage `/var/lib/caddy` | Yes | 164 KB, 18 files | **Excluded** | None | Certificates and ACME account re-issued on the new VM. Rate-limit risk if repeated. | VERIFIED (exists, excluded). Rate-limit risk INFERRED. |
| Caddy `/root/.local/share/caddy` | Yes | 44 KB, 6 files | **Excluded** | None | As above | VERIFIED |
| Caddy `/root/.config/caddy` | Yes | 16 KB, 1 file | **Excluded** | None | As above | VERIFIED |
| `/etc/caddy` | Yes | 84 KB, 14 files | **Included** (E1, line 212). Repo copy `deploy/caddy/Caddyfile.v3` byte-identical to live `Caddyfile` (`cmp`). | Git | None | VERIFIED |
| `/etc/systemd/system` | Yes | Directory | **Included** (E1, line 213) | `deploy/*.service` tracked in git | None | VERIFIED |
| `/root/private-knowledge` | Yes | 4.1 MB, 13 files | **Included** (E1, line 217) | None | Restored from latest snapshot | VERIFIED |
| `/root/.restic-pass` | Yes | Mode 0600, root | **Excluded by design** (E4) | Password manager (owner). Custody UNKNOWN. | Backup unreadable | VERIFIED (exists, excluded) |
| `/root/.config/rclone/rclone.conf` | Yes | Mode 0600, root | **Excluded by design** (E5) | Re-authorise with owner Google account and OAuth client (runbook §1) | Remote unreachable until re-authorised | VERIFIED (exists, excluded) |
| `/root/.ssh/authorized_keys` and `.bak-*` copies | Yes | Mode 0600 | **Excluded** (`/root/.ssh` not in path list) | Owner's SSH keys elsewhere (UNKNOWN) | Lost keys: access to new VM depends on owner key | VERIFIED (exists, excluded) |
| `/root/.config/gh/hosts.yml`, `config.yml` | Yes | Mode 0600 | **Excluded** | Re-authenticate with owner GitHub login | Loss of `gh` auth, not of repo data | VERIFIED (exists, excluded) |
| `/root/.local/share/com.vercel.cli/auth.json` | Yes | Mode 0600 | **Excluded** | Re-login with owner Vercel account | Loss of Vercel CLI auth | VERIFIED (exists, excluded) |
| `/root/.supabase/telemetry.json`, `traces/` | Yes | Mode 0600 | **Excluded**. Telemetry only. | Not needed for recovery | None | VERIFIED |
| Git stashes (21 commit objects) | Yes | refs/stash, 21 entries | **Not in bundle** (E3 uses `--branches`). `.git` not in path list (E31). | None | Total loss of 57 stash-only commits (E29). Their base commits are on branches for 19 of 21 (E28). | VERIFIED |
| Local branches with no remote-tracking counterpart (153) | Yes | Local heads | **In bundle** (E3, `--branches`) | Bundle only. If the bundle is lost, no other copy. | Loss of unpushed branch history | VERIFIED (count). Pushed status per branch UNKNOWN. |
| Remote-tracking branches with no local branch (100) | Yes | Remote refs | **Not in bundle** (`--branches` excludes remotes) | GitHub | Recoverable from GitHub if the branch still exists there | VERIFIED (count). Existence on GitHub not checked (remote inventory forbidden). |
| Local tags (108) | Yes | Refs | **Not in bundle** (`--branches` excludes tags) | GitHub, if pushed. Which are pushed: UNKNOWN. | Loss of unpushed tags | VERIFIED (count). Push status UNKNOWN. |
| Uncommitted tracked change `core/mission-control/registry/mission-index.txt` | Yes | Working-tree modification | **Excluded** (not in path list; not in git) | None | Loss of that change | VERIFIED (`git status`) |
| Source, tracked docs, `knowledge/`, `deploy/` | Yes | Tracked | Not needed in backup | GitHub, and the bundle for local branches | Re-clone | VERIFIED |
| Python venvs | Yes | Gitignored | **Excluded by design** (script comments, `deploy/starship-backup.sh:155-165`). `pip freeze`, python version and `pyvenv.cfg` are captured instead. | Rebuild from freeze | Rebuild needed, with the extra index URL noted in the script | VERIFIED |
| Docker images | Registry | n/a | **Excluded by design** (runbook line 29) | Re-pull | Re-pull | DOCUMENTED |

## 5. Infisical recovery dependencies (Investigation 2)

**Running deployment (metadata only, VERIFIED):**

- Three containers: `infisical-infisical-1`, `infisical-db-1` (healthy), `infisical-redis-1` (healthy). Project label `infisical`. Container start time 2026-10-19 13:24 UTC.
- Mounts: `infisical_infisical-uploads` at `/app/backend/uploads` (0 files); `infisical_infisical-db` at `/var/lib/postgresql/data` (84 MB); `infisical_infisical-redis` at `/data` (12 MB). All three are local-driver named volumes.
- Compose labels reference `/root/TJRHQ/deploy/infisical/docker-compose.yml`, which does not exist (E21, E22).
- The `coolify` network is declared `external: true` and "exists today; Infisical is attached to it. Do not remove it" (E20, `docker-compose.yml:53-54`). The Infisical app's Traefik labels route through it (`traefik.docker.network=coolify`).

**Compose files available (VERIFIED):**

- Repo: `deploy/infisical/docker-compose.yml` (tracked, commits `e218bd7c2` 2026-10-04 and `846b2aa31` 2026-10-09, "pin image digest, set project name, match running DISABLE_SIGNUP default").
- Private copy: `/root/private-knowledge/infisical-compose/docker-compose.yml` (2212 bytes). The repo copy is 4085 bytes. The two are **not identical** (`diff -q`).
- Which file matches the running containers byte-for-byte: UNKNOWN. The README says the repo copy was "rebuilt from the original authoring transcript and checked against the running containers" (`deploy/infisical/README.md:5-7`). The private copy's env comments say the env was "extracted from the running container (docker inspect)".
- The repo's `.env` is absent (`deploy/infisical/` contains only `.env.example`, `README.md`, `docker-compose.yml`). The private copy has a 149-byte `.env` and a 169-byte `db.env`.

**Documented versus tested (VERIFIED where marked):**

| Step | Documented | Tested | Source |
|---|---|---|---|
| Compose recreated from private copy | Yes | No evidence of a fresh-host run | runbook §4.1 |
| Restore `infisical-db.dump` with `pg_restore` | Yes | "Tested 2026-10-09: all 100 secrets decrypted to values identical to live" | runbook line 69. DOCUMENTED, not re-run. |
| `ENCRYPTION_KEY` and `AUTH_SECRET` from recovery env | Yes | Same test | runbook §4.3 and line 69. DOCUMENTED. |
| `.infisical-auth.env` restored to `platform-runtime/` | Yes | No evidence of a service login after restore | runbook §4.4 |
| Services start after Infisical | Yes | No evidence | runbook §6 |

**Recovery steps that depend on files found only on this VM:**

1. The Infisical compose in the runbook is found in `/root/private-knowledge`, which is in the restic path list. Access to it therefore needs the restic password. This is a dependency on off-VM custody, not on VM-local files.
2. The Infisical volume `infisical_infisical-db` has no physical copy in backup. Only the logical `pg_dump` (`deploy/starship-backup.sh:130`) is captured. The dump uses `pg_dump --format=custom` of `$POSTGRES_DB`. Logical restore is the only route.
3. The `coolify` Docker network must exist before `docker compose up` (E20). It is created by Coolify. On a replacement VM, either Coolify is restored first, or `docker network create coolify` is run by hand. Neither step is documented as tested.
4. The running containers' compose label path (`/root/TJRHQ/...`) is stale. Recovery should use `docker compose -p infisical -f <restored compose>` with the restored file. Using the stale label path will fail, and there is no test of this.
5. Redis `requirepass` value comes from compose interpolation of `${REDIS_PASSWORD}` (`docker-compose.yml`, `command:` line). Names only were checked. If the `.env` supplying it is missing, Redis is expected to start without the intended password or fail (INFERRED from compose interpolation rules; not tested).

**Deviation from revision 1:** Revision 1 said the compose project name must be set explicitly. That is wrong: `deploy/infisical/docker-compose.yml:12` already sets `name: infisical` (commit `846b2aa31`). The stale part is only the container label path (E21).

## 6. Git recovery coverage (Investigation 3)

**Object classes and survival on VM loss:**

| Class | Count | In bundle? | Other copy | Survives VM loss? | Label |
|---|---|---|---|---|---|
| Local branch heads | 203 at revision 2 (202 earlier) | Yes (`--branches`) | GitHub, if pushed (153 have no remote-tracking ref) | Yes, if bundle and restic both survive | VERIFIED |
| Remote-tracking branches with no local branch | 100 | No | GitHub | Yes via GitHub | VERIFIED (count). GitHub existence UNKNOWN. |
| Tags | 108 local | No | GitHub, if pushed. Push status UNKNOWN. | Unknown | VERIFIED (count) |
| Stash commits | 21 | No (refs/stash not included) | None | **No** | VERIFIED (E27) |
| Stash-only commits, including index and untracked parents | 57 | No | None | **No** | VERIFIED (E29) |
| Base commit of each stash (first parent) | 21 | Yes for 19 (reachable from a branch, E28) | Branch | Yes for 19 | VERIFIED |
| Index commit of each stash (second parent) | 21 | No (not contained by any ref) | None | **No** | VERIFIED (E28) |
| Untracked commit of each stash (third parent, 10 of 21) | 10 | No | None | **No** | VERIFIED (E28) |
| Uncommitted working-tree change | 1 tracked file, 1 untracked file | No | None | **No** | VERIFIED (`git status`) |

**Notes:**

- The bundle command is `git bundle create --branches`. `--branches` covers `refs/heads/*` only. Stashes, tags and remote-tracking refs are excluded by definition.
- Stash objects are not reachable from any ref, so `git bundle` cannot include them. The `.git` directory is not in the restic path list (E31). Stash objects exist only in the VM's `.git` store.
- Revision 1 said "stashes are not in the bundle and not in restic beyond what the live tree contains". That was correct for the bundle but understated the restic side: restic does not include `.git` at all, so stash objects are not in restic in any form.
- Revision 1 said "first 10 of 21" stashes were checked. All 21 were checked in revision 2 (E27).
- Stash contents were not inspected, per the restriction. Whether any stash holds data not present in a branch is UNKNOWN. The stash messages in `git stash list` are metadata and show names such as `wsp before endeavour-27 checkout` and `wip-mobilecommandbar-verify-b3-run2`. They do not show contents.

## 7. Recovery credentials and external dependencies (Investigation 4)

Classification uses documented routes and file-presence metadata only. No values were read, printed, fingerprinted or compared.

### 7.1 Strictly required to access the encrypted backup

| Item | Custody | Route | Label |
|---|---|---|---|
| Restic repository password (`/root/.restic-pass`) | Owner's password manager (runbook line 33, DOCUMENTED) | None other than custody | Custody UNKNOWN |
| Google OAuth client ID and secret for `gdrive2` | Owner's password manager (runbook line 39, DOCUMENTED) | Recreate a client only if the owner account can still see the repo. Under `drive.file` scope, a new client cannot see files created by the old one (runbook line 45, DOCUMENTED). | Custody UNKNOWN |
| Owner's Google account access (to authorise the rclone token and reach the Drive repo) | Owner | Owner login | Not verifiable from the repo |

### 7.2 Re-authorisable through an owner-controlled account

| Item | Route | Label |
|---|---|---|
| rclone `gdrive2` token | `rclone authorize drive` with owner Google account and OAuth client (runbook §1) | DOCUMENTED |
| GitHub CLI auth (`gh hosts.yml`) | Owner GitHub login. Repo is public (memory note). Clone does not need auth; push does. | VERIFIED (file presence), route INFERRED |
| Vercel CLI auth (`auth.json`) | Owner Vercel login | VERIFIED (file presence), route INFERRED |
| SSH access to the new VM | Owner SSH key. `authorized_keys` is not backed up (E1 excludes `/root/.ssh`). | VERIFIED (exclusion) |
| Caddy ACME account and certificates | Re-issued by Let's Encrypt on first start | VERIFIED (storage present), route INFERRED |
| Telegram bot tokens | Re-issue through the bot platform with owner account | INFERRED (no evidence checked) |
| Supabase DB password, API keys | Owner Supabase dashboard (INFERRED: standard capability, not verified here) | INFERRED |

### 7.3 Potentially recoverable after backup access

| Item | Source inside the backup | Dependency | Label |
|---|---|---|---|
| Infisical `ENCRYPTION_KEY`, `AUTH_SECRET` | `/root/private-knowledge/infisical-recovery.env` (E24) | Requires the restic password (7.1) | VERIFIED (presence), DOCUMENTED (tested 2026-10-09) |
| Infisical DB password, Redis password | `/root/private-knowledge/infisical-compose/db.env` and `.env` (names checked) | Requires the restic password | VERIFIED (presence) |
| Service secrets (Supabase service and DB URLs, Telegram tokens, API keys) | `.env` files in the repo tree (E2) and inside the Infisical database | Restic password, and `ENCRYPTION_KEY` to decrypt the Infisical database | VERIFIED (path inclusion). Decryption UNKNOWN beyond the 2026-10-09 test. |
| `.infisical-auth.env` (machine identity for services) | `platform-runtime/.infisical-auth.env` (E1) | Restic password. Machine identity validity on a new host UNKNOWN. | VERIFIED (inclusion) |
| Supabase vault secrets | Excluded from the dump (runbook line 28). Re-enter from Infisical. | Infisical restored first | DOCUMENTED |

### 7.4 Dependencies with no verified recovery route

| Dependency | Why no route | Label |
|---|---|---|
| Coolify key material and encrypted configuration (`/data/coolify/source/.env` and dated copies; `coolify-db` volume) | Not in backup. If Coolify encrypts stored values with a key held only in that `.env`, those values are lost. Whether Coolify does this is UNKNOWN. | VERIFIED (exclusion). Encryption behaviour UNKNOWN. |
| Vercel environment variable values | Not in backup. Vercel stores values server-side; whether they can be read back depends on type. | UNKNOWN |
| GitHub Actions secrets and repository settings (branch protection, webhooks) | Not in repo. Usually write-only. | UNKNOWN |
| Stash-only commits (57) | Not in any ref or backup (§6) | VERIFIED |
| Unpushed local-only branches (153, pushed status UNKNOWN) | Only in the bundle and restic | VERIFIED (count) |
| Supabase Storage object binaries | Outside `pg_dump` (`--schema=storage` dumps metadata only). Storage sits in Supabase cloud. If the project is lost, no route is documented. Whether the project holds binaries is UNKNOWN. | INFERRED (binaries), UNKNOWN (contents) |
| Redis contents (both Redis volumes) | Not in backup. Role UNKNOWN. | UNKNOWN |
| Google Drive account itself (2FA, recovery options, quota) | Not in repo | UNKNOWN |

**Possible fallback not in revision 1:** the older restic repository `rclone:gdrive:starship-backups` (rclone shared client) is kept until at least 2026-10-24 and only on the Captain's explicit yes (runbook lines 46-47, DOCUMENTED). Whether it still exists, and whether it holds snapshots that the new repo lacks, is UNKNOWN. Checking it would require remote access, which this assessment does not do.

## 8. Evidence reconciliation (Investigation 5)

### 8.1 The 10-versus-11 snapshot discrepancy

- The 2026-11-05 verification report (DOCUMENTED) expected 11 snapshots and found 10 after the run. Its explanation was that an older snapshot aged out, but it did not identify which.
- Local journal (VERIFIED, E11, E12) shows saves on each night from 10-29 to 11-08, and restic printed `11 snapshots` after the 11-07 run and `12 snapshots` after the 11-08 run.
- Retention is `keep-daily 7` with `keep-weekly 4` and `keep-monthly 3` (E6). Under the simplest reading, each night keeps the newest snapshot for each of the most recent 7 calendar days.
- Applying that reading to the journal saves and the report's listed older snapshots (Oct 10, 18, 25 — DOCUMENTED):
  - 11-04: window is 10-29 to 11-04. The 10-29 snapshot is 7th and kept. Total 10.
  - 11-05: adding `3ab9464e` makes 11. The 10-29 snapshot is now 8th and falls out. Total **10**. This matches the report.
  - 11-06: adding `53418bf2`. The 10-30 snapshot falls out. Total 10.
  - 11-07: adding `5e34d59f`. The 10-31 snapshot is 8th, but it is the latest snapshot of October and is kept by `keep-monthly`. Total **11**. This matches the journal.
  - 11-08: adding `625051d6`. Total **12**. This matches the journal.
- The report's gap list (Oct 10, 18, 25, 30, 31, then daily from Nov 1) is consistent with this model: 10-29 is the only save in the window that is missing, and it is missing because it aged out.

**Conclusion:** the discrepancy is explained by retention, not by a failed write. Label: **INFERRED** (the journal does not name removed snapshots). The model is consistent with all four counts the journal and report provide. The explicit removal list is not in the local journal because the script pipes restic's forget output through `tail -15`.

**Is the current repository 12 snapshots?** The local journal's last count is 12 (11-08). The integrity doc (DOCUMENTED) records 12 from a manual check. Neither is a remote observation. The current remote count is UNKNOWN until someone with access lists the repository.

### 8.2 Sampled integrity versus full recovery testing

| Evidence | What it proves | What it does not prove | Label |
|---|---|---|---|
| `restic check --read-data-subset=1%` on 11-05 (DOCUMENTED) | Repository structure and one pack readable | Other 99% of packs | DOCUMENTED |
| `restic check --read-data-subset=1/20` on 11-08 (DOCUMENTED) | Repository structure and about 5% of packs readable (4 of 52 in the doc) | Full readability | DOCUMENTED |
| Three-file drill on 11-08 (DOCUMENTED) | Three files restored and compared to live | Any directory tree, any database restore | DOCUMENTED |
| Infisical restore test on 10-09 (DOCUMENTED) | 100 secrets decrypted to identical values | That the current live Infisical matches the backup at 11-08 | DOCUMENTED |
| Supabase restore test on 10-09 (DOCUMENTED, 166 tables, 163 identical counts, 3 high-churn tables 2-4 rows behind) | A scratch restore works | Restore on current schema or on a clean host | DOCUMENTED |
| Weekly integrity timer (E16) | Nothing yet | First run pending at 11:30 AEDT on 11-08 | VERIFIED (timer), outcome UNKNOWN |

**Conclusion:** no full-snapshot restore to a clean directory has been recorded. No full-data check (`--read-data`) has been recorded. Revision 1's wording "restore evidence is sampled" is correct, but it should say "no full restore has been recorded at all" rather than "has been tested in part".

### 8.3 Supabase recovery-point objective

**Claim:** up to 72 hours of Supabase data loss.

**Supported by:**

- Schedule (E7): dump only when cached age ≥ 71 h. Cache stays otherwise.
- Journal (E14): dumps on 10-28, 10-31, 11-03, 11-06 at age 71 h. Between them, 23 h and 47 h cache ages are logged. The cadence holds.
- Current cache mtime (E15): 2026-11-06 02:41:35. Next dump due about 2026-11-09 02:40 AEDT.
- Each nightly snapshot re-adds the cached dump (E7), so the newest snapshot holds a dump at most about 71 h old. Restic deduplicates unchanged dumps.

**Not supported or limited by:**

- The claim is about the dump's age, not about the Supabase project. Data written after the last dump and before the VM is lost is lost.
- Four log tables have data excluded (E9). They are regenerable but are not "recovered" by the dump.
- Vault contents and Storage object binaries are not in the dump at all (§7.4). They are not covered by any RPO.
- TOC entry counts changed from 1985 (11-03) to 1893 (11-06), a drop of 92 (E14). The cause is UNKNOWN. The guard in E8 (≥ 100 entries) still passes. A schema change, table removal or cleanup could explain it. The 2026-09-01 "dead-tables-pre-drop" backup file exists in the repo (`core/infrastructure/supabase/backups/`), so a drop is plausible, but it is not verified. The evidence needed is a comparison of the two dumps' TOC lists, which this assessment did not run.

**Verdict:** "up to 72 hours" for dumped database content is supported. Claims about storage binaries, vault contents or unlogged writes are not.

## 9. Top five recovery gaps, ranked by impact (revised)

Impact ranking considers: how much of the rebuild is blocked, how many items are affected, whether a route exists, and how likely it is to be missed.

1. **Off-VM custody of the three gating secrets is unverified (restic password, Google OAuth client, Infisical `ENCRYPTION_KEY` and `AUTH_SECRET`).** Everything depends on them, and the repo cannot show they exist in the password manager. Evidence needed: owner confirmation of custody, not values. Label: UNKNOWN custody, VERIFIED dependency.
2. **Stash-only commits (57) and unpushed local branches (153, pushed status UNKNOWN) survive only on this VM and in the bundle.** Stashes have no route at all. Unpushed branches have only the bundle and restic. Label: VERIFIED.
3. **Operational state outside the backup path list.** Largest by consequence: `outputs/` (36 MB, 21 files, 1 of 21 backed up), `.cortex/memory.db` (30 MB), `data/memory_graph.db` (920 KB), `data/alert_state`, `/etc/self-improvement`, Coolify (6.5 MB plus 100 MB database volume, key material in `source/.env`). Label: VERIFIED exclusion. Regeneration per item UNKNOWN.
4. **Infisical recovery depends on a reconstructed compose, a stale label path, and an uncertain `coolify` network.** The repo compose was rebuilt from transcript after a 2026-09-24 loss (E19). The private compose differs from the repo copy (E23). Containers reference a path that does not exist (E21, E22). The `coolify` network is external (E20). Logical restore is the only Infisical route (no physical copy). Label: VERIFIED structure, DOCUMENTED test.
5. **No full restore has ever been recorded, and the first weekly integrity check has not run yet.** Integrity samples are small. The Supabase and Infisical tests are documented from 10-09. Label: DOCUMENTED and VERIFIED (timer).

**Revision 1 gap ranking, for comparison:** 1 credentials, 2 uncaptured state, 3 Infisical, 4 git coverage, 5 restore evidence. Revision 2 keeps the same five items but changes the order of 2 and 4 because stash and unpushed-branch loss are now quantified and have no route.

## 10. Unresolved questions and evidence needed

| # | Question | Evidence that would settle it | Who can supply it | Access needed |
|---|---|---|---|---|
| Q1 | Do the restic password, the Google OAuth client ID and secret, and Infisical `ENCRYPTION_KEY`/`AUTH_SECRET` exist in the owner's password manager, and are they current? | Owner confirmation of item presence and last-updated date (no values) | Owner | None from VM |
| Q2 | Does the current remote repository hold 12 snapshots, and which dates? | `restic snapshots --compact` on the remote repo | Owner, or an operator with access | Remote access (forbidden in this task) |
| Q3 | Which snapshot was removed on 11-05 and 11-06? | Remote snapshot list, compared with journal IDs in E11 | As Q2 | As Q2 |
| Q4 | Does the private `infisical-compose/docker-compose.yml` or the repo copy match the running containers? | Compare each to `docker inspect` output for image digest, env names and mounts | Operator on this VM | Read-only `docker inspect` on named containers, metadata |
| Q5 | What do the Supabase dumps' TOC lists differ by (92 entries, 11-03 to 11-06)? | `pg_restore --list` on the two cached dumps. Requires the cache files, which are local. | Operator on this VM | Local read of dump TOC, not contents |
| Q6 | Are the 57 stash-only commits and the 153 unpushed branches reachable from any remote? | GitHub branch and tag listing | Owner, or GitHub admin | Remote inventory (forbidden in this task) |
| Q7 | Do the `coolify` Docker network and Coolify's key material survive a rebuild? | Coolify documentation, and whether `source/.env` is required to decrypt `coolify-db` | Owner, plus the Coolify product docs | Documentation only |
| Q8 | Does the Infisical uploads volume matter? | Already answered: 0 files | — | — |
| Q9 | Are any Redis volume keys required after restore? | Application code that reads from Redis at startup | Code review | None |
| Q10 | Does the old `gdrive:starship-backups` repo still exist, and does it hold snapshots absent from the new repo? | Remote listing | Owner | Remote access (forbidden) |
| Q11 | Has the first weekly integrity run passed? | `journalctl -u starship-backup-integrity.service` after 11:30 AEDT on 11-08 | Operator on this VM | Read-only journal access |
| Q12 | Is SEC-01 administratively closed in the form stated? | The risk-acceptance record referenced by commit `8d44f1cdd` | Owner | Repo read |
| Q13 | Does Supabase Storage hold binaries, and are they needed? | Supabase project storage listing | Owner | Supabase dashboard |
| Q14 | Do Vercel environment values exist and can they be read back or re-entered? | Vercel project settings | Owner | Vercel dashboard |

## 11. Corrections to revision 1

| Revision 1 claim | Status | Correction |
|---|---|---|
| "The last eight runs logged `finished OK`" | Corrected in rev 1 | Six runs, 2026-11-03 to 2026-11-08 (E10). |
| "The Infisical uploads volume is not backed up at all" (presented as a material gap) | **Downgraded** | The volume has 0 regular files (§4). Not backed up, but not material. |
| "Infisical compose project name must be set explicitly" | **Wrong** | `name: infisical` is already set (E20). Only the stale container label path matters (E21, E22). |
| "The runbook restores from the private compose; that path works in principle" | **Overstated** | The private copy is not byte-identical to the repo copy (E23). The repo copy was reconstructed from transcript (E19). Which matches the running containers is UNKNOWN (Q4). |
| "Stashes are not in the bundle and not in restic beyond what the live tree contains" | **Restated** | Stash objects are unreachable from any ref (E27). `.git` is not in restic at all (E31). Stash objects exist only on the VM. |
| "First 10 of 21 stashes checked" | **Extended** | All 21 checked (E27). |
| "Tags recoverable from GitHub if pushed" | **Narrowed** | Push status of 108 tags is UNKNOWN. |
| "Snapshot count anomaly: which one was pruned is UNKNOWN" | **Partly resolved, labelled INFERRED** | The 10-29 snapshot aged out on 11-05 (§8.1), and 10-30 on 11-06. |
| "Restore evidence is sampled" | **Restated** | No full restore is recorded at all (§8.2). |
| "Supabase RPO up to 72 h" | **Supported**, with limits | §8.3 explains what is and is not covered. |
| "`/etc/self-improvement/dashboard.env` not backed up" | **Confirmed** | Directory exists, 1 file (§4). |
| "`outputs/` 19 of 20 not backed up" | **Corrected** | 21 regular files, 36 MB, only `delivery_ledger.txt` included. |
| "Caddy ACME storage not backed up" | **Confirmed**, with sizes | 164 KB, 44 KB, 16 KB (§4). |
| "Coolify data not backed up" | **Confirmed**, with sizes and the `coolify` network dependency | 6.5 MB plus 100 MB database volume, and key material in `source/.env` (E20, §4, §7.4). |
| "Google OAuth client and password manager custody" | **Unchanged** | Still UNKNOWN (Q1). |
| "PR #609 merged, CI green" | **Verified** | E17. |
| "SEC-01 administratively closed" | **Not verified** | Commit title only (Q12). |

## 12. Replacement-VM recovery sequence (revised)

Preconditions (owner, outside the VM): restic password, Google OAuth client ID and secret, Infisical `ENCRYPTION_KEY` and `AUTH_SECRET` (the last two are also in the backup, once the restic password is available). Owner's SSH key for the new host. Owner's GitHub, Vercel and Supabase accounts.

1. Provision Linux with Docker, `restic` 0.16+ and `rclone` 1.75+ (E26, runbook line 35).
2. Create the `gdrive2` remote with the owner's OAuth client and `drive.file` scope (runbook §1). Confirm with `restic ... snapshots`. **Note:** this lists snapshots remotely, so it is a remote operation for the new VM, not for this assessment.
3. Restore the latest `starship-nightly` snapshot to a mode-700 directory (runbook §2).
4. Clone from the restored bundle and check out `main` (runbook §3). Add `origin` and fetch. This recovers remote-tracking refs and pushed tags. It does **not** recover stashes (§6) or unpushed tags.
5. Restore `/etc/systemd/system`, `/etc/caddy`, `/root/private-knowledge` and `.env` files to their paths. Restore `/root/.restic-pass` and `rclone.conf` from the password manager. Do not restore them from the snapshot.
6. Create or confirm the external `coolify` Docker network (§5, E20). Restore Coolify first if it is in use.
7. Start Infisical from the restored compose, with the working directory set to the restored path. Do not rely on the stale label path. Start `db` and `redis`, restore `infisical-db.dump` with `pg_restore`, then start the app (runbook §4). Confirm `ENCRYPTION_KEY` matches the value in the password manager before trusting the restored secrets.
8. Restore `.infisical-auth.env` to `platform-runtime/`. Verify a service login. This step is not tested in the runbook (§5).
9. Supabase: create or reuse a project. Enable extensions, create roles, restore `supabase.dump`, re-create cron jobs, re-enter vault secrets from Infisical (runbook §5, DOCUMENTED).
10. Start Caddy (re-issues ACME certificates, §4), model-router, command-centre, LCARS, Telegram bots and self-improvement services in dependency order, after Infisical.
11. Re-link Vercel (`vercel link`), re-enter any missing Vercel env values, re-enter GitHub Actions secrets.
12. Restore `outputs/` and `data/` items from the snapshot where they are included. Accept the loss of the items in §4 that are excluded.
13. Re-enable `starship-backup.timer` and `starship-backup-integrity.timer`. Confirm one nightly and one weekly run complete before calling the rebuild done.

**Expected loss without further work:** stash-only commits (57); pushed status of unpushed branches (UNKNOWN); tags not pushed (UNKNOWN); `outputs/` except the delivery ledger; `data/memory_graph.db`; `.cortex/memory.db` (unless rebuildable); `data/alert_state`; `/etc/self-improvement/dashboard.env` (content recovery requires owner); Coolify state and key material; Redis contents; Caddy certificates (re-issued); Supabase changes since the last dump (up to about 71 h); Supabase vault contents and Storage binaries (unless re-entered or reachable); Vercel env values; GitHub Actions secrets; uncommitted working-tree changes.

## 13. Existing protections (revised)

| Protection | Evidence | Label |
|---|---|---|
| Nightly encrypted off-box restic snapshot | E10, journal | VERIFIED |
| Retention, 7 daily / 4 weekly / 3 monthly, prune after success | E6 | VERIFIED (code). Behaviour inferred from §8.1. |
| Supabase dump with cache and 72 h cadence | E7, E14 | VERIFIED |
| Dump validity guard | E8 | VERIFIED (code) |
| Infisical logical dump and container definitions | `deploy/starship-backup.sh:130,139` | VERIFIED (code) |
| Git bundle with `bundle verify` | E3 | VERIFIED (code). Coverage §6. |
| Failure alerting via `OnFailure=alert-on-failure@` | `deploy/starship-backup.service` | VERIFIED (unit) |
| Lock contention now fails (exit 75) | `deploy/starship-backup.sh:82` | VERIFIED (code) |
| Weekly sampled integrity check, first run pending | E16 | VERIFIED (timer), outcome UNKNOWN |
| Infisical restore test, 10-09 | E25 | DOCUMENTED |
| Supabase restore test, 10-09 | E25 | DOCUMENTED |
| Caddyfile in repo identical to live | `cmp` | VERIFIED |
| Installed backup script identical to repo script | `cmp /opt/starship-backup/backup.sh` against the repo file; the two were compared in revision 1 | VERIFIED (revision 1) |
| `.gitignore` covers `.env`, venvs, `outputs/` | `.gitignore:7-24,51` | VERIFIED |

## 14. Recommendations (for owner decision and later work)

These are recommendations only. None was applied.

**Owner decisions:**

1. Confirm custody of the restic password, OAuth client and Infisical keys (Q1).
2. Decide whether to add a second backup destination (Gap 1 and §7.3).
3. Decide what to do with the 21 stashes and 153 unpushed branches (push, keep the bundle, or drop). Decision affects shared state, so it is the owner's.
4. Decide whether `outputs/`, `.cortex/memory.db`, `data/memory_graph.db`, `data/alert_state`, `/etc/self-improvement` and Coolify state should be backed up. Decide RPO for Supabase (the current 72 h is a deliberate egress saving).

**Technical work (separate authorisation):**

1. Add the excluded persistent paths in §4 to the backup, after the owner's decision in item 4.
2. Capture stash objects and unpushed tags, for example with a separate bundle that includes `refs/stash` and tags, or `git format-patch` per stash.
3. Record the compose file that matches the running containers (Q4). Make the repo compose and the private compose the same, or name one as authoritative.
4. Add a runbook step that checks the external `coolify` network exists before Infisical starts.
5. Run one full restore of the latest snapshot to a scratch directory and diff it against the live tree. Run `restic check --read-data` at least once on the full repository, when the owner authorises remote access.
6. Add a success marker or alert for the weekly integrity unit (`docs/operations/restic-backup-integrity.md:48`).
7. Record the snapshot removals in the journal. Change the script so `forget` output is not truncated by `tail -15`.
8. Explain the 92-entry TOC drop (Q5) before relying on the Supabase dump in a rebuild.
9. Verify the first weekly integrity run (Q11).

## 15. Limitations

- All "VERIFIED" statements are about this VM at the time of the run. No remote state was observed.
- The retention model in §8.1 is an inference from the policy and the journal. It is not a remote observation.
- Stash contents, database contents, secret values and credential fingerprints were not read.
- No restore has been run in this assessment. Documented tests are reported as DOCUMENTED.
- Head counts (branches, tags, stashes) changed during the investigation because other sessions were active. Figures are as observed at the time noted.
