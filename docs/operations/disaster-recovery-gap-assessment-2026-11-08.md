# TJRHQ disaster recovery gap assessment (2026-11-08, revision 4)

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
| E16 | Weekly integrity timer installed, `NEXT Sun 2026-11-08 11:30 AEDT`. **Corrected: the first run completed 11:30:20–11:30:48 AEDT on 11-08 with "no errors were found" (§16).** | VERIFIED | `systemctl list-timers`; `journalctl -u starship-backup-integrity.service` (11-08 11:30) |
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
| `outputs/` (whole directory) | Yes | 36 MB, directory, 21 regular files | **Excluded**, except `outputs/delivery_ledger.txt` (E1). Gitignored (E32). | None | Loss of operational logs, reports and state, including `command_bus.db` (a `.db` file, type not checked), `deadmans_switch_state.json`, `mission_intelligence.json`, `knowledge_utilisation.json`, `operating_patterns.json`, `readiness_trend.json`, `verification_engine.log` (27 MB), `deadmans_switch.log` (2.5 MB), `delivery_apply.log` (413 KB; the 5.8 MB file is the dated copy `delivery_apply.log-20261108`, corrected §16) | VERIFIED (exists, excluded). Regeneration per file UNKNOWN. |
| `outputs/delivery_ledger.txt` | Yes | 8.7 KB, file | **Included** (E1) | None | Restored from latest snapshot | VERIFIED |
| `data/memory_graph.db` | Yes | 920 KB, SQLite-named file | **Excluded** (not in list; gitignored, E32) | None | Loss of memory graph store. Rebuildability UNKNOWN. | VERIFIED (exists, excluded) |
| `.cortex/memory.db` | Yes | 30 MB, regular file | **Excluded** (not in list; gitignored, E32). Named in `.gitignore:163`. | None | Loss of the memory database. Whether it can be rebuilt from source is UNKNOWN. | VERIFIED (exists, excluded) |
| `data/alert_state/` | Yes | 8 KB, directory, 2 files | **Excluded** | None | Loss of alert dedup state. Consequence of a fresh install: alerts may re-fire. | VERIFIED (exists, excluded). Consequence INFERRED. |
| `data/resilience-crosswalk/` | Yes | 12 KB, directory, 1 file | **Excluded** | None | Loss of audit trail file. | VERIFIED |
| `data/self-improvement/review/` | Yes | Directory | **Included** (E1, line 207) | Some files gitignored; untracked file present | Restored from latest snapshot | VERIFIED |
| `/etc/self-improvement/` | Yes | 8 KB, directory, 1 file (`dashboard.env`) | **Excluded** (not in path list, lines 206-219) | None | Dashboard service config lost. Secret content not read. | VERIFIED (exists, excluded) |
| `/data/coolify/` | Yes | 6.5 MB, directory, 59 files, subdirectories `applications`, `backups`, `databases`, `images`, `proxy`, `sentinel`, `services`, `source`, `ssh`, `ssl` | **Excluded** | None. Contains `source/.env` and dated copies (names only checked; contents not read). | Coolify is decommissioned (`deploy/caddy/Caddyfile.v3:25-28`), so this is residual state. Its `.env` (mode 0644) holds secret-named variables and is not backed up. | VERIFIED (exists, excluded). Decommissioned by documentation. Key-material use UNKNOWN. See §4A.3. |
| Docker volume `coolify-db` | Yes | 100 MB | **Excluded** (no Docker volume is in the path list) | None | Coolify database lost. No running consumer (decommissioned, §4A.3). | VERIFIED (exists, excluded) |
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

## 4A. Infisical and Coolify evidence (discovery of 2026-11-08, revision 3)

Scope: read-only metadata. No container was started, stopped or restarted. No `docker compose` command was run (`compose config` would interpolate and print secret values, and compose execution is out of scope). No database was connected. No secret value, environment value or credential was read or printed. Environment variables are reported by name only.

**Security incident in this discovery:** an early `docker inspect` template printed the Redis `--requirepass` value from the `infisical-redis-1` command line. The value is not reproduced anywhere in this document. It should be treated as exposed to anyone with this session's transcript. See §4A.7.

### 4A.1 Running Infisical deployment (VERIFIED)

| Container | Image reference | Running image ID | Digest status | Compose service | Networks | Mounts (volume → path) | Restart | Health | Published | Created / started |
|---|---|---|---|---|---|---|---|---|---|---|
| `infisical-infisical-1` | `infisical/infisical:latest-postgres` | `36438985877f` | Repo digest `sha256:36438985877fb5ab99c76ee1a9c73611e44d8518b44a77304b5d4c05451f8c62`, equal to the compose pin | `infisical` | `coolify` (10.0.1.0/24), `infisical_default` | `infisical_infisical-uploads` → `/app/backend/uploads` (0 regular files) | `unless-stopped` | No healthcheck configured | `127.0.0.1:8446` → 8080 (confirmed by `ss -ltn`) | Created 2026-09-05; started 2026-10-19 |
| `infisical-db-1` | `postgres:15-alpine` (tag) | `fe0737ba566a` | **Not** the tag's current target (`a46e076249ce`, tag re-pulled 2026-09-17). No repo digest. | `db` | `infisical_default`, alias `infisical-pg` | `infisical_infisical-db` → `/var/lib/postgresql/data` (84 MB) | `unless-stopped` | `pg_isready -U infisical`, 10 s interval, healthy | None | Created 2026-09-04; image created 2026-08-13 |
| `infisical-redis-1` | `redis:7-alpine` (tag) | `ff02b58f971e` | **Not** the tag's current target (`520775a41a63`, tag re-pulled 2026-09-17). No repo digest. | `redis` | `infisical_default`, alias `infisical-redis-svc` | `infisical_infisical-redis` → `/data` (12 MB) | `unless-stopped` | `redis-cli ping`, 10 s interval, healthy | None | Created 2026-09-04; image created 2026-08-18 |

Sources: `docker inspect` on each container (Config, HostConfig, NetworkSettings, Mounts, State), `docker image inspect`, `docker volume inspect`, `ss -ltn`. Container status from `docker ps -a`: all three "Up 2 weeks"; both database and Redis healthy.

Labels (VERIFIED, names and non-secret values): compose project `infisical`; `com.docker.compose.project.config_files=/root/TJRHQ/deploy/infisical/docker-compose.yml`; `com.docker.compose.project.working_dir=/root/TJRHQ/deploy/infisical`; compose version 5.2.0. The app container also has seven `traefik.*` labels (router `infisical`, entrypoint `https`, TLS with cert resolver `letsencrypt`, service port 8080, `traefik.docker.network=coolify`).

Environment variable names on the app container (VERIFIED, 27 names, all accounted for): 16 come from the image (`CAPTCHA_SITE_KEY`, `ChrystokiConfigurationPath`, `HOST`, `HTTPS_ENABLED`, `INFISICAL_PLATFORM_VERSION`, `INTERCOM_ID`, `NODE_ENV`, `NODE_OPTIONS`, `NODE_VERSION`, `PATH`, `PORT`, `POSTHOG_API_KEY`, `STANDALONE_BUILD`, `STANDALONE_MODE`, `TELEMETRY_ENABLED`, `YARN_VERSION`); 11 match the private recovery env file (`AUTH_SECRET`, `DB_CONNECTION_URI`, `DISABLE_SIGNUP`, `ENCRYPTION_KEY`, `REDIS_URL`, `SITE_URL`, `SMTP_FROM_ADDRESS`, `SMTP_HOST`, `SMTP_PASSWORD`, `SMTP_PORT`, `SMTP_USERNAME`). No running name is undeclared, and none declared in the recovery env is missing from the container. Database container names: `POSTGRES_PASSWORD`, `POSTGRES_DB`, image defaults. **`POSTGRES_USER` is absent** (see §4A.2, row 14). Redis container: image default `REDIS_VERSION`, and the password is passed on the command line (§4A.7).

Who uses it, and how: TJRHQ wrappers reach Infisical at `http://127.0.0.1:8446/api` (`platform-runtime/run-with-infisical.sh:33`, `platform-runtime/run-with-infisical-bot.sh:30`, `platform-runtime/lib-infisical.sh:3`). **No service uses the public Traefik hostname.** The local port is what matters for startup.

### 4A.2 Compose comparison (repo, private reconstruction, running containers)

Repo copy: `deploy/infisical/docker-compose.yml` (tracked; commits `e218bd7c2`, 2026-10-04, recovered; `846b2aa31`, 2026-10-09, pin digest and project name). Private copy: `/root/private-knowledge/infisical-compose/docker-compose.yml` (not tracked; in backup path list via `/root/private-knowledge`, `deploy/starship-backup.sh:217`). Both parsed with a YAML parser. Structure only; env values not read.

| # | Dimension | Repo | Private | Running | Match | Label |
|---|---|---|---|---|---|---|
| 1 | Project name | `name: infisical` | `name: infisical` | label `project=infisical` | Yes | VERIFIED |
| 2 | Compose config-path label | Not applicable (file lives in `/opt/starship-endeavour/deploy/infisical/`) | Not applicable (file lives in `/root/private-knowledge/infisical-compose/`) | `/root/TJRHQ/deploy/infisical/docker-compose.yml`, directory does not exist | **No**. Neither copy is at the recorded path. | VERIFIED |
| 3 | Infisical image | Pinned to digest `sha256:3643…862` | Same pin | Image ID matches the pin and the `latest-postgres` tag | Yes | VERIFIED |
| 4 | DB image | `postgres:15-alpine`, no digest | Same | Running ID `fe0737ba566a` differs from the tag target `a46e076249ce` | **No** | VERIFIED (IDs). Running 15.19 per private compose comment, DOCUMENTED, not re-verified. |
| 5 | Redis image | `redis:7-alpine`, no digest | Same | Running ID `ff02b58f971e` differs from the tag target `520775a41a63` | **No** | VERIFIED |
| 6 | Infisical networks | `coolify` (external) and `default` | `coolify` (external) and `default` | `coolify` and `infisical_default` | Yes | VERIFIED |
| 7 | DB and Redis network aliases | `db`: `infisical-pg`; `redis`: `infisical-redis-svc` | **None** | `infisical-pg`, `infisical-redis-svc` | **No**. Private omits both aliases. | VERIFIED. Effect on `DB_CONNECTION_URI` and `REDIS_URL` hostnames: INFERRED. |
| 8 | Named volumes | `infisical-db`, `infisical-redis`, `infisical-uploads` | Same | Same names, driver `local` | Yes | VERIFIED |
| 9 | Published ports | `127.0.0.1:8446:8080` | Same | `127.0.0.1:8446` → 8080 | Yes | VERIFIED |
| 10 | Restart policy | `unless-stopped` on all three | Same | Same | Yes | VERIFIED |
| 11 | Healthchecks | DB `pg_isready`; Redis `redis-cli ping`; Infisical none | Same | DB and Redis healthy; Infisical none | Yes | VERIFIED |
| 12 | Startup dependency | Infisical waits for `db` and `redis` (`service_healthy`) | Same | Label `depends_on=db:service_healthy, redis:service_healthy` | Yes | VERIFIED |
| 13 | Traefik labels on Infisical | Seven labels | **None** | Seven labels | **No** (private). Traefik is not running (§4A.3), so the labels currently route nothing. | VERIFIED |
| 14 | DB user environment | `POSTGRES_USER` supplied via `${…}` | `db.env` declares `POSTGRES_USER` | **Absent** from the container | **No**. A fresh init from the running container's env would create the default `postgres` role. The volume already exists, so this matters only for a rebuild. The runbook's `pg_restore -U infisical` needs role `infisical` (runbook §4.2). | VERIFIED (absence). Init behaviour of the postgres image: INFERRED. |
| 15 | Infisical env wiring | Inline `environment:` with `${VAR}` interpolation. Needs a `.env` in the project directory. | `env_file: ../infisical-recovery.env` | 27 names, all explained (§4A.1) | Different mechanisms. Repo declares 12 names (adds `NODE_ENV`); private declares 11. | VERIFIED |
| 16 | Redis command | `redis-server --requirepass ${REDIS_PASSWORD}` | Same template | Command line contains the literal value (not reproduced) | Template matches. The running container embeds the value, which the template does not. | VERIFIED. See §4A.7. |
| 17 | Interpolation source | `deploy/infisical/.env` **absent** (only `.env.example` tracked) | `.env` present, one variable name `REDIS_PASSWORD` | n/a | Repo copy is not self-contained | VERIFIED |
| 18 | `coolify` network | External | External | Exists: bridge, 10.0.1.0/24, created 2026-07-19 | Yes | VERIFIED |

**Verdict.** Neither compose file demonstrably reproduces the running deployment. They agree on structure, names, ports, volumes, restart, health and dependencies, and on the Infisical image digest. They disagree on DB and Redis image references (no longer resolve to the running images), network aliases, Traefik labels, DB user environment and env wiring. The compose `config-hash` label on the running containers cannot be recomputed without running compose, which is out of scope. Whether a restored copy would produce a byte-identical configuration: **UNKNOWN**.

### 4A.3 Coolify status (VERIFIED unless marked)

**Decommissioned by documentation.** `deploy/caddy/Caddyfile.v3:25-28`: "2026-09-26: Coolify decommissioned (6-container pass-through shim with zero deployed apps since its 2026-07-19 install)". `deploy/caddy/Caddyfile.v3:172-174`: "restored to owning 80/443 directly; the legacy_caddy Traefik forwarding shim is gone." The live `/etc/caddy/Caddyfile` is byte-identical to the repo copy (`cmp`, rev 1).

**Runtime state.**
- No Coolify container exists, running or stopped. `docker ps -a` lists five containers: `changedetection.io`, `uptime-kuma`, and the three Infisical containers.
- No Traefik container exists. Ports 80 and 443 are owned by host `caddy` (`ss -ltn`).
- No Coolify image is present locally. `docker images` lists six repositories: `postgres:17`, `redis:7-alpine`, `postgres:15-alpine`, `dgtlmoon/changedetection.io`, `louislam/uptime-kuma:1`, `infisical/infisical:latest-postgres`.
- **Changed since 2026-11-03.** `reports/vm-audit/vm-evidence-20261103-110813.md:152` recorded 16 images, including Coolify (742 MB app, 652 MB helper, 998 MB realtime), `traefik`, `sentinel` ×2, `gitleaks` and `pgvector`. Line 214 recorded "Coolify images (2.4G) with no Coolify containers running". Those images are gone now. No commit since 2026-10-20 mentions Coolify (`git log --grep`), and no document found records the removal. **Cause UNKNOWN.** Q16.

**Volumes and network.**
- `coolify-db`: 100 MB, created 2026-07-19 12:54:52 +10:00, compose project `source` (v2.38.2). `coolify-redis`: 492 KB. Neither is mounted by any container. `reports/VM-Capacity-Assessment-vmi3371936-2026-10-04.md:122` calls them orphaned and asks to confirm they are unused. `knowledge/missions/VM-OPTIMISE-ZERO-COST-PLAN-20261009.md:74` says not to delete orphaned Coolify volumes.
- `coolify` network: bridge, 10.0.1.0/24, created 2026-07-19 12:53:42 +10:00, one attached container (`infisical-infisical-1`). Coolify's install log ends "Coolify installation completed successfully" at 2026-07-19 12:55:06 (VERIFIED, `/data/coolify/source/installation-20260719-125334.log`).
- The Infisical compose declares the network external with the comment "exists today; Infisical is attached to it. Do not remove it" (private copy `/root/private-knowledge/infisical-compose/docker-compose.yml:54`). **Corrected: the phrase is absent from the repo copy, which has `external: true` at line 106 (§16).**

**`/data/coolify/` (not in backup path list, `deploy/starship-backup.sh:206-219`).**
- `source/`: `docker-compose.yml` defines a non-external `coolify` network and services `coolify`, `postgres`, `redis`, `soketi`. Its `coolify` and `soketi` services have no `image:` key. `docker-compose.prod.yml` is the production variant: image `${REGISTRY_URL:-docker.io}/coollabsio/coolify:${LATEST_IMAGE:-latest}`, realtime image `coollabsio/coolify-realtime:1.0.19`, external `coolify` network, volumes `coolify-db` and `coolify-redis`.
- `source/.env`: **mode 0644**, modified 2026-09-19 10:04. Variable names only: `APP_ID`, `APP_NAME`, `APP_KEY`, `DB_USERNAME`, `DB_PASSWORD`, `REDIS_PASSWORD`, `PUSHER_APP_ID`, `PUSHER_APP_KEY`, `PUSHER_APP_SECRET`, `ROOT_USERNAME`, `ROOT_USER_EMAIL`, `ROOT_USER_PASSWORD`, `REGISTRY_URL`, `DOCKER_ADDRESS_POOL_BASE`, `DOCKER_ADDRESS_POOL_SIZE`, `LATEST_IMAGE`, `COOLIFY_VERSION`.
- 17 dated `.env-<date>` copies (2026-08-13 to 2026-09-19), each mode 0644. `.env.production` mode 0700. `upgrade.sh` mode 0700.
- Upgrade cadence: daily upgrade logs from 2026-07-19 to 2026-09-19. Last line: "Upgrade completed: 2026-09-19 10:06:49". No later log. No crontab or unit references Coolify (`crontab -l`, `deploy/*.service`, `deploy/*.timer`). Consistent with decommissioning on or around 2026-09-26 (INFERRED).
- `proxy/`: `docker-compose.yml` (1762 bytes), `acme.json` (28,703 bytes, mode 0600), `dynamic/`, `backups/`. `acme.json` is Traefik's ACME store (INFERRED from file name). Traefik is not running. The file is not backed up.
- `sentinel/` 6.0 MB, `ssh/` 20 KB, `ssl/` 8 KB, `applications/`, `databases/`, `services/`, `images/`, `backups/` (all small or empty by `du`).

**Encryption-key dependency.** `APP_KEY` is in `source/.env`. Whether Coolify uses it to encrypt values stored in `coolify-db` is **UNKNOWN** from this VM. Coolify is built on Laravel, whose `APP_KEY` is the usual encryption key (INFERRED). Database contents were not inspected.

**Documentation disagreement.** `USS-TJR-Control/README.md:15` says "no Coolify". Line 87 of the same file and `USS-TJR-Control/VM-STARTUP-PROCEDURE.md:48` list Coolify as present. The Caddy config comments of 2026-09-26 say decommissioned. The Caddy comments are the most recent and are relied on here.

**Code and unit dependencies.** A search of the repo, excluding docs, logs, `data/` and venvs, finds Coolify only in `deploy/infisical/docker-compose.yml` and `deploy/caddy/Caddyfile.v3`. No unit or timer references Coolify. **No TJRHQ code path depends on Coolify.** (VERIFIED for the files searched.)

**Docs for Coolify recovery.** None found. The only Coolify references in docs are the status notes above.

### 4A.4 Replacement-VM dependency sequence (what the evidence supports)

1. **Docker and images.** Install Docker. Pull `postgres:15` (any 15.x) and `redis:7`. Pull `infisical/infisical` by the pinned digest. Local copies are not in the backup. Not demonstrated.
2. **Network.** Create the external network named `coolify`. The compose file cannot start without it, but nothing else about Coolify is required. Not demonstrated.
3. **Secrets from outside the VM.** Restic password and Google OAuth client (§7.1 in rev 2). Restic restore then yields the recovery env and `db.env`. Infisical needs `ENCRYPTION_KEY`, `AUTH_SECRET`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`. Documented, not demonstrated on a fresh host.
4. **Pick a compose file.** Neither is demonstrated. Before use, the choice must be reconciled with §4A.2 rows 7, 13, 14, 17.
5. **Start database and Redis only.** Both have healthchecks, so Infisical's `depends_on` gate works once they report healthy.
6. **Restore the database.** Run `pg_restore` from `infisical-db.dump` as role `infisical` (runbook §4.2). The role must exist first. On a fresh volume it is created from `POSTGRES_USER`, which the running container no longer has (row 14). Use the private `db.env` or add `POSTGRES_USER` to the repo compose.
7. **Start Infisical.** Gated on DB and Redis health. No healthcheck exists on the app, so readiness must be checked with an HTTP probe on `127.0.0.1:8446` (not run here).
8. **Restore the machine identity.** `platform-runtime/.infisical-auth.env` (in the backup). Services log in with it. Login not tested.
9. **Start services.** Wrappers call `127.0.0.1:8446/api`. The 2026-10-06 incident comment (`platform-runtime/lib-infisical.sh:5-11`) records that a container which came up after its dependent units made those units run with no secrets and no error. Order matters. A worktree branch `USS-TJR-MSN-0407-infisical-wrapper-failloud` exists (`git worktree list`), which suggests a fail-loud fix was in progress. This assessment did not verify that fix on `main`.
10. **Public Infisical route.** Not required by any service. Traefik labels are inert today (no Traefik). Whether to restore a public route is an owner decision (Q20).
11. **Coolify.** Not required. Decommissioned (§4A.3). Its volumes, `/data/coolify` and remaining images are residual state. Retention is an owner decision (Q18).

**Circular dependencies assessed:**
- **Restore chain: none.** The restore needs the restic password (off VM), then restic files, then Infisical, then services. Nothing in that chain needs a service that needs Infisical.
- **Backup chain: a runtime dependency, not a restore cycle.** Step 1 of `deploy/starship-backup.sh` runs the Supabase dump under the Infisical wrapper (`:105`). Steps 2–5 are documented as independent of Infisical (`:20-22`). If Infisical is down at 02:40, the Supabase dump fails and the rest still runs.
- **Machine identity.** `.infisical-auth.env` is in the backup and is needed to reach Infisical. Its validity depends on records in the Infisical DB, which is restored from the same backup. Whether the identity is still valid after restore is **UNKNOWN** until tested.
- **Coolify: no link.** No cycle, since TJRHQ has no Coolify dependency.

**Components that cannot be reconstructed from documented evidence:**
- The exact running DB and Redis images. The tags have moved and the running IDs have no digest pins. A logical restore into `postgres:15` should work across minor versions (INFERRED), but identical images are not reconstructable.
- Redis contents. Not backed up. Role **UNKNOWN**.
- The DB user environment in the running container (row 14). Reconstructable only from the private `db.env`, which does declare `POSTGRES_USER`.
- The public Traefik route, which has no proxy to serve it.

### 4A.5 Evidence and confidence table (material findings)

| # | Finding | Exact source or command | Observed | Label | Recovery consequence | Remaining uncertainty |
|---|---|---|---|---|---|---|
| F1 | Infisical image pinned and matches running image | `docker inspect`, `docker image inspect`, compose line 58 (pin) | Running ID `36438985877f` has repo digest equal to the pin | VERIFIED | Infisical app image is reproducible by digest | Registry availability of the digest |
| F2 | DB image tag moved; running image untagged | `docker image inspect postgres:15-alpine` vs `docker inspect infisical-db-1` | Tag `a46e076249ce` (re-pulled 2026-09-17) ≠ running `fe0737ba566a` (2026-08-13) | VERIFIED | Compose `up` on a fresh host gets a different DB image | Whether the two differ in minor version (DOCUMENTED: running 15.19) |
| F3 | Redis image tag moved; running image untagged | Same, for `redis:7-alpine` | Tag `520775a41a63` (2026-09-17) ≠ running `ff02b58f971e` (2026-08-18) | VERIFIED | As F2 | Redis version of the running image not checked |
| F4 | Compose config path label points at a missing directory | `docker inspect` label; `ls /root/TJRHQ` | Label `/root/TJRHQ/deploy/infisical/docker-compose.yml`; directory absent | VERIFIED | Compose commands that read the label will fail on this VM | None for the label; the replacement path is an operator choice |
| F5 | Private compose lacks network aliases and Traefik labels | `yaml.safe_load` on both compose files | Private has no `networks` on db/redis and no `labels` on infisical | VERIFIED | Private copy alone does not reproduce hostnames or routing | Whether `DB_CONNECTION_URI` uses `infisical-pg` (value not read) |
| F6 | Running DB container has no `POSTGRES_USER` | `docker inspect infisical-db-1`, env names | Absent. Present in repo and private compose | VERIFIED | Fresh volume init creates role `postgres`, not `infisical` | Init behaviour of image: INFERRED |
| F7 | Coolify decommissioned by documentation | `deploy/caddy/Caddyfile.v3:25-28, 172-174` | Text as quoted | DOCUMENTED | No Coolify restore needed | Whether removal is complete beyond the documented scope |
| F8 | No Coolify runtime, Traefik or Coolify images present | `docker ps -a`, `docker images` | None present | VERIFIED | Confirms F7 | Why images vanished between 11-03 and 11-08 (Q16) |
| F9 | Coolify volumes and network persist, unmounted | `docker volume inspect`, `docker network inspect coolify` | Volumes exist, not mounted. Network has one container (Infisical). | VERIFIED | Infisical needs the network name only | Owner decision on volumes (Q18) |
| F10 | `coolify` network is external to the Infisical compose | `deploy/infisical/docker-compose.yml:53-54` | External, must exist | VERIFIED | Creation required on a new host | Whether `compose up` fails without it: INFERRED from external semantics. Not run. |
| F11 | Coolify `.env` contains secret-named variables at mode 0644 | `ls -la /data/coolify/source/.env` | Mode 0644, 17 variable names | VERIFIED | Exposure to any local user; not in backup path list | Whether any other user exists on the VM |
| F12 | Coolify state is not backed up | `deploy/starship-backup.sh:206-219` vs `/data/coolify` | Not in list | VERIFIED | Lost on VM loss, but not required (F7) | Whether anyone wants it (Q18) |
| F13 | Services use the loopback port, not the public route | `platform-runtime/run-with-infisical.sh:33`, `lib-infisical.sh:3`, `run-with-infisical-bot.sh:30` | `http://127.0.0.1:8446/api` | VERIFIED | Public route not on the startup path | None |
| F14 | No TJRHQ code depends on Coolify | `grep -ril coolify` excluding docs, logs, `data/`, venvs | Only `docker-compose.yml` and `Caddyfile.v3` | VERIFIED | No code-level dependency | Files outside the repo, not searched |
| F15 | Env names all explained | `docker inspect` env names vs image defaults and recovery env | 27 of 27 explained | VERIFIED | Recovery env is complete for the app | Values not checked |
| F16 | Redis password embedded in container command | `docker inspect` `Config.Cmd` | Literal value on the command line (value not reproduced) | VERIFIED | Visible to any principal with Docker access. Exposed in this session's transcript. | Rotation needed (owner decision, §4A.7) |
| F17 | Infisical health: DB and Redis healthy, app has no healthcheck | `docker inspect` health fields | As stated | VERIFIED | App readiness not observable from Docker | HTTP readiness of the app: not probed |
| F18 | No compose execution, so resolved config equality untested | Method restriction | n/a | VERIFIED (not run) | Neither compose is demonstrated | Q15 |

### 4A.6 Demonstrated versus documented

| Claim | Status |
|---|---|
| Infisical container set matches compose structure (names, ports, volumes, restart, health, dependencies) | Matches on inspection. Not demonstrated by compose. |
| Infisical restore from logical dump gives identical secrets | DOCUMENTED (runbook line 69, 2026-10-09). Not re-run. |
| Infisical restore on a fresh host | Not documented as tested |
| Services start after Infisical on a fresh host | Not documented as tested |
| Repo compose brings up Infisical | Not demonstrated. `.env` is absent from the repo directory (§4A.2 row 17). |
| Private compose brings up Infisical | Not demonstrated. Missing aliases and labels (F5). |
| Coolify can be restored | Not demonstrated. Decommissioned by documentation (F7). |

### 4A.7 Security observations (no changes made)

1. **Redis password on the command line.** `infisical-redis-1` was started with `redis-server --requirepass <value>` (F16). Anyone who can run `docker inspect` reads it, and so does anyone who reads the process list (INFERRED). The value appeared in this session's output. **Recommendation:** owner decides on rotation and moving it to a file or Docker secret. Rotation was not performed (restricted).
2. **Coolify `.env` mode 0644** (F11). **Recommendation:** owner decides on `0600`, or on removing the decommissioned directory.
3. **Dated `.env` copies** (17 in `/data/coolify/source`, mode 0644). They accumulate secrets and are not backed up (F12). Same recommendation.

## 4B. Security findings and Future Actions Register

Documentation only. This section records findings and the actions they need. It does not remediate, rotate, change permissions, restart anything, or re-inspect any system. Credential values and fingerprints are not reproduced anywhere in this section. Evidence cited is the sanitized discovery evidence already recorded in §4A and §4 (`docker inspect` metadata, `ls -la` mode output, compose and path-list file references).

### SEC-DR-01: Redis credential exposure

| Field | Content |
|---|---|
| Finding ID | SEC-DR-01 |
| Evidence | Sanitized: `docker inspect` `Config.Cmd` of `infisical-redis-1` (metadata, §4A.1, F16); compose references (§4A.2 row 16). Value not reproduced. |
| Confidence | VERIFIED: the value was exposed in session output and sits in container command metadata. UNKNOWN: validity, use, transcript retention, other copies. |
| Potential impact | Disclosure of the Redis authentication secret. Unauthorized access limited to `infisical_default` and Docker-level principals (no published port). |
| Future action | Scope exposure; confirm Redis role; plan and execute rotation under approval; move secret off the command line; decide backup-history handling (§ item 6 below). Detailed steps follow. |
| Dependencies | Infisical `REDIS_URL`; Redis healthcheck; compose interpolation (private `.env`); restic history. |
| Authorization | Separate owner approval required. |
| Status | OPEN — DOCUMENTED ONLY |

**Verified facts**

- The `infisical-redis-1` container was started with a `redis-server --requirepass <value>` command line. The value is visible in container command metadata to anyone who can run `docker inspect` (§4A.1, F16, `docker inspect` `Config.Cmd`).
- During read-only metadata inspection in this session, that argument, including the credential value, appeared in the Claude Code session output. Exposure location 1 is this session's transcript.
- The compose file passes the value by variable reference, `${REDIS_PASSWORD}`, in both the `command:` and the `healthcheck:` (`deploy/infisical/docker-compose.yml`; `/root/private-knowledge/infisical-compose/docker-compose.yml`). The literal value is not in either file. It is in the running container's command metadata.
- Redis publishes **no host port** (`docker inspect` `NetworkSettings.Ports` empty for `infisical-redis-1`). It is reachable only on the `infisical_default` Docker network (§4A.1). A host-listener check on port 6379 was not run; the basis for "no external access" is the absence of a published port in Docker metadata.
- The Redis data volume `infisical_infisical-redis` is 12 MB (§4A.1). Its contents are not inspected.
- The password is set in two environment-level places by name only: the Infisical app's `REDIS_URL` (recovery env file, §4A.1) and `REDIS_PASSWORD` in the private `.env` (`/root/private-knowledge/infisical-compose/.env`, name only).
- Restic path list includes `/root/private-knowledge` and the repo `.env*` files (`deploy/starship-backup.sh:217, 222-224`). Snapshots taken while the value was in those files hold it under the retention policy (`deploy/starship-backup.sh:241`, 7 daily / 4 weekly / 3 monthly).

**UNKNOWN**

- Whether the credential value is still in use and accepted by Redis. Redis was not authenticated against, by design.
- Who else can read the transcript, and how long the session transcript, its logs or any upstream logging are retained. Retention policy is outside this repository.
- Whether the value appears in any other log, shell history or monitoring output on this VM. Not searched.
- Whether the same value is used anywhere else (the Coolify `.env` also names `REDIS_PASSWORD`; whether it is the same secret is UNKNOWN, and its value was not compared).

**Potential impact**

- Disclosure of the Redis authentication secret to anyone with access to the transcript, its logs, or the backup snapshots that contain the old value.
- Unauthorized Redis access is possible only from containers on `infisical_default`, or from a principal with Docker access on the host. External network access is not possible because no host port is published (verified above).
- Redis contents are unknown. If they include Infisical session or cache data, the impact on Infisical is UNKNOWN until inspected.

**Future action (for a separate authorization; not performed)**

1. Scope the exposure. Owner determines who can read the transcript and the retention of the transcript store. Do this from the owner's own records. Do not read transcripts or logs containing the value.
2. Confirm Redis's role. Determine what Redis holds and whether Infisical depends on any persisted data from it, before rotating.
3. Plan a controlled rotation: generate a new value out-of-band, update every consumer by name (compose interpolation source, the private `.env`, the recovery env `REDIS_URL`, and the healthcheck), and keep the old value available until the new one is verified.
4. Restart in a planned window. Infisical's `depends_on` gates on Redis health (§4A.2, row 12), so Redis and Infisical must be restarted in order. Verify Redis health, Infisical app availability on `127.0.0.1:8446`, and one successful wrapper login.
5. Remove the value from the command line. Move it to a file-based `requirepass` or a Docker secret, so the next `docker inspect` does not show it.
6. Decide what to do about backup history. Restic snapshots taken before rotation still contain the old value. Pruning follows retention policy. Owner decides whether a rebuild-time rotation is accepted, or whether earlier snapshots should be pruned early.
7. Record the closure with evidence that does not reproduce the value. For example, a `docker inspect` check that the command line no longer carries a literal, and a passing health check.

**Dependencies**

- Infisical app (`REDIS_URL`), health gating, and all wrappers that depend on Infisical (§4A.4).
- Redis healthcheck command in compose.
- Compose interpolation sources: the private `.env` and any future repo `.env` (the repo copy is absent, §4A.2 row 17).
- Restic snapshot history (item 6 above).

**Rollback**

- Keep the old value until the new one is verified against Redis and Infisical. Revert all consumers together if Redis rejects the new value.

**Authorization:** separate owner approval required for rotation, for any restart of Redis or Infisical, and for any change to compose or the recovery env. This documentation does not authorize them.

**Priority:** HIGH for future security remediation.

**Status:** OPEN — DOCUMENTED ONLY.

### SEC-DR-02: Coolify credential-file permissions

| Field | Content |
|---|---|
| Finding ID | SEC-DR-02 |
| Evidence | Sanitized: `ls -la /data/coolify/source` (modes, sizes, dates, names only); Caddy decommission note (`deploy/caddy/Caddyfile.v3:25-28`); absence from restic path list. No file contents read. |
| Confidence | VERIFIED: mode `0644` on `.env` and 17 dated copies; `source/` mode `drwx------`. UNKNOWN: credential validity, parent-directory mode, other copies, effective accessibility. |
| Potential impact | Credential disclosure to principals who can traverse into the directory. Unauthorized access to upstream services if any credential is still valid. |
| Future action | Confirm parent-directory mode; inventory names and upstream services; rotate or retire credentials; decide retention or archival; correct permissions of anything kept. Detailed steps follow. |
| Dependencies | Coolify decommissioning record; optimise-plan rule on orphaned volumes; any upstream service still using the credentials. |
| Authorization | Separate owner approval required for permission changes, deletion or archival, and rotation. |
| Status | OPEN — DOCUMENTED ONLY |

**Verified facts**

- `/data/coolify/source/.env` has mode `0644` (`ls -la`, modified 2026-09-19 10:04). It contains secret-named variables. Names only were recorded (§4A.3): `APP_KEY`, `DB_PASSWORD`, `REDIS_PASSWORD`, `PUSHER_APP_SECRET`, `ROOT_USER_PASSWORD`, and others.
- Seventeen dated copies, `.env-2026-08-13-10-00-26` through `.env-2026-09-19-10-00-19`, each mode `0644` (`ls -la`, same listing). They are created by a daily job, and the last one is dated 2026-09-19.
- `/data/coolify/source/` itself has mode `drwx------` (`ls -la` listing, the `.` entry). Non-root users cannot traverse into it. The mode of the parent directory `/data/coolify/` was **not** recorded in the discovery evidence.
- Coolify is decommissioned per `deploy/caddy/Caddyfile.v3:25-28`. No Coolify container runs, and no listener exists on port 8000 (`ss -ltn`, earlier discovery).
- `/data/coolify/` is not in the restic path list (`deploy/starship-backup.sh:206-219`). Copies are not in off-VM backup.
- The `coolify-db` volume (100 MB) still exists. No running container mounts it (§4A.3).

**UNKNOWN**

- Whether any credential in these files is still valid, and whether any upstream service still accepts it. Examples: the root user password, the Pusher secrets, the registry URL. Not tested, by design.
- The effective accessibility of the files. The file mode is `0644`. Access in practice depends on the mode of `/data/coolify/`, which was not recorded, and on who holds root or Docker access.
- Whether `coolify-db` contains credentials that remain valid. Not inspected, by design.
- Whether any other copies of these values exist on the VM (for example in the Coolify `backups/` directory, or elsewhere). Not searched.

**Potential impact**

- **Corrected (§16):** `/data/coolify` and `/data/coolify/source` are both mode `drwx------`, so non-owner local users cannot traverse into the directory. Effective exposure is limited to the owner account and root (VERIFIED, `stat`). The earlier "parent mode not recorded" gap is closed.
- If any credential remains valid, disclosure could allow access to the upstream service it belongs to. Impact depends on that service and is UNKNOWN.
- Retained copies outside backup increase the chance that a retained copy persists after the live file is cleaned up.

**Future action (for a separate authorization; not performed)**

1. Confirm the mode of `/data/coolify/` and any other parent path to the files. Record it without reading the files.
2. Inventory the variable names in `source/.env` and the dated copies, and for each one, decide whether the upstream service still exists. Owner-level inventory only, no values.
3. For any credential that remains valid, plan rotation, or document why it is retained.
4. Decide retention. Options: delete the dated copies; or archive the Coolify state offline with mode `0600` and no network exposure. Coordinate with the owner's decision on `coolify-db` and `coolify-redis` (Q18).
5. Correct permissions to `0600` on any file that is kept. This is a separate change and must be approved.
6. Confirm no other copies exist, and record the result without reproducing content.

**Dependencies**

- Coolify decommissioning evidence (`deploy/caddy/Caddyfile.v3:25-28`) and the optimise plan's rule not to delete orphaned Coolify volumes without review (`knowledge/missions/VM-OPTIMISE-ZERO-COST-PLAN-20261009.md:74`).
- Any upstream service that still accepts the credentials (UNKNOWN).
- Rollback: if archival or deletion removes something still needed, the only recovery route is the owner's own records, since these files are not in backup.

**Authorization:** separate owner approval required for any permission change, deletion or archival of the files, and for any credential rotation. This documentation does not authorize them.

**Priority:** HIGH for assessment. Remediation priority depends on whether any credential remains valid.

**Status:** OPEN — DOCUMENTED ONLY.

### Future Actions Register (summary)

| Finding ID | Summary | Priority | Confidence of exposure | Owner decision needed | Status |
|---|---|---|---|---|---|
| SEC-DR-01 | Redis `--requirepass` value in container command metadata and session output | HIGH | VERIFIED exposure; use of value UNKNOWN | Scope of transcript exposure; rotation window; backup-history handling | OPEN — DOCUMENTED ONLY |
| SEC-DR-02 | Coolify `.env` and 17 dated copies at mode `0644` | HIGH (assessment) | VERIFIED mode; validity and accessibility UNKNOWN | Credential validity; retention or archival; permission correction | OPEN — DOCUMENTED ONLY |

The Future Actions Register above is the sole place where these items are tracked. Neither item has been acted on.

## 5. Infisical recovery dependencies (Investigation 2)

**Running deployment (metadata only, VERIFIED):**

- Three containers: `infisical-infisical-1`, `infisical-db-1` (healthy), `infisical-redis-1` (healthy). Project label `infisical`. Container start time 2026-10-19 13:24 UTC.
- Mounts: `infisical_infisical-uploads` at `/app/backend/uploads` (0 files); `infisical_infisical-db` at `/var/lib/postgresql/data` (84 MB); `infisical_infisical-redis` at `/data` (12 MB). All three are local-driver named volumes.
- Compose labels reference `/root/TJRHQ/deploy/infisical/docker-compose.yml`, which does not exist (E21, E22).
- The `coolify` network is declared `external: true` and "exists today; Infisical is attached to it. Do not remove it" (E20; private copy line 54, absent from repo copy, §16). The Infisical app's Traefik labels reference it (`traefik.docker.network=coolify`), but no Traefik container is running (§4A.3). No service uses the public route (§4A.1).

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
3. The `coolify` Docker network must exist before `docker compose up` (E20). Coolify itself is decommissioned (§4A.3) and is not needed. On a replacement VM, `docker network create coolify` supplies the name. Not tested.
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
| Weekly integrity timer (E16) | Sampled, 1 in 20 packs | First run completed 11-08 11:30 AEDT: 12/12 snapshots, 4/52 packs read, "no errors were found" (§16) | VERIFIED (journal) |

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
- TOC line counts changed from 1985 (11-03) to 1893 (11-06), a drop of 92 (E14). **Partially explained in §8.4:** the 11-06 dump reproduces offline (1,878 entries plus 15 header lines), and the decrease is consistent with migration `0249` moving seven tables out of the dumped schemas. The guard in E8 (≥ 100 entries) still passes. A schema change, table removal or cleanup could explain it. The 2026-09-01 "dead-tables-pre-drop" backup file exists in the repo (`core/infrastructure/supabase/backups/`), so a drop is plausible, but it is not verified. The evidence needed is a comparison of the two dumps' TOC lists, which this assessment did not run.

**Verdict:** "up to 72 hours" for dumped database content is supported. Claims about storage binaries, vault contents or unlogged writes are not.

### 8.4 Supabase dump TOC reconciliation — November 3–6, 2026

**Finding status: PARTIALLY EXPLAINED.** The decrease is consistent with a deliberate schema move in migration `0249_archive_revs_tables.sql`. It is not confirmed. The 11-03 dump is not available locally, so an object-by-object comparison was not possible. A coverage gap follows from the move regardless of the exact count (§8.4.5).

**Correction to §5 and §8.3:** the 92-entry decrease was previously described as having an UNKNOWN cause. That is superseded by this subsection. The journal figure is a count of output **lines**, not of entries (§8.4.1).

#### 8.4.1 Evidence: which dumps, and how each count was produced

| Item | Dump 2026-11-03 | Dump 2026-11-06 | Source |
|---|---|---|---|
| Journal line | `supabase dump: 39 MB, 1985 table-of-contents entries` at 02:42:27 AEDT | `supabase dump: 40 MB, 1893 table-of-contents entries` at 02:41:35 AEDT | `journalctl -u starship-backup.service`, 2026-11-03 and 2026-11-06 |
| Dump file | Not local. Only restic snapshot `afa14ad1` (11-03) holds it. Not retrieved, per boundary. | `/var/lib/starship-backup/supabase.dump`, 42,722,427 bytes, mtime 2026-11-06 02:41:35 (+1100) | `ls -la`, `stat` |
| Cache mode | Dump taken: cache age 71 h, due | Dump taken: cache age 71 h, due | Journal, same days |
| Exit status | Dump wrapper exit = `pg_dump` exit (`rc=$?` captured, `deploy/starship-backup.sh:69`, `:105`). Journal records no failure line for the dump. | Same; `finished OK` at 02:41:38 | Script; journal |
| Size guard | ≥ 1 MB, ≥ 100 entries; passed | Same; passed | `deploy/starship-backup.sh:109` |
| Counting method | `docker run -i --rm postgres:17 pg_restore --list < dump \| wc -l`, count of output **lines** | Same | `deploy/starship-backup.sh:107` |
| Image | `postgres:17`, current ID `2d2b8998d310`, created 2026-10-06 | Same current ID | `docker image inspect postgres:17`. An image re-pulled between the two dates would have a newer creation date. None is present, so the same image is inferred for both (INFERRED). |
| `pg_dump` options | `--no-owner --no-privileges --format=custom --schema=public --schema=auth --schema=storage --schema=supabase_migrations` + data exclusions for 4 log tables | Same | `deploy/starship-backup.sh:66-67`, `:51` |
| Database target | `SUPABASE_DB_URL` from Infisical, by variable name only. Target value not read. | Same | `deploy/starship-backup.sh:65-66` (names only). Target identity: INFERRED same. |
| Script changes to dump lines in window | None. The only commits touching `deploy/starship-backup.sh` in 2026-11-03 to 2026-11-06 are `7a8dd3b84` (2026-11-05, venv freeze) and `dbbfbae1a` (2026-11-03, unit tracking). A diff of `7a8dd3b84` shows no change to `pg_dump`, schema, exclusion or TOC lines. Diff of `dbbfbae1a` for those lines not run. | — | `git log`, `git diff` (metadata) |
| Warnings and retries | Not logged. `pg_dump` stderr is written to a staging file that is removed on exit (`deploy/starship-backup.sh:84-85`). It is printed only on failure. | Same | Script. This is a **limitation**: warnings on a successful dump cannot be observed from logs. |

The journal counts are output line counts. The 11-06 dump's `pg_restore --list` output, reproduced offline in this subsection, has **1,893 lines**: 15 header lines (beginning `;`) and **1,878 entries**. The 11-03 figure of 1,985 is therefore 1,985 lines, which is about 1,970 entries if its header is also 15 lines (INFERRED, the header is produced by the same tool and version).

#### 8.4.2 Method for this reconciliation

- Local dump: `/var/lib/starship-backup/supabase.dump` (11-06 only). Read with `docker run --rm --network none -v /var/lib/starship-backup:/in:ro postgres:17 pg_restore --list /in/supabase.dump`. Exit 0, no stderr, 1,893 lines. The output was saved to a scratchpad file and parsed locally. The same image and method as the script.
- No restore mode was used. No database connection was made. No TOC names were printed in this report.
- Type and schema were parsed from each entry's description column (uppercase type words, then schema). All 1,878 entries were recognised (0 unrecognised).
- The 11-03 dump is not local. The comparison by object type cannot be run. Only the 11-06 breakdown is recorded here, and the decrease is analysed through the repository's migration evidence instead.

#### 8.4.3 Counts for the 11-06 dump

Entries by schema (1,878 total):

| Schema | Entries | Note |
|---|---|---|
| `public` | 1,541 | Dumped |
| `auth` | 250 | Dumped |
| `storage` | 78 | Dumped (metadata only, see §7.4) |
| `supabase_migrations` | 4 | Dumped |
| (no schema) | 5 | Extensions, schema objects |

Entries by object type:

| Object type | Entries | | Object type | Entries |
|---|---|---|---|---|
| INDEX | 367 | | TRIGGER | 22 |
| COMMENT | 319 | | SEQUENCE | 20 |
| CONSTRAINT | 225 | | SEQUENCE SET | 20 |
| POLICY | 203 | | TYPE | 11 |
| TABLE | 169 | | SEQUENCE OWNED BY | 9 |
| TABLE DATA | 165 | | DEFAULT | 9 |
| ROW SECURITY | 157 | | SCHEMA | 4 |
| FK CONSTRAINT | 90 | | MATERIALIZED VIEW | 1 |
| FUNCTION | 56 | | MATERIALIZED VIEW DATA | 1 |
| VIEW | 30 | | | |

TABLE entries by schema: `public` 133, `auth` 27, `storage` 8, `supabase_migrations` 1 (total 169). The difference between TABLE (169) and TABLE DATA (165) is 4. The script excludes data for exactly 4 log tables (`deploy/starship-backup.sh:51`). That match is consistent with the exclusion, but was not checked table by table (INFERRED).

The 11-03 breakdown by object type is **UNKNOWN**.

#### 8.4.4 Material differences and the candidate cause

**Candidate cause.** Migration `core/infrastructure/supabase/migrations/0249_archive_revs_tables.sql` (commit `98ba1cf6a`, committed 2026-11-03 08:33 UTC, i.e. 19:33 AEDT; corrected from +1100) contains:

- Seven executed `ALTER TABLE … SET SCHEMA archive` statements. A further `SET SCHEMA public` match at line 12 is a comment (the reversal note), not an executed statement. No executed `DROP`, `CREATE TABLE` or `CREATE INDEX` (keyword counts only; corrected from "eight statements" by §16, Agent 4).
- The same commit decommissions the REVS pilot bot and removes `telegram-bots/revs/`, with the bot kept on a branch. The archiving migration therefore appears to belong to that decommissioning.

The dump filter includes only `public`, `auth`, `storage` and `supabase_migrations` (`deploy/starship-backup.sh:67`). A table moved to `archive` **leaves the dump**, together with its indexes, constraints, policies, comments and data.

**Checks against the 11-06 dump (names withheld):**

- The seven tables named in the `SET SCHEMA archive` statements: **0 of 7 present** in any dumped schema. Consistent with the moves being in place when the 11-06 dump ran.
- The one `SET SCHEMA public` target: not counted separately; `public` is dumped, so this statement does not remove anything.
- Two tables created by later emergency-alert migrations (`0252`, `0254`, committed 2026-11-06 09:23 (`0252`) and 10:19 (`0254`) +1100, both after the 02:41 dump): **0 of 2 present**. Consistent with those migrations not being applied at dump time. Application times are not recorded in the repository (see §8.4.6).

**Magnitude check (INFERRED, not confirmed).** 92 lines over seven tables is about 13 lines per table. In the 11-06 dump, `public` has 1,541 entries over 133 tables, about 11.6 entries per table. This includes functions and other non-table objects, so it is a rough comparison. The two figures are of the same order.

**Other migrations in the window.** Migrations `0240` to `0248` were committed on 2026-11-01 and 2026-11-02, before the 11-03 dump. They add objects, which is consistent with the increase from 1,966 (10-31) to 1,985 (11-03). Their names and statements have no DROP or move statements (keyword counts: 0 each).

**Runbook figure, not corroborating.** The 2026-10-09 restore test reported **166 tables** (runbook line 82). The 11-06 dump has **169** TABLE entries. That is an increase of 3 since 10-09, not a decrease of 7. The two counts may use different methods (restored database versus TOC), so this does not contradict the candidate cause. It also does not support it.

#### 8.4.5 Recovery implications

1. **Are both dumps structurally readable?** The 11-06 dump: yes, offline `pg_restore --list` exit 0, 1,893 lines, no stderr. The 11-03 dump: **UNKNOWN from here**. The script checked it at creation (≥ 100 lines), but it was not re-read.
2. **Which objects are in the earlier dump but not the later one?** Entry-level comparison **UNKNOWN**. Candidate: the seven tables moved by `0249`, together with their dependent entries (INFERRED).
3. **Evidence of deliberate schema removal?** Yes, for the candidate: the `0249` migration moves tables to `archive`, and the same commit decommissions a bot. This is a **move, not a drop** (no DROP statements). Whether it was applied, and when, is **UNKNOWN**.
4. **Evidence of incomplete backup capture?** None for capture failure. Exit status, size guard, entry count guard and absence of failure log lines all pass for both nights. **But** this shows the dump is complete *for the schemas it selects*. It does not show that all relevant data is captured. The moved tables are **no longer captured by any nightly dump** after they are moved, which is a silent coverage reduction. Their data remains in the live Supabase project only (INFERRED: `archive` schema lives in the same project).
5. **What remains unknown without database-side verification?** Whether `0249` was applied, and when. Whether the `archive` schema exists and holds the seven tables. Whether the removed entries are exactly the seven tables' dependents. Whether any `archive` data is backed up elsewhere. Whether pg_dump emitted warnings on either night. Whether the 11-03 dump's content matches the same schemas. None of these is answered by TOC metadata alone.

**A valid custom-format dump and a successful `pg_restore --list` are not proof of a successful full restore.** Neither test restores any row, and neither compares data with the live database.

#### 8.4.6 Verified findings, inferences and unresolved questions

| Class | Statement | Source |
|---|---|---|
| VERIFIED | The 11-06 dump lists 1,893 lines, 1,878 entries, reproducible offline | Offline `pg_restore --list`, same image and method |
| VERIFIED | Both journal counts come from the same script line, with the same image tag | `deploy/starship-backup.sh:107`, journal |
| VERIFIED | No dump-related lines of the script changed between 11-03 and 11-06 (commit `7a8dd3b84` diff shows none) | `git diff` |
| VERIFIED | Dump filter excludes all schemas except the four listed | `deploy/starship-backup.sh:67` |
| VERIFIED | Migration `0249` contains seven executed `SET SCHEMA archive` statements; its one `SET SCHEMA public` match is a comment (line 12); no executed DROP | Line-level check of the migration file |
| VERIFIED | Migration `0249` is committed 2026-11-03 08:33 UTC (19:33 AEDT), after the 02:42 AEDT dump of that day | `git log --format=%ci` |
| VERIFIED | 0 of the seven moved tables appear in the 11-06 dump | Offline TOC, presence check (names withheld) |
| VERIFIED | 0 of the two later emergency-alert tables appear in the 11-06 dump | As above |
| INFERRED | Migration `0249` was applied before the 11-06 dump, causing most of the decrease | Combination of the above. Not confirmed by database-side evidence. |
| INFERRED | The image was the same on both nights | Image creation date and absence of any newer image |
| INFERRED | Exit status 0 indicates that `pg_dump` finished writing the dump. It does not show the absence of warnings or that the dump matches the live database. | Standard `pg_dump` behaviour; warnings unobservable here |
| UNKNOWN | Whether `0249` was applied, and when | No migration-application record in the repository. Database not queried. |
| UNKNOWN | The 11-03 object-type breakdown and entry-level difference | 11-03 dump not local |
| UNKNOWN | Whether pg_dump warnings occurred on either night | Stderr discarded on success |
| UNKNOWN | Whether `archive` data is backed up elsewhere | No evidence in repository |

**Correction to earlier text.** Revision 3 said the cause was unknown and that comparing the two TOC lists was the evidence needed (former §8.3, the bullet on the 92-entry drop). This is now partially answered by §8.4. The comparison remains impossible without the 11-03 dump.

**Correction to terminology.** The journal says "table-of-contents entries". The number counted is output lines, which include 15 header lines. The 11-06 dump has 1,878 entries.

#### 8.4.7 Future investigation and remediation (DOCUMENTED ONLY)

These steps are not performed. Each needs separate authorization.

1. **Confirm migration application.** Owner or DB operator confirms whether `0249` was applied, and when, from the Supabase migration history. No database query was made here.
2. **Decide the archive policy.** Decide whether tables moved to `archive` should be dumped. If yes, add `archive` to the dump filter (`deploy/starship-backup.sh:67`) after review. If no, document that the archived data is outside backup scope and where its recovery depends on the live project.
3. **Compare TOCs when the 11-03 dump is available** from restic, through an authorized restore to a scratch location, using `pg_restore --list` only. This would settle the entry-level difference.
4. **Record pg_dump warnings.** Change the script to retain `pg_dump` stderr on success, so warnings are observable.
5. **Restore-test the archive decision.** Any restore test should include a row-count comparison for the archived tables, against the live project, with authorization.

**Status: OPEN — DOCUMENTED ONLY.** Priority MEDIUM. The coverage reduction in §8.4.5(4) is the material item. The count difference alone is not a recovery failure.

**Path-count change (96 → 38 lines, 11-04 to 11-05).** Reconciled in §8.5: the count is a list-line count, and the change is a script edit that replaced per-unit lines with one directory line and added four entries. No coverage loss is identified.

### 8.5 Backup path-count change, 2026-11-04 to 2026-11-05

**Finding status: EXPLAINED (mechanism).** The journal count fell because a script change replaced one line per top-level systemd unit with one line for the whole `/etc/systemd/system` directory. The change added coverage. The exact 11-04 unit count is INFERRED, not observed. No backup coverage was lost, as far as the evidence shows.

#### 8.5.1 What the count measures

- Journal line: `paths to back up: N entries`, produced by `deploy/starship-backup.sh:226` (current `main`; line 176 in `543ab9312`, line 184 in `dbbfbae1a`).
- The count is `wc -l` of the file list `$STAGE/paths.txt`, which is written by one block (current lines 205–225). It is a count of **list lines**, not files and not configured paths.
- Each line is one of: the staging directory (1); each configured path that exists (a directory counts as 1 regardless of contents); and each `.env`-like file that the `find` clause returns.
- Configured paths that do not exist are not listed. They are logged as `note: <path> does not exist, skipped` (`deploy/starship-backup.sh:220`). No such note appears in any journal entry from 2026-11-01 to 2026-11-08 (VERIFIED, journal grep).
- The list is passed to `restic backup --files-from`. Restic then counts files, not lines. The restic file count is a separate measure (§8.5.5).

#### 8.5.2 Two script versions

| Element | Pre-11-03 version (`543ab9312`, 2026-10-10) | Current version (`dbbfbae1a` onward, 2026-11-03) |
|---|---|---|
| Fixed list lines including staging dir | 10 | 14 |
| Systemd units | One line per top-level `*.service` and `*.timer` in `/etc/systemd/system` (`find -maxdepth 1 -type f`) | One line: `/etc/systemd/system` (whole tree, including drop-ins and enable symlinks) |
| Added fixed entries | — | `/etc/systemd/system`, `/opt/deploy-guard`, `/etc/sysstat`, `/etc/systemd/journald.conf.d` |
| Removed | `find /etc/systemd/system -maxdepth 1 …` line | Same |
| `.env` clause | Identical | Identical (`find "$REPO_ROOT" -xdev … -prune -o … -name '.env' -o -name '.env.*'`) |

Source for both columns: `git show <commit>:deploy/starship-backup.sh` and `git diff 543ab9312 dbbfbae1a -- deploy/starship-backup.sh` (VERIFIED). The diff has three hunks. Its only removed line is the per-unit `find`. Its only added path entries are the four listed. The other additions are a chatterbox freeze variable and its command, and a comment.

#### 8.5.3 Reconciliation of the two nights

| Night | Journal count | Script version (inferred) | Fixed lines | Unit lines | `.env` lines | Source |
|---|---|---|---|---|---|---|
| 2026-11-03 02:42 | 99 | Pre-11-03 (`dbbfbae1a` committed 13:56 that day, after the run) | 10 | 65 (derived) | 24 (assumed) | Journal; `git log` |
| 2026-11-04 02:40 | 96 | Pre-11-03 | 10 | **62 (derived)** | 24 (assumed) | Journal; rollback copy below |
| 2026-11-05 02:40 | 38 | Current | 14 | 0 | 24 (current count) | Journal; `git show` |
| 2026-11-06 to 11-08 | 38 | Current | 14 | 0 | 24 (current count) | Journal |

Derivation and checks:

- The `.env` count now is **24**: the current `find` clause returns 24 entries (VERIFIED). The 11-05 count of 38 equals 14 + 24, so the two figures agree on the 11-05 run (VERIFIED arithmetic).
- No `.env`-like file was modified in the 11-04 → 11-05 window, and no directory under the repo changed mtime in that window (`find -newermt`, counts only). A deletion inside a directory would change that directory's mtime, so a deletion of `.env` files in that window is not supported (INFERRED from mtime semantics).
- Assuming 24 `.env` lines on 11-04, the 96 implies **62 unit lines** on 11-04 (96 − 10 − 24). The live count of top-level units is **64** (VERIFIED `find -maxdepth 1`). This 62 is derived from the journal, not counted independently. It is the only number in this table not directly observed.
- Arithmetic check: 96 − 38 = 58 = 62 (unit lines removed) − 4 (new fixed entries added). That is consistent. It is not independent evidence, because 62 is derived from the same two numbers.
- **The 11-03 → 11-04 difference of 3 lines (99 → 96) is not explained.** It would need 3 fewer unit lines or 3 fewer `.env` lines, or a different installed version. No evidence was found for any of these (UNKNOWN).

**Which version ran on 11-04.** The rollback copy `/root/backup-script-rollback-2026-11-04/backup.sh.orig` is **byte-identical to `543ab9312`** (`cmp`, VERIFIED). Its directory was last modified on 2026-11-04 at 16:44, after the 02:40 run (directory mtime, VERIFIED; creation time not recorded). The 11-05 verification report describes this copy as the rollback target for the pre-change script (DOCUMENTED, `reports/vm-audit/backup-verification-20261105.md:43`). Together these show the pre-change script was the one in place on 11-04, and the change was installed after that run (INFERRED; there is no installation record in the repo).

**Corroboration from the venv freeze.** The venv-freeze lines (`7a8dd3b84`, committed 2026-11-05 08:42) do not appear in the 11-05 journal, but do appear from 11-06. That matches an installed script that predates `7a8dd3b84` on 11-05 and was updated after 11-05 (VERIFIED journal; INFERRED install timing).

#### 8.5.4 Coverage implications

**What stopped contributing:** the per-unit lines. Each was a top-level unit or timer file. These are **covered by the directory line** (`/etc/systemd/system` as a whole), which is a superset: it includes the same unit files plus drop-ins and enable symlinks.

**What was added:** `/etc/systemd/system` (whole tree), `/opt/deploy-guard`, `/etc/sysstat`, `/etc/systemd/journald.conf.d`. **These were not backed up before the change.** This is a **coverage increase** from the 11-05 run onward. It is documented as a gap in the path list before 11-05 (`reports/vm-audit/units-b7897aa6.md:48`, which says drop-ins and enable symlinks were missed).

**Nothing removed from the fixed list.** The nine pre-change fixed entries are all still present in the current list (VERIFIED: the diff shows no removed path other than the `find`).

**Restic evidence of the change (documented, not re-run here):** the 2026-11-05 verification compares the previous snapshot `4fb41b3e` (252 files, 95.124 MiB) with `3ab9464e` (476 files, 95.196 MiB). It records `/etc/systemd/system` at 275 entries and `/opt/deploy-guard` at 5 entries, and calls the change a file-count increase (`reports/vm-audit/backup-verification-20261105.md:18`). The restic count supports the coverage-increase reading. It was not re-verified here, and no restic command was run.

**Persistent locations in §4 and the effect of this change.** None of the locations listed in §4 was in the path list before or after the change (except `delivery_ledger.txt`, which was listed in both). So this change did not alter their coverage. Their status is unchanged:

| Location | Covered elsewhere | Reconstructable | Verified status |
|---|---|---|---|
| `outputs/` (other than delivery ledger) | No | Partly, per file (not verified) | Excluded, not changed by this count change |
| `data/memory_graph.db`, `.cortex/memory.db` | No | Unknown | Excluded, unchanged |
| `/etc/self-improvement/` | No | Unknown | Excluded, unchanged |
| Coolify data | No | Decommissioned (§4A.3) | Excluded, unchanged |
| Infisical uploads volume | No | Empty (0 files) | Excluded, unchanged |
| Caddy ACME storage | No | Re-issued on boot (INFERRED) | Excluded, unchanged |
| Git stashes | No (`.git` not in list) | No | Excluded, unchanged |
| Uncommitted tracked change | No | No | Excluded, unchanged |

**Timeline correction to earlier statements.** Earlier revisions of this report listed `/etc/systemd/system`, `/opt/deploy-guard`, `/etc/sysstat` and `/etc/systemd/journald.conf.d` as backup coverage without a date. Coverage of these began with the **11-05** run. Snapshots before that (the 10-09 to 11-04 snapshots) did not contain them, except the top-level unit files. Any restore of those paths from a pre-11-05 snapshot would be incomplete (VERIFIED by the script history).

#### 8.5.5 Limits of the count as a coverage measure

- The count is list lines. It is not a file count, a byte count, or a measure of what restic actually stored. A single directory line can cover thousands of files. The 11-05 change shows this: 96 → 38 lines, with a file count increase.
- A count that stays the same can hide a changed path. The journal does not record which lines are in the list. A per-run path manifest would be needed for that.
- The count does not show deleted or excluded `.env` files. It shows only what the `find` matched at the time.

#### 8.5.6 Verified, inferred and unresolved

| Class | Statement | Source |
|---|---|---|
| VERIFIED | The count is `wc -l` of `$STAGE/paths.txt` | `deploy/starship-backup.sh:226` |
| VERIFIED | Missing configured paths are logged and not counted | `deploy/starship-backup.sh:220`; journal |
| VERIFIED | The per-unit `find` was removed and four fixed entries were added in `dbbfbae1a` | `git diff 543ab9312 dbbfbae1a` |
| VERIFIED | The `.env` clause is identical in both versions | `git show` both versions |
| VERIFIED | The 11-04 rollback copy is byte-identical to `543ab9312` | `cmp` |
| VERIFIED | The live count of top-level units is 64, and of `.env` matches is 24 | `find` (counts only) |
| VERIFIED | No `.env`-like file or repo directory changed in the 11-04 → 11-05 window | `find -newermt` (counts only) |
| VERIFIED | The "(root) LIST (root)" journal line is cron's log entry for the script's `crontab -l` call | Journal entry from `crontab[…]`, and `deploy/starship-backup.sh` (crontab line) |
| INFERRED | 62 unit lines on 11-04; the sum reconciles | Derived from journal, and from §8.5.3 |
| INFERRED | The pre-change script ran on 11-04 and the change was installed afterwards | Rollback copy timing; venv freeze timing |
| UNKNOWN | Why 11-03 (99) differs from 11-04 (96) by 3 lines | No evidence found |
| UNKNOWN | Exact unit lines on 11-04 | Not recorded; not observable now |

**The "(root) LIST (root)" journal line.** It is cron's log entry for the script's `crontab -l` call (`crontab-root.txt`), not a backup error. It appears in the journal on five of the six runs from 11-03 to 11-08 (not on 11-05). **Corrected from "six occurrences".** Its absence on 11-01 and 11-02 is UNKNOWN, and it is not explained by any change found in this investigation.

#### 8.5.7 Future actions (DOCUMENTED ONLY)

1. **Record a per-run manifest.** Write the path list (or its hash and line count per category) to the journal or to a local file. This makes the count auditable without printing secrets.
2. **Split the count.** Log fixed-path lines, unit lines and `.env` lines separately, so a change like 11-05 is visible without reconstruction.
3. **Record the script commit** in each run's first journal line, so the installed version is known for every night.
4. **Explain the 3-line change between 11-03 and 11-04** from the installed-script history or from `.env` file history.
5. **Confirm the installed script matches the repo** after each change, using a byte comparison. This is the same check as in the integrity doc.
6. **Re-verify the 11-05 restic coverage** for `/etc/systemd/system`, `/opt/deploy-guard`, `/etc/sysstat` and `journald.conf.d` against the repo list, with authorization.

**Status: OPEN — DOCUMENTED ONLY.** Priority LOW. No coverage loss has been identified. The count change is a list-line effect of the 11-03 script change, and the change added coverage.

## 9. Top five recovery gaps, ranked by impact (revised)

Impact ranking considers: how much of the rebuild is blocked, how many items are affected, whether a route exists, and how likely it is to be missed.

1. **Off-VM custody of the three gating secrets is unverified (restic password, Google OAuth client, Infisical `ENCRYPTION_KEY` and `AUTH_SECRET`).** Everything depends on them, and the repo cannot show they exist in the password manager. Evidence needed: owner confirmation of custody, not values. Label: UNKNOWN custody, VERIFIED dependency.
2. **Stash-only commits (57) and unpushed local branches (153, pushed status UNKNOWN) survive only on this VM and in the bundle.** Stashes have no route at all. Unpushed branches have only the bundle and restic. Label: VERIFIED.
3. **Operational state outside the backup path list.** Largest by consequence: `outputs/` (36 MB, 21 files, 1 of 21 backed up), `.cortex/memory.db` (30 MB), `data/memory_graph.db` (920 KB), `data/alert_state`, `/etc/self-improvement`, Coolify (6.5 MB plus 100 MB database volume, key material in `source/.env`). Label: VERIFIED exclusion. Regeneration per item UNKNOWN.
4. **Infisical recovery depends on a reconstructed compose, a stale label path, and an uncertain `coolify` network.** The repo compose was rebuilt from transcript after a 2026-09-24 loss (E19). The private compose differs from the repo copy (E23). Containers reference a path that does not exist (E21, E22). The `coolify` network is external (E20). Logical restore is the only Infisical route (no physical copy). Label: VERIFIED structure, DOCUMENTED test.
5. **No full restore has ever been recorded. The first weekly integrity check completed on 11-08 (sampled, 1 in 20 packs; §16).** Integrity samples are small. The Supabase and Infisical tests are documented from 10-09. Label: DOCUMENTED and VERIFIED (timer).

**Revision 1 gap ranking, for comparison:** 1 credentials, 2 uncaptured state, 3 Infisical, 4 git coverage, 5 restore evidence. Revision 2 keeps the same five items but changes the order of 2 and 4 because stash and unpushed-branch loss are now quantified and have no route.

## 10. Unresolved questions and evidence needed

| # | Question | Evidence that would settle it | Who can supply it | Access needed |
|---|---|---|---|---|
| Q1 | Do the restic password, the Google OAuth client ID and secret, and Infisical `ENCRYPTION_KEY`/`AUTH_SECRET` exist in the owner's password manager, and are they current? | Owner confirmation of item presence and last-updated date (no values) | Owner | None from VM |
| Q2 | Does the current remote repository hold 12 snapshots, and which dates? | `restic snapshots --compact` on the remote repo | Owner, or an operator with access | Remote access (forbidden in this task) |
| Q3 | Which snapshot was removed on 11-05 and 11-06? | Remote snapshot list, compared with journal IDs in E11 | As Q2 | As Q2 |
| Q4 | Does the private `infisical-compose/docker-compose.yml` or the repo copy match the running containers? | **Partly answered (§4A.2):** neither is demonstrated to reproduce the deployment. Structure matches; DB and Redis image references, aliases, labels and DB user env do not. Remaining: a compose resolution in an isolated sandbox (Q15). | Operator on a sandbox host | Sandbox `docker compose config` comparison |
| Q5 | What do the Supabase dumps' TOC lists differ by (92 lines, 11-03 to 11-06)? | **Partially answered (§8.4):** candidate cause is migration `0249` moving seven tables to `archive`. Entry-level comparison still needs the 11-03 dump, which is not local. Application date of `0249` is also unknown. | Owner or operator | Migration history from Supabase (owner); 11-03 dump only through an authorized restore to scratch |
| Q6 | Are the 57 stash-only commits and the 153 unpushed branches reachable from any remote? | GitHub branch and tag listing | Owner, or GitHub admin | Remote inventory (forbidden in this task) |
| Q7 | Do the `coolify` Docker network and Coolify's key material survive a rebuild? | **Partly answered (§4A.3):** Coolify is decommissioned and no TJRHQ dependency exists. The network must be created by name. Whether `APP_KEY` encrypts anything still needed: UNKNOWN. | Owner, plus Coolify product docs | Documentation only |
| Q8 | Does the Infisical uploads volume matter? | Already answered: 0 files | — | — |
| Q9 | Are any Redis volume keys required after restore? | Application code that reads from Redis at startup | Code review | None |
| Q10 | Does the old `gdrive:starship-backups` repo still exist, and does it hold snapshots absent from the new repo? | Remote listing | Owner | Remote access (forbidden) |
| Q11 | Has the first weekly integrity run passed? | `journalctl -u starship-backup-integrity.service` after 11:30 AEDT on 11-08 | Operator on this VM | Read-only journal access |
| Q12 | Is SEC-01 administratively closed in the form stated? | The risk-acceptance record referenced by commit `8d44f1cdd` | Owner | Repo read |
| Q13 | Does Supabase Storage hold binaries, and are they needed? | Supabase project storage listing | Owner | Supabase dashboard |
| Q14 | Do Vercel environment values exist and can they be read back or re-entered? | Vercel project settings | Owner | Vercel dashboard |
| Q15 | Does either compose file resolve to the running configuration? | Resolve both in an isolated sandbox host (not this VM), compare resolved images, networks, aliases, volumes, labels, env names. Secrets must not be printed. | Operator with a sandbox | Sandbox only |
| Q16 | Why were Coolify images (`coollabsio/coolify`, `coolify-realtime`, `traefik`, `sentinel` ×2, `gitleaks`, `pgvector`) removed between 2026-11-03 and 2026-11-08? | Docker daemon event log (`docker events --since`), shell history, or the operator who ran the cleanup. Not documented in repo. | Owner or operator | Read-only daemon event log |
| Q17 | Which DB role does a fresh init create when `POSTGRES_USER` is absent? | Confirm the compose used to create `infisical_infisical-db` at the time (volume creation metadata). Behaviour of the postgres image on init: INFERRED. | Operator | Read-only volume creation metadata |
| Q18 | Retain or delete Coolify residue (volumes `coolify-db`, `coolify-redis`; `/data/coolify`; `coolify` network)? | Owner decision. The VM-OPTIMISE plan (line 74) says not to delete without review. | Owner | Decision only |
| Q19 | Does Coolify use `APP_KEY` to encrypt values stored in `coolify-db`? | Coolify product source or docs | Owner, or Coolify docs | Documentation only |
| Q20 | Should a public Infisical route be restored? Current Traefik labels route nothing; no Caddy site serves the Infisical hostname. | Owner decision | Owner | Decision only |
| Q21 | Is the Infisical machine identity (`.infisical-auth.env`) still valid after a DB restore? | A login test on a restored host | Operator on a restored host | Restored host only |
| Q22 | Should the Redis password be rotated and moved out of the command line? | Owner decision (exposed in this session, §4A.7) | Owner | Decision and rotation |
| Q23 | Should `/data/coolify/source/.env` and its dated copies be restricted to `0600` or removed? | Owner decision | Owner | Decision and `chmod` |

## 11. Corrections to revision 1

| Revision 1 claim | Status | Correction |
|---|---|---|
| "The last eight runs logged `finished OK`" | Corrected in rev 1 | Rev 1 wording "six runs" was also incomplete: the journal shows `finished OK` on each night in the window (11-01 to 11-08 verified, §16 item 1). |
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
6. Create the external `coolify` Docker network by name (§4A.4 step 2). Coolify is decommissioned and need not be restored (§4A.3).
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

## 16. Consolidated Four-Agent Architecture Investigation

**Status:** complete for all four workstreams, with owner-only gaps listed in §16.10. Evidence cutoff 2026-11-08 11:46:53 AEDT. Document state at the start of this investigation: PR #610 head `26d19196b`, verified by `gh pr view` and by the local worktree HEAD.

### 16.0 Method and labels

- Four read-only specialists, one per workstream: (1) disaster recovery and data integrity; (2) identity, authorization and secrets; (3) automation, deployment and failure handling; (4) observability, audit and evidence assurance. Agent 4 also assured the report's claims. No specialist edited a tracked file, committed, pushed, created a branch or PR, or changed the live checkout.
- Labels: **VERIFIED** (directly observed in the evidence, command or file:line cited). **INFERRED** (plausible reading of evidence, assumption stated). **UNKNOWN** (not established; the evidence that would settle it is named). **CONTRADICTED** (an earlier claim disproved by newer or primary evidence; the correction is given in §16.7).
- Provenance marks. **[LC]** means the lead re-checked the claim against the source in this session. **[AR]** means a specialist cited file:line with a verified read, but the lead did not re-open that line. Items marked [AR] are reported at the strength the specialist gave them, not higher.
- Live-state rules followed: no service, timer, container or alert was started, stopped, triggered or cleared. No database, restic, rclone or live HTTP request was made. No secret value, raw `docker inspect` output, `.env` content or credential-bearing log line was read. Agent 3 made one read-only GitHub API call that returned 403; no workflow was dispatched.

### 16.1 Executive findings summary (verified findings, ranked by operational impact)

1. **Command Centre `/api/config` returns the backend API key without authentication (CB-01).** [LC] `core/command-centre/backend/app.js:81` exempts `/api/config` from the auth middleware; the handler at lines 106–108 returns the key; the server listens on all interfaces (`app.js:240` `app.listen(PORT)`, live `ss` shows `*:5000`). [LC] Host `ufw` has `DEFAULT_INPUT_POLICY="DROP"` and no rule for 5000. [LC] Caddy proxies only `/api/v1/*` and `/health` (`deploy/caddy/Caddyfile.v3` `@api` matcher). **Net exposure: local processes and local users can read the key; it is not reachable from the internet through the host firewall.** The key grants every `/api/v1` write. Severity HIGH for the local threat model. Hardening is needed regardless (see FA-01).
2. **Commits on `origin/main` deploy to the production VM without an approval gate (CB-14).** [LC] `deploy/auto-deploy.sh` fast-forwards `origin/main` and restarts units on a timer (`auto-deploy.service`, `User=deploy`). [LC] A search of the script finds no CI-status or check-run gate; its only `status` matches are `git status`. [AR] Restart failures are logged and the script can exit 0. Branch protection and required reviews on `main` are **UNKNOWN**: the GitHub API returned 403 to the read-only query.
3. **Backup component failures can exit 0 (contradicts the script header).** [LC] `deploy/starship-backup.sh` line 25–27 says any failure exits non-zero. [LC] Lines 121 (`cp` of the cached dump), 126 (log-only branch), 220 (missing critical paths, logged as a note only) and 222–223 (the `find`) are not checked. [LC] Lines 73, 152 and 153 end in `|| true`. The `set -uo pipefail` at line 32 has no `-e`. Result: a silent partial backup is possible, and the journal would show `finished OK`.
4. **`mission-engineering-dispatch` has been silent since 2026-10-28 and per-mission failures exit 0.** [LC] `systemctl list-timers` shows the timer enabled, with NEXT blank and LAST `Wed 2026-10-28 20:43:09 AEDT`. [LC] `core/engineering/mission_dispatch.py:329` returns 0 on the normal path and `sys.exit(main())` at line 333. No alert path is configured for this unit. [AR] Its unit description still says "every 15 minutes". The reason for the stop is UNKNOWN; no record was found.
5. **Infisical client secret is passed on the command line during login (new).** [LC] `platform-runtime/lib-infisical.sh:60-62` passes `--client-secret=` as an argv argument. The value is visible in `/proc/<pid>/cmdline` for the duration of the login. Whether `hidepid` is set on `/proc` is UNKNOWN. Pattern only; no value read.
6. **The backend accepts the API key in the query string (new).** [LC] `core/command-centre/backend/app.js:88` `const provided = req.headers['x-api-key'] || req.query.api_key;`. A key in a URL can be written to access logs. [AR] The Caddy log filters do not redact the URI (`deploy/caddy/Caddyfile.v3` ~lines 154, 287). Whether URIs reach logs on the live host is INFERRED, not verified.
7. **Redis credential exposure (SEC-DR-01, existing) is preserved.** Verified via §4B. Rotation is owner-only.
8. **Restore depends on three owner-held secrets (existing, §7.1).** The restic password, the Google OAuth client and the Infisical keys are not on the VM by design. Custody is UNKNOWN (Q1).
9. **The backend uses the Supabase service-role key for all database access (CB-02).** [AR] `supabase-connector.js:16`, `api/capture.js:25`, `connectors/intelligence-adapter.js:29`, `api/captains-log.js:211`. Any compromise of the single key gate is therefore a service-role compromise (bypass of row-level security). Live RLS state is UNKNOWN; migrations show a permissive `anon_read` policy on two intelligence tables (`0035`, CB-08) [AR].
10. **Two chat and message entry points lack user-level authorization.** [AR] Telegram gate is per chat, not per user (`core/platform/telegram_access.py:21-41`, CB-11). [AR] The Slack research command logs "allowing all users" with no check (`platform-runtime/commands/research_command.py:213-214`, CB-12). The LCARS mutating routes listed in §16.3 need only a session, not the Captain role (CB-13) [AR].

**Also material (not in the top ten):** the 0249 archive move reduces dumped Supabase coverage from 11-03 onward (§8.4, VERIFIED on the migration and script; application date self-reported only, §16.7); the alert pipeline cannot detect its own send failures (`alert_on_systemd_failure.py:199-203` returns 0 on send failure [AR]); and the auto-deploy script can exit at `git fetch` under `set -e` after stashing `data/self-improvement` (`auto-deploy.sh:135-136`, `:233` [AR]).

### 16.2 Recovery coverage matrix (Agent 1, reconciled)

| Component | Required state | Existing recovery source | Evidence | Status | Gap |
|---|---|---|---|---|---|
| Restic repository `gdrive2:starship-backups-v2` | Reachable with password and OAuth client | Off-VM Google Drive, owner custody | `deploy/starship-backup.sh:42`; runbook §1 | IRREPLACEABLE (single provider) | Custody UNKNOWN (Q1) |
| Restic password `/root/.restic-pass` | Present for backup and restore | Owner password manager only | Mode 600 root (`stat`); script:43; not in path list | IRREPLACEABLE | No on-VM fallback, by design |
| rclone `gdrive2` config | Token for Drive | Re-authorise with owner Google account | Mode 600 root (`stat`); script:35,42 | RECONSTRUCTABLE (owner input) | Needs OAuth client secret |
| Old repo `rclone:gdrive:starship-backups` | Fallback, if still present | Unknown | runbook lines 46–47 | UNKNOWN | Remote check prohibited (Q10) |
| Infisical `ENCRYPTION_KEY`, `AUTH_SECRET` | Decrypt Infisical DB | `/root/private-knowledge/infisical-recovery.env` (in backup, script:217) | Mode 600 (`stat`); runbook §4 | COVERED, behind restic password | Chained dependency |
| Infisical Postgres | Logical restore | `pg_dump` custom format | script:130–138 | COVERED (logical) | Physical volume `infisical_infisical-db` not backed up (2,124 files, 84 MB) |
| Infisical Redis volume | Cache or state, role UNKNOWN | None | Volume present (12 MB) | UNKNOWN | Not backed up |
| Infisical compose | Authoritative definition of running stack | Repo copy and private copy | §4A.2 | UNKNOWN | Neither demonstrated; label path stale |
| `.infisical-auth.env` | Service machine identity | Backed up | script:211; mode 640 root:infisical-readers (`stat`) | COVERED | Validity on new host UNKNOWN |
| Supabase `public`, `auth`, `storage`, `supabase_migrations` | Data | `pg_dump` | script:66–67 | COVERED | RPO up to about 72 h (§8.3) |
| Supabase `archive` schema (7 tables moved by 0249) | Data | None off the live project | script:67 excludes it; migration 0249 | IRREPLACEABLE for that data | Silent coverage reduction from 11-03 (§8.4) |
| Supabase grants (roles `xo_bot`, `revs_bot`, `telegram_engineer_ro`) | Role grants | Migrations, if re-run | script:67 `--no-privileges`; §8.4.3 (no ACL entries) | RECONSTRUCTABLE only if migrations re-run cleanly | Re-run untested [AR] |
| Supabase Vault | Secrets | Re-enter from Infisical | runbook line 28; no `vault.create_secret` call sites found [AR] | UNKNOWN | Secret count and mirroring UNKNOWN |
| Supabase Storage binaries | Files | None | Not in dump; no `.storage.from(` call sites found [AR] | UNKNOWN | Whether buckets hold objects needs dashboard or DB (Q13) |
| `cron.job` rows | Schedules | Data-only SQL | script:71–73 | COVERED | |
| Git branch heads (203 local) | All heads | `git bundle --branches` | script:144–145 | COVERED while bundle survives | 153 heads have no `origin/*` counterpart (VERIFIED) |
| Git tags (108 local) | Tag refs | None (`--branches` excludes tags) | `git for-each-ref` [AR] | UNKNOWN; IRREPLACEABLE if not pushed | 107 are `archive/*`; 92 commits reachable only from tags [AR]; GitHub state UNKNOWN |
| Git stash (21 entries; 57 stash-only commits) | Stash commits | None | §6, §4 | IRREPLACEABLE | Not in bundle, `.git` not in restic (script:222–224) |
| Live checkout uncommitted work | 2 entries | None unless in path list | `git status` | IRREPLACEABLE (small) | Not captured |
| Other worktrees | Clean at scan | Via bundle | [AR] | COVERED | |
| `.cortex/memory.db` (31 MB) | Agent memory store | None | `stat`; gitignored | IRREPLACEABLE, regeneration UNKNOWN | Not backed up |
| `data/memory_graph.db` (920 KB) | Memory graph | None | `stat`; gitignored | IRREPLACEABLE, regeneration UNKNOWN | Not backed up |
| `/root/.claude` (187 MB, 5,762 files) | Session and memory state | None | [AR] `du`, `find` | UNKNOWN | Off-VM copy not checked |
| `outputs/` (21 regular files, 36 MB) | Logs and state | Only `delivery_ledger.txt` (script:208) | §4 | UNKNOWN per file | Remainder not backed up |
| `/root/.ssh` | Keys and `authorized_keys` | None | Mode 700 [AR] | RECONSTRUCTABLE (owner key) | `authorized_keys` lost |
| Caddy ACME (`/var/lib/caddy`, `/root/.local/share/caddy`) | Certificates | Re-issue | Not in path list | RECONSTRUCTABLE | Let's Encrypt rate limits INFERRED |
| `/etc/ssh` host keys | Host identity | Regenerate | [AR] | RECONSTRUCTABLE | Clients must re-trust |
| `/etc/ufw` rules | Firewall | Status text only (`script:152`) | `ufw status` [LC] | UNKNOWN (partial) | Rules file not backed up |
| Coolify (`/data/coolify`, volumes `coolify-db`, `coolify-redis`) | Decommissioned | None | §4A.3 | UNKNOWN (owner decision, Q18) | Key material loss, not required for TJRHQ |
| Ollama models (`/usr/share/ollama`, about 55 GB) | Model weights | Re-pull | runbook; [AR] | RECONSTRUCTABLE | Time and bandwidth |

**Irreplaceable (no source off the VM or the live project):** the restic password (custody only), the `archive` schema data (live project only), git stash commits, git commits reachable only from unpushed tags or branches, `.cortex/memory.db`, `data/memory_graph.db`, the live checkout's uncommitted work, and `/root/.claude` memory unless copied elsewhere. **Reconstructable:** rclone configuration, SSH keys (owner copy), ACME certificates, Ollama models, Infisical compose (given the recovery env), and Supabase grants (if migrations re-run). **Unknown:** Supabase Storage objects, Vault contents, the old restic repository, Coolify key material, GitHub-side copies of tags, branches and stashes.

### 16.3 Authorization matrix (Agent 2)

| Entry point | Operation | Intended identity | Enforcement | Evidence | Confidence |
|---|---|---|---|---|---|
| Command Centre `/api/v1/*` (all writes) | Capture, mission status, captain's log, advisory, notifications, governance, health pulses | Owner's LCARS server | Global `X-Api-Key` middleware (`app.js:80–94`); 503 in production with no key (`app.js:84`); query-string key accepted (`app.js:88`) | [LC] `app.js:80–94`; [AR] Caddy `@api` matcher | High while the key stays secret |
| Command Centre `/api/config` | Returns the key | "local-only" per comment | Exempt (`app.js:81`); no IP or host check | [LC] `app.js:81`, `:106–108` | Verified; local exposure only |
| Intelligence-governance `POST /` | Spawns Python dispatch with a role | Portal server only | Trusts the role from the portal; API-key gate only (`api/intel-governance.js:11–14`) | [AR] | Medium |
| Intelligence `POST /generate` | Spawns scheduler | Owner | API-key gate only; `days` passed as argv string (`api/intelligence.js:108–120`) | [AR] | Medium |
| LCARS `app/api/*` mutations (57 route files) | Captain actions | Captain via Supabase session | `middleware.ts:145` `getUser()` for non-public paths; most routes add their own guard | [AR] | High for guarded routes |
| LCARS mutations with no route-level role check: `self-improvement/decide`, `self-improvement/opportunities/decide`, `settings` PUT, `tts/speak` | Decisions, writes, paid TTS | Captain | Session only; any authenticated user passes | [AR] (CB-13) | Medium; depends on signup setting (UNKNOWN) |
| LCARS mobile bearer writes | Captain writes | Captain bearer | `MOBILE_BEARER_WRITE_ROUTES` and `requireCaptainWrite()` | [AR] | High |
| Self-improvement dashboard `/api/decide`, `/api/opportunity/decide` | Captain decisions | Captain via portal proxy | `before_request` fail-closed, `hmac.compare_digest` (`dashboard.py:638–650`) | [AR] | High (SEC-01 area, not reopened) |
| Context service `127.0.0.1:5001` | Captain context reads | Local callers | `X-Context-Service-Secret`; **returns open when the secret is unset** (`context_service.py` ~324–331) | [AR] | Medium; deployed env UNKNOWN (CB-07) |
| TTS services (kokoro, chatterbox) | Speech generation | Portal | `X-TTS-Secret`, fail-closed when unset; both bind `0.0.0.0` | [AR] | Medium |
| Telegram XO, capacitybot, resiliencebot | Actions, including `systemctl restart tg-xo.service` (`xo/app.py:531`) | Captain chat | Chat-ID allowlist, fail-closed on empty list; no user-ID check | [AR] (`core/platform/telegram_access.py:21–41`) | Medium (CB-11) |
| Slack research command | Runs research or LLM jobs | "Captain, XO, designated researchers" (comment) | **None**; logs "allowing all users" | [AR] `research_command.py:213–214` (CB-12) | Low |
| GitHub workflows | CI | Repository | `python-ci` `contents: read`; `lcars-portal-ci` has no permissions block; scorecard `read-all` with `id-token: write`. No deploy job, no `environment:` keys | [AR] `.github/workflows/*.yml` | Medium |
| `deploy/auto-deploy.sh` (`User=deploy`) | Fast-forward `origin/main`, install, restart | Push access to `main` | No CI gate, no PR gate in repo; branch protection UNKNOWN | [LC] (no check gate) | Low for change control (CB-14) |

### 16.4 Credential-boundary risk register

Severity is the lead's view of impact in the stated threat model. "Live" means whether the live system matches the code.

| ID | Risk | Evidence | Label | Severity | Future action | Owner authorization |
|---|---|---|---|---|---|---|
| CB-01 | `/api/config` returns the backend key unauthenticated | `app.js:81`, `:106–108`; ufw default DROP, port 5000 not allowed [LC] | VERIFIED (code and host firewall); external reachability blocked | HIGH (local); hardening needed | FA-01 | Yes, plus key rotation |
| CB-02 | Backend uses the service-role key for all queries (bypasses RLS) | [AR] `supabase-connector.js:16` and three more | VERIFIED (code) | HIGH | FA-09 (per-route least-privilege client) | Yes |
| CB-03 | `command-centre.service` runs `node app.js` with no Infisical wrapper; secrets come from repo-root `.env` via `dotenv` | [LC] `deploy/command-centre.service` `ExecStart=/root/.nvm/…/node app.js`; [LC] `app.js:19–20` dotenv | VERIFIED | MEDIUM–HIGH (bypasses the secret store) | FA-03 | Yes |
| CB-04 | Infisical client secret on argv | [LC] `lib-infisical.sh:60–62` | VERIFIED (pattern) | MEDIUM | FA-04 | Yes |
| CB-05 | API key accepted in the query string; Caddy log filter does not redact URIs | [LC] `app.js:88`; [AR] Caddy log filters | VERIFIED (acceptance); INFERRED (logged) | HIGH if logged | FA-02 | Yes |
| CB-06 | Caddy drop-in provides `BACKEND_API_KEY` but Caddy no longer injects it | [AR] `deploy/caddy.service.d/apikey.conf:4`; `Caddyfile.v3:46–48` | INFERRED (unused copy) | LOW–MEDIUM | FA-23 | Yes |
| CB-07 | Context service fails open when its secret is unset | [AR] `context_service.py` ~329–331 | VERIFIED (code); deployed env UNKNOWN | MEDIUM | FA-24 | Yes |
| CB-08 | Residual `anon_read` policy on two intelligence tables | [AR] `0035`, no later drop found | VERIFIED (history); live UNKNOWN | MEDIUM–HIGH | FA-10 (owner runs `pg_policies`) | Yes |
| CB-09 | Tables created without `ENABLE ROW LEVEL SECURITY` in migrations | [AR] `0001`, `0024`, `0026`, `0124`, `0125`, `0126` | INFERRED; live `rowsecurity` UNKNOWN | HIGH if PostgREST exposes them | FA-10 | Yes |
| CB-10 | Migration `0239` applied by hand, not as written | [AR] `0239` header note | VERIFIED (file) | MEDIUM (history unprovable) | FA-15 | Yes |
| CB-11 | Telegram gate is per chat, not per user | [AR] `telegram_access.py:21–41` | VERIFIED (code) | MEDIUM | FA-13 | Yes |
| CB-12 | Slack research command has no authorization | [AR] `research_command.py:213–214` | VERIFIED (code) | MEDIUM (spend, data access) | FA-12 | Yes |
| CB-13 | LCARS mutating routes without Captain role check | [AR] §16.3 | VERIFIED (code); signup setting UNKNOWN | HIGH if signup open | FA-11 | Yes |
| CB-14 | Code on `main` runs on the VM as `deploy` | [LC] `auto-deploy.sh`, no CI gate; branch protection UNKNOWN | VERIFIED (mechanism) | HIGH (change control) | FA-05 | Yes |
| CB-15 | SEC-01 Caddy containment: active state unknown | [LC] live and repo `Caddyfile` both contain the "NOT DEPLOYED" marker text twice; active blocks not determinable by grep | UNKNOWN | HIGH if containment is absent | FA-14 | Yes |
| CB-16 | Infisical service wrappers missing for about 19 units, including command-centre, auto-deploy and starship-backup | [AR] unit scan | VERIFIED (scan) | MEDIUM | FA-03 (extend) | Yes |

### 16.5 Automation and failure-detection matrix (Agent 3)

| Job or workflow | Trigger | Failure signal | Alert path | Recovery procedure | Evidence | Gap |
|---|---|---|---|---|---|---|
| `starship-backup.service` | Timer 02:40 AEDT; enabled and active; last run 11-08 02:40, finished OK | exit 1 for listed failures; exit 75 for lock contention | `OnFailure=alert-on-failure@` [LC unit] | Pre-lockfix backup copy in `/opt/starship-backup/` (dated 11-08); documented rollback in integrity doc | [LC] script `:249–252`; journal | Component failures can exit 0 (§16.1 item 3) |
| `starship-backup-integrity.service` | Sunday 11:30 AEDT; NEXT 11-15 | `flock` or restic non-zero | `OnFailure` [AR] | Documented (placeholder `<date>` in rollback) | [LC] journal 11-08 11:30:20–11:30:48 | Sampled 1 in 20 packs; no success marker |
| `auto-deploy.service` | Timer every 5 min; fast-forward `origin/main`; no CI gate | ABORT exit 1 (dirty tree, ff failure, fetch) | `OnFailure` yes; dirty-tree alert debounced 30 min [AR] | Manual git on VM | [AR] `auto-deploy.sh:226,241–244,337,383,391` | Restart failures logged then exit 0; main commits deploy unreviewed |
| `mission-engineering-dispatch` | Timer every 15 min, stopped in practice since 10-28 | Per-mission failures still exit 0 | None | None documented | [LC] `systemctl list-timers`; [LC] `mission_dispatch.py:329` | Silent about 10 days; stop reason UNKNOWN |
| `hq-evolution.service` | Timer 03:00 | Exception, heartbeat failure, nonzero exit | None | `Restart=on-failure`, `RestartSec=300`, no `StartLimit` [AR] | [AR] `evolution_orchestrator.py:871–877` | Unbounded restarts; comment "restart once" is CONTRADICTED by config |
| `self-improving-system.service` | Timer 04:34 | Nonzero exit | `OnFailure` yes; 2 h cooldown; `StartLimit` 5/h [AR] | Restart 300 s | [AR] 13 failure marks, 10 restarts in 14 days, last 11-05 07:53 | Cooldown hides repeats |
| GitHub CI (`lcars-portal-ci`, `python-ci`, scorecard) | PR; push to `main`; scorecard also schedule and dispatch | CI status | None | None | [AR] workflow files | No deploy job, no `environment:` protection |
| `deadmans-switch.service` | Timer 10 min | Nonzero | None | None | [AR] | The watchdog is itself unwatched |
| Cron draft worker (`*/30`) | Cron | Unknown | None | None | [AR] crontab (one entry) | UNKNOWN |
| `alert-on-failure@` path (`alert_on_systemd_failure.py`) | Triggered by `OnFailure` | Send failure | Telegram via XO bot | None | [AR] `:199–203` returns 0 on send failure | Alert failure is silent; the alert unit has no `OnFailure` of its own |

**Answers to the four specific questions.** (a) Can a failed scheduled task exit successfully and escape detection? **Yes.** Backup component failures, the restart-failure swallow in auto-deploy, dispatch per-mission failures, and any stopped timer are all silent [LC, AR]. (b) Does each critical job have an alert path? **No.** 6 of 42 deploy units carry `OnFailure=`; the dispatch, deadman's switch, verification and delivery units do not [AR]. (c) Is the alert destination usable? **INFERRED yes**, the Captain's chat via the XO bot. No live test was made (prohibited); the journal has zero "alert send failed" lines in 14 days [AR]. (d) Are alert failures observable? **No** [AR]. (e) Does deployment preserve the owner approval boundary? **Not for the VM path.** Push rights to `main` are the only gate [LC, AR]. (f) Is the first weekly integrity result documented? **Now yes, in the journal** (11-08 11:30:48: "no errors were found", 12 of 12 snapshots, 4 of 52 packs). **The integrity doc records no result**, and §16.7 corrects the report's "pending" wording.

**Additional findings from Agent 3 (not in the report before this section):** `auto-deploy.sh:135–136` stashes `data/self-improvement`, but the restore runs only at `:227`, `:243` or `:250`; the `git fetch` at `:233` runs under `set -e` (`:74`) and can exit before restoring [AR]. The stash count is 21 and the auto-deploy-labelled entries are UNKNOWN (the default stash message is "WIP on main"). The alert state file contains a key for `some-other.service` with a timestamp identical to `auto-deploy.service` [AR]: likely test residue, INFERRED. Unpinned images: `postgres:17` (backup), `postgres:15-alpine` and `redis:7-alpine` (Infisical compose), with `infisical` pinned by digest; no documented rollback for Infisical, Postgres or Ollama [LC grep]. The `starship-backup.sh:139` `docker inspect` output of the Infisical containers is written into the restic snapshot; its content was not inspected (INFERRED risk for owner review). Stopped timers are not detected at all.

### 16.6 Audit and evidence-assurance matrix (Agent 4)

**Audit and traceability inventory (condensed).**

| Record | Store | Writer | Retention | Correlation key | Gap |
|---|---|---|---|---|---|
| Audit events | Supabase `audit_events` | `core/platform/audit_service.py:59`; callers `intelligence/governance/workflow_gate.py:165` and two more [AR] | 90 days (`0221`, daily cron 03:50); included in dump | actor, category, action; no run or commit ID | Docstring says no production caller, contradicted by callers (production status INFERRED) |
| Escalation acknowledgement | Supabase `escalation_events` | `platform-runtime/escalation_manager.py:255–272` [AR] | Not found | `alert_key` | Retention not verified |
| Captain approval queue | None found | n/a | n/a | n/a | Approval record store UNKNOWN |
| Agent command execution | SQLite `outputs/command_bus.db` (20 KB) | `core/coordination/command_bus.py:43,131,136–152` [AR] | Pruning not checked | `event_key`, `mission_id` | Not backed up (`outputs/` excluded) |
| XO decisions | Supabase `command_memory_records` | `lib/officers/xo_orchestrator.py:270` [AR] | Not checked | None | Not joined to other records |
| Backup run log | journald | `starship-backup.sh:78,226`; restic prints snapshot IDs | Restic 7/4/3; journald cap 1 GB, disk at cap (1,022.9 MB); earliest backup journal entry 2026-10-13 [AR] | Snapshot ID only | `forget` output truncated by `tail -15` (`:243`) |
| Deploy events | journald and git | `auto-deploy.sh:246` logs "pulled $LOCAL_SHA → $REMOTE_SHA" | As journald | Commit SHA | No deploy record store; 75 "pulled" lines since 11-01 |
| Alert state | `data/alert_state/` (last_alert.json 289 B) | `core/platform/deadmans_switch.py:157–173` [AR] | None | None | No acknowledgement record |

**Correlation.** The only shared keys are the restic snapshot ID (journal only), the commit SHA (auto-deploy journal and git) and `mission_id` (command bus and the Telegram callback). No key joins a backup run, a deploy and an approval. The bundle step logs size and ref count only (`starship-backup.sh:144–146`), so there is no backup-to-commit mapping.

**Assurance matrix (selected rows; 35 claims were checked).**

| # | Claim (short) | Source | Label used | Assurance result | Missing proof |
|---|---|---|---|---|---|
| A1 | Backup "ran successfully on every night from 2026-11-03" (§1) | Journal | VERIFIED | Understated: runs OK from 11-01 and earlier in window | None |
| A2 | Supabase dumps 10-28, 10-31, 11-03, 11-06 with TOC 1966/1966/1985/1893 | Journal | VERIFIED | Confirmed | Restore test |
| A3 | Dump only at cache age ≥ 71 h | `starship-backup.sh:56–57,103` | VERIFIED | Confirmed | None |
| A4 | Restic printed 11 after 11-07, 12 after 11-08 | Journal | VERIFIED (log line) | Incomplete: "11 snapshots" also printed 11-01 | Meaning as count: INFERRED |
| A5 | 10-29 snapshot "aged out" on 11-05 (§8.1) | Script `:241` and journal | INFERRED | Model ignores weekly and monthly exceptions in detail | Remote list (Q2, Q3) |
| A6 | Weekly integrity "first run pending" (E16, §8.2, Q11) | Journal | **CONTRADICTED** | Run completed 11:30:48 with "no errors were found", 12/12 snapshots | Corrected in §16.7 |
| A7 | "(root) LIST (root)" on "six" runs (§8.5.6) | Journal | **CONTRADICTED** | Five occurrences: 11-03, 04, 06, 07, 08 | Corrected |
| A8 | "Six runs, 2026-11-03 to 2026-11-08" (§11) | Journal | **CONTRADICTED** | Finished OK on each night in the window | Corrected |
| A9 | Compose `name: infisical` at line 12 and external network at lines 21, 52–54 (E20) | Repo compose | **CONTRADICTED** | Repo copy: name at 16, external at 106. Lines 12, 54 belong to the **private** copy. | Corrected |
| A10 | Quoted phrase "exists today; Infisical is attached to it" in repo compose | Git | **CONTRADICTED** | Phrase is only in the private copy (line 54) | Corrected |
| A11 | Running containers reference `/root/TJRHQ` compose path; directory absent | `docker inspect` label; `test -d` | VERIFIED | Re-checked | None |
| A12 | Private compose not identical to repo copy | `cmp` | VERIFIED | Re-checked | Which matches runtime (Q4) |
| A13 | 21 stashes, 57 stash-only commits, 19 of 21 first parents in a ref | `git stash`, `rev-list`, `for-each-ref` | VERIFIED | Re-checked | Stash content not inspected |
| A14 | 0249 committed "08:33 +1100" (§8.4) | `git log` | **CONTRADICTED** (timezone) | `git` records `+0000`: 08:33 UTC = 19:33 AEDT. The conclusion (after the 02:42 AEDT dump) still holds. | Corrected |
| A15 | 0249 has "eight SET SCHEMA statements; one to public" (§8.4.4) | Migration | **CONTRADICTED** | Seven executed moves. The public match is a comment on line 12. | Corrected |
| A16 | "No migration-application record in the repository" (§8.4) | Commit messages | **CONTRADICTED (in part)** | `98ba1cf6a` says "Already applied" (0249). `59bcdde43` records 0250 applied to the project on 11-06. Self-reported in git only. | Database history (Q5) |
| A17 | 11-06 TOC 1,893 lines, 1,878 entries | Offline `pg_restore --list` (counts only) | VERIFIED | Reproduced; Agent 4's schema split differs only by method | None |
| A18 | Seven moved tables absent from 11-06 TOC | Offline check (names withheld) | VERIFIED | Consistent with 0249 applied before the dump | Application date (A16) |
| A19 | Path count 96 → 38 explained (§8.5) | `git diff 543ab9312 dbbfbae1a`; journal | VERIFIED (mechanism) | No contradiction | 11-04 unit count of 62 INFERRED |
| A20 | Rollback copy identical to `543ab9312` | `cmp` | VERIFIED | Confirmed | Install record |
| A21 | `.env` mode 0644 exposed "to any local user" (F11, SEC-DR-02) | `stat` | **CONTRADICTED (in part)** | `/data/coolify` and `/data/coolify/source` are both `drwx------`, so non-owners cannot traverse. Exposure is to the owner and root. | Credential validity (owner) |
| A22 | "Parent mode not recorded" gap (SEC-DR-02) | `stat` | **CONTRADICTED** (now closed) | Parent is mode 700 | Corrected |
| A23 | `delivery_apply.log` is 5.8 MB (§4) | `ls` | **CONTRADICTED** | Live file 413 KB; 5.8 MB is `delivery_apply.log-20261108` | Corrected |
| A24 | Coolify decommissioned (`Caddyfile.v3`, §4A.3) | Caddy comments | DOCUMENTED | Quote is at line 28, not 25–28 | Owner records (memory note cited, not in repo) |
| A25 | Redis `--requirepass` value in container metadata; report contains no literal | Grep of report; `docker inspect` not repeated | VERIFIED | No literal in the report | Owner rotation |
| A26 | Infisical logical dump runs nightly | Journal (8 entries since 11-01) | VERIFIED | Confirmed | Restore test (DOCUMENTED) |
| A27 | Installed backup script and units identical to repo | `cmp` | VERIFIED (current) | Stale wording "revision 1" in §13 | None |
| A28 | Lock contention exits 75 (§13) | Script `:82` | VERIFIED | Confirmed | None |
| A29 | PR #609 merged 2026-11-07T23:47:52Z | `git merge` 9b7e35c9c (10:47:52 +1100) | VERIFIED (git) | Confirmed; the time in `gh` is UTC | GitHub checks not re-queried |
| A30 | PR #610 "20 checks SUCCESS" (E18) | Not re-queried | Reported | Not reproduced in this investigation | GitHub |

Remaining report claims that were checked and held are listed in the four specialist outputs, which the lead has reconciled into §§16.1–16.5.

### 16.7 Corrections and contradictions (lead-reconciled)

| # | Earlier claim (section) | Status | Correction |
|---|---|---|---|
| C1 | First weekly integrity run "pending" (E16, §8.2, §9 item 5, §12 step 13, §13, §14 item 9, Q11) | **CONTRADICTED** | Completed 11-08 11:30:20–11:30:48 AEDT: "no errors were found", 12/12 snapshots, 4/52 packs read (journal). Corrected in E16, §8.2 and §9 item 5. Other sections still describe a future verification step; treat the journal as the result. |
| C2 | "Six runs, 2026-11-03 to 2026-11-08" (§11) | **CONTRADICTED** | Finished OK on each night in the journal window. |
| C3 | Compose "name" at line 12 and external at 21, 52–54; quote "exists today…" in repo compose (E20, §3, §5) | **CONTRADICTED** | Repo copy: name at 16, external at 106. The quote is in the private copy at line 54 only. Corrected in E20 and §5. |
| C4 | "(root) LIST (root)" on six runs (§8.5.6) | **CONTRADICTED** | Five. Corrected. |
| C5 | Commit times "+1100" for 0249, 0252, 0254 (§8.4) | **CONTRADICTED** | Git records UTC (`+0000`). Corrected. Ordering relative to dumps unchanged. |
| C6 | Eight `SET SCHEMA` statements, one to public (§8.4.4) | **CONTRADICTED** | Seven executed; one comment. Corrected. |
| C7 | "No migration-application record" (§8.4.4, §8.4.6, §8.4.7) | **CONTRADICTED (in part)** | Commit messages record application ("Already applied" for 0249; 0250 applied 11-06). Self-reported; database history still needed. |
| C8 | Coolify `.env` exposed to any local user; parent mode not recorded (F11, SEC-DR-02) | **CONTRADICTED (in part)** | Both directories are mode 700. Exposure is to owner and root only. Credential validity still UNKNOWN. Priority for SEC-DR-02 is for the owner to re-rate. |
| C9 | `delivery_apply.log` 5.8 MB (§4) | **CONTRADICTED** | 413 KB. Corrected. |
| C10 | "Six occurrences" in the path-count section (§8.5) | **CONTRADICTED** | Corrected to five. |
| C11 | Agent 2 code comments: `/api/config` "local-only"; Slack "designated researchers"; Caddy "/api/* to backend" | **CONTRADICTED** | `/api/config` has no IP or host check; the comment is wrong. The Slack research comment "designated researchers" is disproved by "allowing all users". The Caddy header claim that `/api/*` goes to the backend is disproved by the `@api` matcher. |
| C12 | `hq-evolution` comment "restart once" (Agent 3) | **CONTRADICTED** | Config is `Restart=on-failure` with no `StartLimit`. Not in the report; recorded for completeness. |
| C13 | 0249 timing and "applied" (Agent 1 C1/C2) | **CONTRADICTED** | Confirmed and merged into C5 and C7. |
| C14 | Path-count "retention model" (§8.1) | **INFERRED, limited** | The model ignores weekly and monthly exceptions in detail. The conclusion (one snapshot aged out on 11-05) is INFERRED, not verified. |
| C15 | Integrity cited as "not yet verified" in later stance (§13, §14) | **CONTRADICTED** | Superseded by C1. |

**Duplicates and labelling.** The Redis exposure appears in §4A.7, SEC-DR-01, the register, and Q22; these are consistent and should be kept in sync. Coolify appears in §4A.3, §4A.4, §7.4, SEC-DR-02, F11, F12, Q18, Q19 and Q23; SEC-DR-02's "exposure to any local user" wording is superseded by C8. The 92-line TOC decrease appears in §5, §8.3, §8.4, §14 and Q5; §8.3 is superseded by §8.4.

### 16.8 Preserved findings (not reopened)

- **SEC-01 gates G3, G4, G5** closed with recorded validation (commit `8d44f1cdd`). Not reopened. The live Caddy file contains the SEC-01 "NOT DEPLOYED" marker text, which is a separate question (CB-15, FA-14).
- **SEC-DR-01** (Redis credential exposure). Preserved, not reopened. Owner rotation only.
- **SEC-DR-02** (Coolify `.env` permissions). Preserved, with the exposure assessment revised by C8. Validity UNKNOWN.
- **96 → 38 path count** (§8.5). Explained.
- **1,893-line TOC** for the 11-06 dump (§8.4). Reproduced offline.
- **Coolify decommissioned** (§4A.3). Not an active dependency.

### 16.9 Prioritized future action register

All actions are **OPEN — DOCUMENTED ONLY**. None has been executed. Each needs the owner's separate authorization. Verification methods are suggestions for a future authorized change, not instructions to run now.

| ID | Priority | Action | Dependencies | Suggested verification (future, authorized) | Owner authorization |
|---|---|---|---|---|---|
| FA-01 | HIGH | Remove the key from `/api/config`; bind command-centre to `127.0.0.1` (CB-01) | LCARS server key path; Vercel side; restart window | Local `curl` expecting 401 on `/api/config`; LCARS writes still succeed | Owner and Captain |
| FA-02 | HIGH | Stop accepting `api_key` in the query string; redact URIs in Caddy logs (CB-05) | Any client using query keys | Test with header only; log sample reviewed for key shape without printing values | Owner |
| FA-03 | MEDIUM–HIGH | Wrap `command-centre.service` and the other unwrapped units with `run-with-infisical.sh`; move the repo `.env` out of the service path (CB-03, CB-16) | Infisical health; boot ordering (2026-10-06 incident) | Unit `ExecStart` review; service health after restart | Owner |
| FA-04 | MEDIUM | Pass the Infisical client secret by env or stdin (CB-04) | Infisical CLI support | Login test on restored host | Owner |
| FA-05 | HIGH | Enable branch protection and required reviews on `main`; add an environment with approval for deploys; add a CI-status gate to `auto-deploy.sh` (CB-14) | GitHub admin rights; Vercel deploy-on-merge (INFERRED) | GitHub branch-protection settings read by owner; deploy dry run | Owner |
| FA-06 | MEDIUM–HIGH | Make backup component failures set exit status; keep `pg_dump` stderr on success; log missing critical paths as failures (§16.5) | Alert path (FA-07) | Dry-run mode (`DRY_RUN=1`) reviewed | Owner |
| FA-07 | MEDIUM | Make alert-send failures non-zero and observable; add `OnFailure` for the alert path's own dependencies; watch the watchdog (§16.5) | Telegram path | Authorized test alert, one only, with cooldown respected | Owner |
| FA-08 | MEDIUM | Decide whether the `mission-engineering-dispatch` stop was deliberate; re-enable only after review (§16.1 item 4) | Mission owner | Journal of last cycle, reviewed by owner | Owner |
| FA-09 | MEDIUM | Per-route least-privilege Supabase client instead of the service-role key (CB-02) | Route inventory | Code review per route | Owner |
| FA-10 | HIGH | Owner runs read-only checks: `pg_policies`, `pg_tables.rowsecurity`, and the PostgREST exposure setting (CB-08, CB-09) | Owner database access | Read-only queries only, run by owner | Owner |
| FA-11 | HIGH | Add Captain role checks to the mutating LCARS routes; confirm signup is disabled (CB-13) | Supabase auth settings | Route review; signup setting check by owner | Owner |
| FA-12 | MEDIUM | Add authorization to the Slack research command (CB-12) | Slack identity mapping | Code review | Owner |
| FA-13 | MEDIUM | Add a Telegram user-ID allowlist alongside the chat allowlist; confirm the chat is private (CB-11) | Chat membership | Owner confirms chat type | Owner |
| FA-14 | HIGH | Confirm which SEC-01 blocks are live in `/etc/caddy/Caddyfile` (CB-15) | Caddy reload window if change needed | Owner reads the live file (not by agent) | Owner |
| FA-15 | HIGH | Confirm migration `0249` application and date in the Supabase migration history; decide the archive backup policy (§8.4.7) | Owner database access | Migration history query by owner | Owner |
| FA-16 | LOW | Keep byte-identity checks (`cmp`) after each script or unit change | None | `cmp` against repo | Owner |
| FA-17 | MEDIUM | Pin `postgres`, `redis` and related images by digest; document rollback for Infisical, Postgres and Ollama (§16.5) | Registry access | Digest comparison | Owner |
| FA-18 | HIGH | Confirm custody of the restic password, OAuth client and Infisical keys (Q1); plan rotation after any exposure | Owner password manager | Owner confirms presence (no values) | Owner |
| FA-19 | HIGH | Redis rotation and removal of the value from the command line (SEC-DR-01) | Consumers listed in SEC-DR-01 | Health checks after rotation | Owner |
| FA-20 | MEDIUM | Decide retention or archival of Coolify residue and tighten `/data/coolify/source/.env` permissions (SEC-DR-02, Q18, Q23) | Owner decision | `stat` after change | Owner |
| FA-21 | MEDIUM | Per-run path manifest, script commit in each run's first log line, split counts (§8.5.7) | None | Log sample reviewed | Owner |
| FA-22 | MEDIUM | Address the auto-deploy stash and `set -e` fetch path so local `data/self-improvement` changes are restored (§16.5) | Stash stack (21 entries; do not touch without owner) | Dry run of the restore path | Owner |
| FA-23 | LOW | Remove the unused `caddy.service.d/apikey.conf` after confirming no consumer (CB-06) | Caddy unit | `systemctl cat` review | Owner |
| FA-24 | MEDIUM | Make the context service fail closed when its secret is unset; confirm deployed secrets (CB-07) | Env population | Config review | Owner |
| FA-25 | MEDIUM | Decide journal retention: disk at cap 1,022.9 MB, earliest backup entry 2026-10-13 (§16.6) | Storage | `journalctl --disk-usage` review | Owner |
| FA-26 | LOW | Owner reviews the alert-state residue for `some-other.service` (INFERRED test residue). Do not clear. | Alert system | Owner review of state keys only | Owner |
| FA-27 | MEDIUM | Make `hq-evolution` restarts bounded (`StartLimit`) (C12) | Unit | Config review | Owner |
| FA-28 | LOW | Decide whether `/root/.claude` memory and the two memory databases need backing up or a second copy (§16.2) | Owner decision | Owner confirms | Owner |
| FA-29 | HIGH | Decide Supabase Storage and Vault backup scope (§16.2) | Owner dashboard access | Owner inventory | Owner |

### 16.10 Unresolved questions (owner input or future authorized testing)

1. Restic password, OAuth client and Infisical keys: present and current in the password manager? (Q1)
2. Does the old repository `rclone:gdrive:starship-backups` still exist? (Q10)
3. Remote snapshot list, and which snapshot aged out on 11-05 and 11-06? (Q2, Q3)
4. Migration history: was `0249` applied, when, and does the `archive` schema hold the seven tables? Were `0252` and `0254` applied? (Q5, FA-15)
5. GitHub state of the 153 unpushed branches, the 108 tags (27 pointing to commits on no local branch, 107 `archive/*`), and the 21 stashes (Q6)
6. Branch protection and required reviews on `main` (CB-14, FA-05). GitHub API returned 403 to the read-only query.
7. Supabase: live `pg_policies`, `rowsecurity`, signup setting, PostgREST exposure (CB-08, CB-09, CB-13)
8. Supabase Storage objects and Vault contents, and how many (Q13)
9. Live Caddy SEC-01 containment: which blocks are active (CB-15)
10. Whether the Telegram chat is private or a group (CB-11)
11. Whether mission-engineering-dispatch was stopped deliberately (FA-08)
12. Whether the Redis value is still accepted, and its consumers (SEC-DR-01)
13. Whether Coolify key material is needed (Q18, Q19)
14. Which Infisical compose matches the running containers (Q4)
15. The counting method behind the runbook's 166-table figure; it does not reconcile with the 0249 explanation under the same method (INFERRED arithmetic; §8.4)
16. Who removed Coolify images between 11-03 and 11-08 (Q16)
17. Whether journald's 1 GB cap rolls off history before `MaxRetentionSec` (FA-25)
18. Whether the Slack research command has an entry gate elsewhere (CB-12; not found in this worktree)

### 16.11 Evidence references (selected)

- Backup and restic: `deploy/starship-backup.sh` lines 25–27, 32, 42–43, 56–57, 66–67, 71–73, 82, 103, 105–126, 130, 139, 144–146, 152–153, 206–226, 241–252; `deploy/starship-backup-integrity.{service,timer}`; `docs/operations/restic-backup-integrity.md`; `knowledge/missions/starship-backup-restore-runbook.md` lines 28–35, 46–47, 69, 82–83.
- Command Centre: `core/command-centre/backend/app.js` lines 19–20, 65, 80–94, 88, 106–108, 240; `deploy/command-centre.service` ExecStart.
- Caddy: `deploy/caddy/Caddyfile.v3` lines 25–28, 46–48, 172–174, `@api` matcher; `deploy/caddy/README-v3.md` (NOT DEPLOYED).
- Infisical: `platform-runtime/lib-infisical.sh` lines 3, 5–11, 60–62; `platform-runtime/run-with-infisical.sh:33`; `deploy/infisical/docker-compose.yml` lines 16, 58, 106 (repo); `/root/private-knowledge/infisical-compose/docker-compose.yml` lines 12, 54 (private copy, noted only by line).
- Deployment: `deploy/auto-deploy.sh` lines 74, 135–136, 226, 233, 241–246, 336–337, 382–383, 391; `deploy/auto-deploy.service:38`.
- Migrations: `core/infrastructure/supabase/migrations/0249_archive_revs_tables.sql` lines 12, 21–27; `0035` (anon_read); `0221`; `0231`.
- Git: commits `98ba1cf6a` (0249, "Already applied"), `59bcdde43` (0250 applied), `5567b1a36` (0250 not applied at time), `543ab9312` and `dbbfbae1a` (path list), `7a8dd3b84` (venv freeze), `8d44f1cdd` (SEC-01 closure), `846b2aa31` and `e218bd7c2` (Infisical compose history).
- Journal: `starship-backup.service` 11-01 to 11-08; `starship-backup-integrity.service` 11-08 11:30:20–11:30:48; `mission-engineering-dispatch.timer` (list-timers).
- Host firewall: `/etc/default/ufw` `DEFAULT_INPUT_POLICY="DROP"`; `ufw status`.
- Listeners (metadata): `ss -ltn` shows `*:5000`, `127.0.0.1:5001`, `127.0.0.1:5052`, `0.0.0.0:8893`.

### 16.12 Limits and steps not completed

- No live authentication or authorization test was made. Each authorization result is a code reading or a host-configuration reading.
- No database connection, no audit or alert row read, no migration-history query. Application status of migrations is self-reported in commit messages.
- No remote GitHub or restic inventory. The single read-only GitHub API call (agent 3) returned 403 and is recorded as UNKNOWN.
- No secret value, `.env` content, or raw `docker inspect` output was read.
- Agent 2 did not compare `/opt/deploy-guard/scoped-restart.sh` with the repo copy, did not enumerate python-ci secret names, and did not check ufw live (lead has now checked `ufw status`, §16.1 item 1).
- Agent 4 did not reproduce the per-schema TOC split exactly (its method gave 1543/251/79/5 against 1541/250/78/4/5); totals match.
- Scratch files were written to the session scratchpad only, not the repository.

### 16.13 Quality gates for this update

- Only `docs/operations/disaster-recovery-gap-assessment-2026-11-08.md` was changed in the worktree.
- No secret value, token, password or fingerprint is written in this section. Credential-related items name variables, files and line numbers only.
- All four workstreams are represented: §16.2 (Agent 1), §16.3 and §16.4 (Agent 2), §16.5 (Agent 3), §16.6 (Agent 4).
- Previously resolved issues were not reopened: SEC-01, the 96→38 path count (§8.5), the TOC reproduction (§8.4), Coolify decommissioning. Items that the evidence contradicted are corrected in §16.7, not silently changed.
- No remediation was executed. All future actions are marked OPEN — DOCUMENTED ONLY.
