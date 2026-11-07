# TJRHQ disaster recovery gap assessment (2026-11-08)

Status: read-only assessment. No production files, services, timers, credentials, backups, restores or remote repositories were touched.

Labels used throughout:

- **VERIFIED**: observed directly in this session (file read, command output, or `git` plumbing). Source is given.
- **INFERRED**: follows from verified facts, but was not observed directly.
- **UNKNOWN**: cannot be determined from the repository or the VM without owner input, remote access, or a restore.

Paths are relative to `/opt/starship-endeavour` (the live checkout, `main` at `9b7e35c9c`) unless absolute. The live checkout has one modified tracked file (`core/mission-control/registry/mission-index.txt`) and one untracked file under `data/self-improvement/review/`. Both were observed by `git status` at the time of the run. Nothing was changed.

## 1. Executive summary

**Verdict: TJRHQ could be rebuilt on a replacement VM, but only if the owner can produce three secrets from outside the VM, and only from a backup set that is narrower than the operational state.**

What works (VERIFIED from code and recorded evidence):

- A nightly, encrypted, off-box restic snapshot runs at 02:40 Australia/Melbourne. The six runs from 2026-11-03 to 2026-11-08 each logged `finished OK` (`journalctl -u starship-backup.service`). Retention is 7 daily / 4 weekly / 3 monthly (`deploy/starship-backup.sh:241`).
- The backup contains the Supabase database (custom-format `pg_dump`, refreshed every 72 hours and cached between runs), the Infisical Postgres database, the Infisical container definitions, `/etc/caddy`, `/etc/systemd/system`, `/root/private-knowledge` (including an Infisical recovery env file and a compose copy), `.env*` files under the repo, and a git bundle of local branches (`deploy/starship-backup.sh:130-219`).
- A recovery runbook exists and was exercised on 2026-10-09 for Infisical and Supabase (`knowledge/missions/starship-backup-restore-runbook.md:69,82-83`, as documented; not re-run here).
- PR #609 merged at 2026-11-07T23:47:52Z with all listed checks green. It installs a weekly `restic check --read-data-subset=1/20` timer, scheduled for Sunday 11:30 Australia/Melbourne (`deploy/starship-backup-integrity.timer`). Its first scheduled run had **not** happened at the time of this assessment. The timer shows `NEXT Sun 2026-11-08 11:30:00 AEDT` (`systemctl list-timers`). **No pass claim is made for it.**

What does not work as a complete recovery plan:

- The whole chain depends on secrets that live only in the owner's password manager (restic password, Google OAuth client for the Drive remote, Infisical `ENCRYPTION_KEY`/`AUTH_SECRET`). Whether those copies exist is **UNKNOWN**. Nothing in the repository proves it.
- Large parts of VM-only operational state are not in the restic path list: most of `outputs/`, `data/memory_graph.db`, `.cortex/memory.db` (about 31 MB), `/etc/self-improvement/`, the Coolify data directory, the Infisical uploads volume, and Caddy's ACME storage.
- Git coverage is partial. The bundle contains only `refs/heads/*`. It excludes 21 stashes, remote-tracking refs and tags, and any uncommitted change.
- Restore evidence is narrow: a 1% and a 1-in-20 pack sample integrity check, a three-file restore drill, and an Infisical and Supabase restore on 2026-10-09. No full restore of the complete snapshot has been recorded.

## 2. Scope and method

- Read: `deploy/starship-backup.sh`, `deploy/starship-backup.service`, `deploy/starship-backup.timer`, `deploy/starship-backup-integrity.{service,timer}`, `docs/operations/restic-backup-integrity.md`, `knowledge/missions/starship-backup-restore-runbook.md`, `reports/vm-audit/backup-verification-20261105.md`, `deploy/infisical/README.md`, `deploy/infisical/docker-compose.yml`, `.gitignore`, `deploy/caddy/Caddyfile.v3`.
- Ran read-only commands: `git` plumbing (`ls-files`, `status --ignored`, `for-each-ref`, `stash list`, `branch --contains`, `bundle` was **not** run), `systemctl list-timers` / `list-units`, `journalctl` (read only), `docker ps` / `inspect` / `volume ls` (names and labels only), `ls`/`find` for presence and permissions, `gh pr view 609`.
- Did **not**: run `restic` against any repository, read any secret value, run `rclone` against a remote, read the contents of `.env`, `.restic-pass`, `rclone.conf`, `infisical-recovery.env`, or `.infisical-auth.env`, change any service or timer, or touch the live checkout's stash stack.

Secret handling: env var **names** were listed for the Infisical container, and file **presence and mode** were checked for secret-bearing files. No values appear in this document.

## 3. Recovery coverage matrix

| Asset | Where it lives | In restic path list? | In committed git? | Recovery route | Label |
|---|---|---|---|---|---|
| Source code, tracked docs, `knowledge/` (111 files), `deploy/` (tracked units and scripts), `Missions/` (93 tracked) | GitHub `timjardenross/TJRHQ` | No (not needed) | Yes | `git clone` from GitHub | VERIFIED (`git ls-files` counts) |
| Local branches (202 heads) | VM | Yes, via bundle `deploy/starship-backup.sh:144,219` | Mostly, if pushed | `git clone branches.bundle` then `checkout main` (runbook §3) | VERIFIED |
| Remote-tracking refs (150) and tags (108) | VM + GitHub | No (`--branches` only, line 144) | Yes on GitHub | Re-fetch from GitHub | VERIFIED (`for-each-ref`) |
| **Git stashes (21)** | VM only, shared stack | **No** | **No** | None documented | VERIFIED. Checked first 10 with `git branch -a --contains`: none reachable from a branch. The bundle excludes `refs/stash` by definition. |
| Uncommitted tracked change `core/mission-control/registry/mission-index.txt` | VM only | **No** | No | None | VERIFIED (`git status`) |
| Untracked, non-ignored `data/self-improvement/review/mission_dispatch_log.jsonl.bak-*` | VM | Yes (`data/self-improvement/review`, line 207) | No | Restic | VERIFIED |
| `outputs/` (gitignored, 20 entries; `.gitignore:51`) | VM | Only `outputs/delivery_ledger.txt` (line 208) | No | Restic for ledger only | VERIFIED. 19 of 20 entries not in any backup path. |
| `data/memory_graph.db` (939 KB), `data/alert_state/`, `data/resilience-crosswalk/audit.jsonl` | VM, gitignored | **No** | No | None | VERIFIED |
| `.cortex/memory.db` (30.9 MB, SQLite) | VM, gitignored | **No** | No | None | VERIFIED |
| `/etc/self-improvement/dashboard.env` | VM | **No** (`/etc/self-improvement` not in list, lines 206-219) | No | None | VERIFIED (presence). Contents not read. |
| `/root/private-knowledge/` (Infisical recovery env, compose copy, DB env, knowledge records) | VM | Yes (line 217) | No | Restic | VERIFIED (presence, names only). Contents of the recovery env not read. |
| `/root/.restic-pass` (mode 0600, root) | VM | **No, by design** (runbook §"Not in the backup") | No | Password manager (owner) | VERIFIED (exists). Off-VM copy **UNKNOWN**. |
| `/root/.config/rclone/rclone.conf` (mode 0600, holds gdrive2 token) | VM | **No, by design** (runbook) | No | Re-authorise with OAuth client (runbook §1) | VERIFIED (exists). |
| Supabase Postgres (`public`, `auth`, `storage` metadata, `supabase_migrations`) | Supabase cloud | Yes, cached dump every 72h (lines 66-67, 96-123) | Schema via migrations | Restore dump (runbook §5) | VERIFIED (script). Last verified age: cache 47 h at 2026-11-05 (verification report, deviation 3). Current age **UNKNOWN**. |
| Supabase `vault` schema, Storage object binaries, project settings, auth providers, API keys | Supabase cloud | **No** (`vault` excluded per runbook line 28; binaries are outside `pg_dump`) | No | Re-enter from Infisical / owner / Supabase dashboard | INFERRED (binaries) / VERIFIED (vault exclusion, runbook) |
| `cron.job` rows | Supabase DB | Yes (line 72, cached as `.cron-job.sql`) | n/a | Re-create (runbook §5.4) | VERIFIED |
| Infisical Postgres | Docker volume `infisical_infisical-db` | Yes, `pg_dump` (line 130) | No | `pg_restore` (runbook §4) | VERIFIED |
| Infisical uploads | Docker volume `infisical_infisical-uploads` | **No** | No | None documented | VERIFIED (volume exists, not in any path). Contents **UNKNOWN**. |
| Infisical Redis | Docker volume `infisical_infisical-redis` | **No** | No | Treated as cache | INFERRED (not documented either way) |
| Infisical container definitions | Docker | Yes, `docker inspect` (line 139) | Compose in `deploy/infisical/docker-compose.yml` | Compose + env (runbook §4) | VERIFIED |
| Infisical compose env (`ENCRYPTION_KEY`, `AUTH_SECRET`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`) | `/root/private-knowledge/infisical-compose/.env`, `infisical-recovery.env` | Yes (line 217) | No | Restic and password manager | VERIFIED (presence). Equality with live container **UNKNOWN**. |
| Compose project path label | Container label `com.docker.compose.project.config_files=/root/TJRHQ/deploy/infisical/docker-compose.yml` | n/a | n/a | Stale: `/root/TJRHQ/deploy/infisical` does not exist | VERIFIED |
| Machine-identity auth for services | `platform-runtime/.infisical-auth.env` | Yes (line 211) | No | Restic | VERIFIED (path). Not read. |
| Service `.env` files | Repo tree (`platform-runtime/.env`, `.env.bak-pre-secretkey-20261010`, `telegram-bots/*/.env`, `lcars-portal/.env.local` if present) | Yes, `find` on `REPO_ROOT` (lines 222-223) | No | Restic | VERIFIED (find clause). Individual presence partly UNKNOWN. |
| Caddy config | `/etc/caddy` | Yes (line 212) | Repo copy `deploy/caddy/Caddyfile.v3` identical to live (`cmp`) | Restic or git | VERIFIED |
| Caddy ACME certificates and account | `/var/lib/caddy`, `/root/.local/share/caddy`, `/root/.config/caddy` | **No** | No | Re-issue from Let's Encrypt on boot | VERIFIED (dirs exist). INFERRED: rate-limit risk if reissuing many times. |
| systemd units and drop-ins | `/etc/systemd/system` | Yes, whole directory (line 213) | Repo `deploy/*.service` | Restic or git | VERIFIED |
| Root crontab | `/var/spool/cron/crontabs` | Yes (line 218), plus `crontab-root.txt` (line 153) | No | Restic | VERIFIED |
| `/opt/deploy-guard`, `/etc/sysstat`, `journald.conf.d` | Host | Yes (lines 214-216) | Partly (`deploy/`) | Restic | VERIFIED |
| Docker images | Registry | No | n/a | Re-pull | VERIFIED (runbook line 29) |
| Coolify (`/data/coolify`, volumes `coolify-db`, `coolify-redis`) | VM | **No** | No | None documented | VERIFIED (presence). Role **UNKNOWN** from repo. |
| Ollama models | `/root/.ollama` or similar | No, by design (runbook line 29) | No | Re-pull | VERIFIED (runbook) |
| Google Drive (restic repo `starship-backups-v2`) | Google Drive, `drive.file` scope | n/a | n/a | Single provider, single account | VERIFIED (script line 42) |
| GitHub (sole remote for PRs, issues, Actions) | GitHub | n/a | n/a | Re-clone | VERIFIED (PR #609 via `gh`). Actions secrets and branch protection **UNKNOWN**. |
| Vercel (LCARS portal) | Vercel project link `lcars-portal/.vercel/project.json` | **No** (`.vercel` not in path list) | Ignored by git | Re-link (`vercel link`) and re-enter env | VERIFIED (presence). Vercel env values **UNKNOWN**. |
| Telegram bots (`tg-xo`, `tg-capacitybot`, `tg-resiliencebot`) | systemd, `run-with-infisical*.sh` | Units yes; tokens via Infisical | Units in repo | After Infisical is up | VERIFIED (18 wrapper references in units) |
| Self-improvement services | systemd, `data/self-improvement` | Review state yes; `/etc/self-improvement` no | Scripts in repo | Restic plus repo | VERIFIED |
| Backup scheduler and integrity check | systemd `starship-backup*.timer` | Units in `/etc/systemd/system` (line 213) | `deploy/` | Restore units, `daemon-reload` | VERIFIED |

## 4. Top five recovery gaps, ranked by impact

### Gap 1. Three off-VM secrets are a single point of failure, and their custody is unverified

- **What:** The restic repository password, the Google OAuth client ID and secret used by rclone (`gdrive2`), and the Infisical `ENCRYPTION_KEY` and `AUTH_SECRET` are needed before anything else can be restored. The restic password is deliberately excluded from the backup (`deploy/starship-backup.sh:43`, runbook lines 29, 31-35). The Infisical `ENCRYPTION_KEY` and `AUTH_SECRET` sit inside the encrypted backup (`/root/private-knowledge/infisical-recovery.env`), so they cannot be read until the restic password is available. The OAuth client is needed to reach the Drive repository at all, because `drive.file` scope only shows files created by the same client (runbook line 45).
- **Evidence:** VERIFIED: `/root/.restic-pass` mode 0600 exists; `/root/.config/rclone/rclone.conf` mode 0600 exists; runbook lines 31-35 and 39-47 name the password manager as the sole custodian. UNKNOWN: whether the password manager holds all three items, whether they are current, and whether a second person or device can reach them.
- **Impact:** Total loss of the VM plus loss of any one of these items means loss of every backup. The key-decryption chain is also circular: the Infisical key is inside the backup, and the backup needs the restic password.
- **Why ranked first:** Every other recovery step is blocked by this one, and it cannot be detected from the repository.

### Gap 2. VM-only operational state is outside the backup path list

- **What is excluded, all VERIFIED against `deploy/starship-backup.sh:206-223`:**
  - 19 of 20 `outputs/` entries, including `deadmans_switch_state.json`, `operating_patterns.json`, `mission_intelligence.json`, `knowledge_utilisation.json`, and the delivery apply logs (`.gitignore:51` marks the whole directory as ignored).
  - `data/memory_graph.db` (939 KB), `data/alert_state/`, `data/resilience-crosswalk/audit.jsonl`.
  - `.cortex/memory.db` (30.9 MB SQLite, ignored by git). Whether it is reproducible from source is **UNKNOWN**.
  - `/etc/self-improvement/dashboard.env`.
  - Coolify data (`/data/coolify`) and volumes `coolify-db`, `coolify-redis`.
  - Infisical uploads volume (`infisical_infisical-uploads`).
  - Caddy ACME storage.
  - The uncommitted tracked change in `core/mission-control/registry/mission-index.txt`, which is also not in git.
- **Why it matters:** Several of these are described in the repo as "runtime evidence" or as state that "regenerates." That is true for some items, but **not verified** for each. The `delivery_ledger` is in the backup, and the rest of `outputs/` is not, so a recovered system can silently lose delivery and alert state.
- **Also:** The backup comment on lines 155-165 records a deliberate choice to exclude the Python venvs. That choice is sound. The exclusions above are not documented as deliberate.

### Gap 3. Infisical recovery depends on a stale compose path, an untested replacement sequence, and volumes not in the backup

- **What:** The running `infisical` project was created from `/root/TJRHQ/deploy/infisical/docker-compose.yml` (container labels, VERIFIED). That directory does not exist (VERIFIED). A `docker compose` run from the recorded path will fail, and the `project` label will not match a fresh checkout unless the project name is set explicitly. The compose file warns about this (`deploy/infisical/docker-compose.yml:14-15`: a differently named project "would create NEW, empty volumes"). The runbook restores from `/root/private-knowledge/infisical-compose` (runbook §4.1). That path works in principle, but it has not been exercised as a whole on a fresh host in this assessment.
- **Why it matters:** Infisical is the dependency of every service wrapper (18 references to `run-with-infisical.sh` in unit files, VERIFIED). Until it is back, Telegram bots, the LCARS portal, the self-improvement services, and the Supabase dump job cannot start. The Infisical uploads volume is not backed up at all (Gap 2).
- **Tested vs. claimed:** The runbook states that 100 secrets decrypted to values identical to live on 2026-10-09 (runbook line 69). That claim is **documented, not re-verified**.

### Gap 4. Git coverage is narrower than "all committed work"

- **What:** `git bundle create --branches` (line 144) captures `refs/heads/*` only. It excludes:
  - 21 stashes (`refs/stash`). Some are labelled work-in-progress (for example `wsp before endeavour-27 checkout`, `wip-mobilecommandbar-verify-b3-run2`). Their contents are not in any branch (VERIFIED for the first 10 of 21). Stashes are not in the bundle and not in restic beyond what the live tree contains.
  - Tags (108) and remote-tracking refs (150). Tags are recoverable from GitHub if pushed. Remote-tracking-only refs are recoverable only if the branch still exists on GitHub.
  - Any uncommitted or untracked-but-not-ignored change outside the restic path list.
  - The bundle has no `HEAD` (runbook §3 says so). `checkout main` is a manual step that has to be done.
- **Why it matters:** Stashes and local-only commits on branches that were never pushed would be lost. The git worktrees under `/opt/wt-*` and `/root/*-wt` hold branches that may exist only on this VM. Their unpushed state is **UNKNOWN** from this assessment.
- **Also:** GitHub is the only remote copy of the PR and issue history. Its recovery posture (Actions secrets, branch protection, webhooks, collaborators) is **UNKNOWN**. Those settings are not in the repo.

### Gap 5. Restore evidence is sampled, not end-to-end, and the first scheduled integrity run has not happened

- **What the evidence shows (VERIFIED or documented):**
  - Nightly runs: `finished OK` on each night from 2026-11-03 to 2026-11-08 (journal).
  - Verification on 2026-11-05 (`reports/vm-audit/backup-verification-20261105.md`): one snapshot present, four new paths present, `restic check --read-data-subset=1%` clean (one pack of the repository).
  - Weekly integrity check: `restic check --read-data-subset=1/20` run manually on 2026-11-08 with exit 0, and a three-file restore drill (`docs/operations/restic-backup-integrity.md:27-38`, recorded in that document; not re-run here).
  - Infisical and Supabase restore tests on 2026-10-09 (runbook lines 69, 82-83), documented only.
- **What is missing:**
  - No full-snapshot restore to a clean directory has been recorded, and no full-data integrity check (`--read-data`) has been run.
  - Snapshot count anomaly: the 2026-11-05 report expected 11 snapshots and found 10. Retention pruned one, but which one is **UNKNOWN** (`reports/vm-audit/backup-verification-20261105.md`, deviation 1).
  - The Supabase dump runs every 72 hours and the cached dump was 47 hours old on 2026-11-05 (verification report, deviation 3). Worst-case data loss is up to about three days of Supabase changes, plus any log rows in the four excluded tables (`deploy/starship-backup.sh:51`, runbook line 18).
  - The weekly integrity unit does not alert on success (`docs/operations/restic-backup-integrity.md:48`). Results are only in the journal.
  - **SEC-01:** Commit `8d44f1cdd` records administrative closure of G3, G4 and G5. This assessment has not checked the closure itself. PR #609 is merged and its CI checks are green, which is evidence of the merge, not of the scheduled run.
  - **First scheduled integrity run:** due Sunday 2026-11-08 at 11:30 Australia/Melbourne. **Not verified at the time of writing.** Do not treat PR #609 as having passed its first run until the journal shows it.

## 5. Recovery dependency map (summary)

| Dependency | Needed for | Single point of failure? | Notes |
|---|---|---|---|
| Password manager | Restic password, OAuth client, Infisical keys | Yes | Gap 1 |
| Google Drive (`gdrive2`, `drive.file`) | All restic snapshots | Yes (one provider, one account) | Owner decision on second destination |
| GitHub | Source, PRs, Actions, branch protection | Yes | Bundle covers local branches only |
| Infisical | Every service wrapper, Telegram bots, Supabase dump job | Yes, after restore | Gap 3 |
| Supabase | Production DB, auth, storage metadata, cron | Yes | Dump up to 72 h old; vault and storage binaries outside dump |
| Vercel | LCARS portal hosting and env | Partly | Env values not in backup (UNKNOWN) |
| Caddy | Public routing, TLS | No | Config backed up; ACME re-issue |
| systemd, Docker | Process supervision, Infisical containers | No | Units and Docker definitions backed up; images re-pulled |

## 6. Replacement-VM recovery sequence

Preconditions (owner, outside the VM): restic password, Google OAuth client ID and secret, Infisical `ENCRYPTION_KEY` and `AUTH_SECRET`, optionally the Infisical `POSTGRES_PASSWORD` and `REDIS_PASSWORD` if the recovery env file is unavailable.

1. Provision Linux with Docker, `restic` 0.16+, and `rclone` 1.75+ (the Ubuntu apt rclone 1.60 cannot authorise Drive; runbook line 35).
2. Create the rclone remote `gdrive2` with the OAuth client and `drive.file` scope (runbook §1). Confirm with `restic ... snapshots`.
3. Restore the latest `starship-nightly` snapshot to a mode-700 directory (runbook §2). Treat the output as secret-bearing.
4. Clone the git bundle from the restored tree and check out `main` (runbook §3). Then `git remote add origin` and fetch from GitHub to recover remote-tracking refs and tags. Stashes are **not** recovered by this step (Gap 4).
5. Restore `/etc/systemd/system`, `/etc/caddy`, `/root/private-knowledge`, and the `.env` files to their original paths. Restore `/root/.restic-pass` and `rclone.conf` from the password manager, not from the snapshot.
6. Start Infisical from the saved compose copy (`/root/private-knowledge/infisical-compose`), with the project name set explicitly. Start `db` and `redis` first, restore `infisical-db.dump` with `pg_restore`, then start the app (runbook §4). Restore the uploads volume if it was captured elsewhere (Gap 2).
7. Put `.infisical-auth.env` back under `platform-runtime/`, then confirm a CLI login and the expected secret count for `prod`.
8. Supabase: create or reuse a project, enable extensions, create custom roles by name, restore `supabase.dump` with `pg_restore --no-owner --no-privileges`, re-create cron jobs from `supabase.dump.cron-job.sql`, and re-enter vault secrets from Infisical (runbook §5).
9. Run `systemctl daemon-reload` and start services in dependency order: Infisical, then Caddy, then `model-router` and `command-centre`, then `lcars-portal` and the Telegram bots, then the self-improvement and timer units. Verify each against its unit's health check.
10. Re-link Vercel (`vercel link`) and re-enter any missing Vercel env values from the Vercel dashboard.
11. Re-enable `starship-backup.timer` and `starship-backup-integrity.timer`. Confirm a fresh nightly and a weekly integrity run complete before calling the rebuild done.

Expected loss without any further work: stashes, unpushed local-only commits on any worktree, `outputs/` other than the delivery ledger, `data/memory_graph.db`, `.cortex/memory.db` (unless reproducible), Coolify state, Caddy certificates (re-issued), Supabase changes since the last dump (up to 72 h), Supabase storage binaries, and Vercel env values not in any snapshot.

## 7. Existing protections and evidence

| Protection | Evidence | Label |
|---|---|---|
| Nightly encrypted restic snapshot off-box | Journal `finished OK` on 2026-11-03 through 2026-11-08 | VERIFIED |
| Infisical DB dump and container definitions | `deploy/starship-backup.sh:130,139` | VERIFIED (code) |
| Supabase custom-format dump with cache and 72 h cadence | `deploy/starship-backup.sh:96-123` | VERIFIED (code) |
| Dump-validity guard (size ≥ 1 MB and ≥ 100 TOC entries) | `deploy/starship-backup.sh:109` | VERIFIED (code) |
| Git bundle with `bundle verify` | `deploy/starship-backup.sh:144-145` | VERIFIED (code) |
| Failure alerting via `OnFailure=alert-on-failure@` | `deploy/starship-backup.service` | VERIFIED (unit) |
| Lock contention now fails loudly (exit 75) | `deploy/starship-backup.sh:82`, `docs/operations/restic-backup-integrity.md:21-24` | VERIFIED (code) |
| Weekly sampled integrity check | `deploy/starship-backup-integrity.{service,timer}`; first run **pending** | VERIFIED (unit); run UNKNOWN |
| Manual sampled check and three-file drill, 2026-11-08 | `docs/operations/restic-backup-integrity.md:27-38` | Documented, not re-run |
| Verification report, 2026-11-05, PASS (1% sample) | `reports/vm-audit/backup-verification-20261105.md` | Documented, not re-run |
| Infisical restore test, 2026-10-09 (100 secrets identical) | `knowledge/missions/starship-backup-restore-runbook.md:69` | Documented, not re-run |
| Supabase restore test, 2026-10-09 (166 tables, 163 identical counts) | Same, lines 82-83 | Documented, not re-run |
| Caddyfile in repo identical to live | `cmp deploy/caddy/Caddyfile.v3 /etc/caddy/Caddyfile` | VERIFIED |
| Installed backup script identical to repo script | `cmp /opt/starship-backup/backup.sh deploy/starship-backup.sh` | VERIFIED |
| Repo has `.gitignore` for secrets and venvs | `.gitignore:7-24` | VERIFIED |

## 8. Unverified assumptions and limitations

- **Snapshot contents are not inspected.** This assessment did not list or read any snapshot. The statements about what a snapshot contains come from the script's path list (`deploy/starship-backup.sh:206-223`) and from the 2026-11-05 verification report.
- **The password manager is UNKNOWN.** The repository names it as the custodian, but does not show the items are present, current or readable by anyone other than the owner.
- **Secrets were not read.** Whether `infisical-recovery.env` matches the live `ENCRYPTION_KEY` was not checked. The runbook's 2026-10-09 test is the only evidence, and it is documented only.
- **Docker volumes are not inspected.** Contents of `infisical-uploads`, `coolify-db`, and `coolify-redis` are UNKNOWN.
- **`/data/coolify` role is UNKNOWN** from this repository. Its relationship to Infisical's `coolify` Docker network (`traefik.docker.network=coolify`, container label) is INFERRED.
- **Google Drive quotas, retention and account security are UNKNOWN.** The repository cannot prove the Drive account has 2FA, recovery options, or enough storage.
- **GitHub settings are UNKNOWN** outside the repository (branch protection, Actions secrets, webhooks).
- **Unpushed branches on worktrees are UNKNOWN** without a per-worktree `git log origin/...` comparison. Several worktrees exist under `/opt/wt-*` and `/root/*-wt`.
- **Restore timing is UNKNOWN.** The replacement sequence above has no measured duration.
- **Retention cause UNKNOWN:** which snapshot was pruned on 2026-11-05 is not recorded.
- **Rebuild on a fresh host has not been exercised as a whole.** Only the Infisical and Supabase halves were tested, and only on 2026-10-09.
- **Restic password rotation and OAuth client rotation history are UNKNOWN.** Changing either without updating the password manager would break restore.

## 9. Recommended next actions

### Owner decisions

1. **Confirm the password-manager custody** of the restic password, the Google OAuth client ID and secret, Infisical `ENCRYPTION_KEY` and `AUTH_SECRET`, and Infisical `POSTGRES_PASSWORD`/`REDIS_PASSWORD`. Record only where they live, never their values. Decide whether a second person or a break-glass path needs access.
2. **Decide on a second backup destination** (different provider or account) or accept Google Drive as a single point of failure.
3. **Decide on stash and worktree policy:** whether the 21 stashes should be triaged (kept, applied, or dropped) and whether unpushed worktree branches should be pushed to GitHub before any further rebuild work. This is an owner decision because it affects shared state.
4. **Decide on RPO for Supabase.** The current 72-hour dump cadence is a deliberate egress saving. Confirm it is acceptable, or fund a more frequent dump.
5. **Decide whether `outputs/` and `.cortex/memory.db` need backing up.** Either add them to the path list, or document each as reproducible with the command that regenerates it.
6. **Confirm SEC-01 closure** against the actual risk-acceptance record, and confirm the owner is content that the first integrity run is the gate for "PR #609 verified."

### Technical work (for a later, separately authorised change)

1. **Add the missing paths to the backup:** `/etc/self-improvement`, `data/memory_graph.db`, `data/alert_state`, `data/resilience-crosswalk`, `.cortex/memory.db`, the non-ignored remainder of `outputs/`, and `core/mission-control/registry/mission-index.txt` (or commit it). Decide Caddy ACME storage (`/var/lib/caddy`) and Coolify data after owner input on Gap 2.
2. **Extend the git bundle** to include `refs/stash` (as a named bundle or as `git stash show -p` patches), tags, and a `HEAD` reference. Document the stash-recovery step in the runbook.
3. **Fix the stale compose path** `/root/TJRHQ/deploy/infisical` in the running Infisical project: either recreate the project from `/root/private-knowledge/infisical-compose` with an explicit `-p infisical`, or update the label through the next recreate. Do not do this without a planned window, because it touches the key-store container.
4. **Back up the Infisical uploads volume** (`infisical_infisical-uploads`) or confirm it is empty.
5. **Run one full restore** of the latest snapshot to a scratch directory and diff against the live tree, not just three files. Run `restic check --read-data` at least once on the full repository.
6. **Add success alerting or a success-marker file** for the weekly integrity unit, since it currently logs to the journal only (`docs/operations/restic-backup-integrity.md:48`).
7. **Investigate the 10-vs-11 snapshot count** (verification report, deviation 1) and record the pruning decision in the journal.
8. **Write a single recovery-drill runbook** that covers all eleven steps in §6 and times them, then run it against a throwaway VM, not production.
9. **Verify the first scheduled integrity run** (Sunday 2026-11-08, 11:30 AEDT) from the journal, and record the outcome in `docs/operations/restic-backup-integrity.md`.

## 10. Notes for the reviewer

- This document is a single new file. It changes no code, configuration, timer, service, credential, or backup.
- Every "VERIFIED" claim maps to a path and line or to a read-only command. Where a claim relies on a document, it is labelled as documented.
- No secret values, tokens, connection strings, or key material were read or are recorded here. Presence and file modes are given only for the three secret-bearing files named in Gap 1.
