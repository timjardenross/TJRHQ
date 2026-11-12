# TJRHQ Command Centre — Architecture & Code Review Baseline v1.0

| Field | Value |
|---|---|
| Status | **APPROVED FOR PLANNING — NOT APPROVED FOR EXECUTION** |
| Baseline date | 2026-11-08 |
| Evidence source | PR #610, [timjardenross/TJRHQ#610](https://github.com/timjardenross/TJRHQ/pull/610) (open, unmerged, discovery only) |
| Evidence commit | [`e61abcffc5b01cf9875697e27acd3e907d7a21d8`](https://github.com/timjardenross/TJRHQ/commit/e61abcffc5b01cf9875697e27acd3e907d7a21d8) (PR #610 head when this baseline was prepared) |
| Evidence document (permalink) | [`docs/operations/disaster-recovery-gap-assessment-2026-11-08.md` at the evidence commit](https://github.com/timjardenross/TJRHQ/blob/e61abcffc5b01cf9875697e27acd3e907d7a21d8/docs/operations/disaster-recovery-gap-assessment-2026-11-08.md) |
| Production commit | [`9b7e35c9c7469215e98641685951a5dc34eec81b`](https://github.com/timjardenross/TJRHQ/commit/9b7e35c9c7469215e98641685951a5dc34eec81b) (`origin/main`; equal to the live VM checkout HEAD at verification time) |
| Review scope | Security, authorization, deployment, operations, backup, recovery and auditability |
| Confidence | Evidence-backed assessment. Unresolved live-state questions are kept visible (§6). |

> **This document approves the review as a planning baseline only.** It does not authorize production changes, credential rotation, database modification, deployment, service restarts, backup or restore operations, PR merges, or implementation of any future action (§7).

---

## 1. Executive assessment

TJRHQ has a viable technical foundation. Nightly encrypted backups run, the owner-approved gates in the SEC-01 programme were closed with recorded validation, and the review found working controls alongside the gaps below. The architecture does not require a wholesale rewrite. The gaps are concentrated in four areas:

1. **API security and credential handling.** A key-disclosure endpoint, a key accepted in query strings, a secret passed on process command lines, and service-role database access without row-level enforcement.
2. **Production deployment governance.** Commits reaching `main` are deployed to the VM by a timer with no CI-status gate in the repository. Owner approval rests on push rights, and branch protection could not be verified.
3. **Failure handling and detection.** Some backup failures exit successfully. A critical dispatch job has been stopped and silent since 2026-10-28. Alert-delivery failures are not themselves reported.
4. **Disaster recovery and auditability.** Off-VM recovery depends on three owner-held secrets. Some persistent state is outside the backup path list. Part of the Supabase data moved to an `archive` schema is no longer in the nightly dump. Replacement-VM restoration has not been demonstrated end to end.

**Verified versus exposed.** Most findings below are **verified code-level or configuration defects**. Their **live exploitability has not been tested**, and this review did not send any live request. Where the host firewall, the live Caddy configuration, or live Supabase policy state would change the exposure, the finding says so and marks the question UNKNOWN.

---

## 2. Architecture review findings

**Severity scale.** HIGH: a material control gap with a plausible loss or compromise path in the stated threat model. MEDIUM: a real gap with bounded impact or existing mitigation. LOW: hardening. Severity is the reviewer's assessment, not the result of a test.

**Classification.** VERIFIED: directly observed in the evidence. INFERRED: a plausible reading, assumption stated. UNKNOWN: not established. CONTRADICTED: an earlier statement disproved and corrected (the correction is in PR #610, §16.7).

**Source references.** "PR #610 §" points to the evidence document at the evidence commit (permalink in the metadata table). Code and configuration references are permalinks to the production commit `9b7e35c9c`.

---

### ARCH-01 — Unauthenticated `/api/config` discloses the backend API key

- **Severity:** HIGH (local threat model). Not reachable from the internet through the host firewall (see mitigation).
- **Operational impact:** Any local process or local user that can reach `127.0.0.1:5000` can read the key. The key authorizes every `/api/v1` write, including capture, mission status, governance and notification actions.
- **Classification:** VERIFIED (code and host firewall configuration). The live response was not requested. Live exploitability: UNKNOWN until tested by the owner.
- **Evidence:** PR #610 §16.1 item 1; §16.4 CB-01.
- **Code location:** [`app.js:81`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/core/command-centre/backend/app.js#L81) exempts `/api/config` from authentication. [`app.js:106`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/core/command-centre/backend/app.js#L106) is the handler that returns the key. [`app.js:240`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/core/command-centre/backend/app.js#L240) calls `app.listen(PORT)` without a host, so the server listens on all interfaces.
- **Mitigating factors:** Host `ufw` default incoming policy is DROP and port 5000 has no allow rule (`ufw status`, `/etc/default/ufw`). Caddy proxies only `/api/v1/*` and `/health` ([`deploy/caddy/Caddyfile.v3:50`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/caddy/Caddyfile.v3#L50), the `@api` matcher). Docker-published ports are not involved, since 5000 is a host process.
- **Outstanding verification:** Whether any other ingress path reaches port 5000 (none found in the reviewed configuration). Whether the key has ever been logged or exposed elsewhere (UNKNOWN).
- **Future action:** FA-01 (see §3).

### ARCH-02 — Commits on `main` deploy to the production VM without an independent gate

- **Severity:** HIGH (change control).
- **Operational impact:** A commit that reaches `origin/main`, including one pushed by a compromised account, is pulled and its units restarted within about five minutes. The repository does not contain a CI-status or approval check on this path.
- **Classification:** VERIFIED (mechanism, from the script and unit file). Branch protection and required reviews on `main`: **UNKNOWN**. The GitHub API returned 403 to the read-only query used in the review.
- **Evidence:** PR #610 §16.1 item 2; §16.3 (auto-deploy row); §16.5 (auto-deploy row).
- **Code location:** [`deploy/auto-deploy.sh:233`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/auto-deploy.sh#L233) (`git fetch origin "$BRANCH"`) and the surrounding fast-forward and restart logic. [`deploy/auto-deploy.service`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/auto-deploy.service) runs as `User=deploy`.
- **Mitigating factors:** A sync-deploy guard protects only the restart allowlist and repair scripts (PR #610 §16.3). It is not an approval gate. Owner push rights are a real control if branch protection is enabled.
- **Outstanding verification:** Branch protection, required reviews and environment protection on `main` (owner, read in GitHub settings). Whether any repository ruleset exists (UNKNOWN).
- **Future action:** FA-05.

### ARCH-03 — Backup component failures can exit successfully

- **Severity:** HIGH for recovery assurance. A backup journal can report `finished OK` after a partial capture.
- **Operational impact:** A failed component, such as a cache copy, a path check or the `find` that builds the list, does not fail the run. The journal then reports success, so the failure is not detected.
- **Classification:** VERIFIED (script read at the production commit). Whether a silent partial backup has occurred: UNKNOWN (not established from the journal alone).
- **Evidence:** PR #610 §16.1 item 3; §16.5 (backup row). The script's own header claim that any failure exits non-zero is **CONTRADICTED** by these lines (PR #610 §16.7; header at [`deploy/starship-backup.sh:25–27`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/starship-backup.sh#L25)).
- **Code location:** [`deploy/starship-backup.sh:121`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/starship-backup.sh#L121) (`cp` of the cached dump, unchecked). [`:126`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/starship-backup.sh#L126) (log-only branch). [`:220`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/starship-backup.sh#L220) (missing critical paths are logged as a note, not a failure). [`:222`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/starship-backup.sh#L222) (`find`, exit unchecked). `|| true` at [`:73`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/starship-backup.sh#L73), [`:152`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/starship-backup.sh#L152) and [`:153`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/starship-backup.sh#L153).
- **Mitigating factors:** The script's `fail()` accumulator and final non-zero exit cover the components that do call it. `pipefail` is set (line 32). The lock-contention path fails loudly (exit 75).
- **Outstanding verification:** Whether any past run hit a silent path (UNKNOWN). Whether `pg_dump` stderr contained warnings on the 2026-11-03 and 2026-11-06 dumps (UNKNOWN; stderr is discarded on success).
- **Future action:** FA-06.

### ARCH-04 — Mission dispatch stopped and silent; per-mission failures exit 0

- **Severity:** MEDIUM–HIGH (operational reliability). The stop reason is unknown.
- **Operational impact:** The mission-engineering dispatch timer is enabled but has not run since 2026-10-28 20:43 AEDT. Its unit description still says "every 15 minutes". No alert path is configured for it.
- **Classification:** VERIFIED (timer state from `systemctl list-timers`; exit path from source). Intent of the stop: UNKNOWN; no record was found.
- **Evidence:** PR #610 §16.1 item 4; §16.5 (dispatch row); §16.7 C12 for the comparable restart issue in `hq-evolution`.
- **Code location:** [`core/engineering/mission_dispatch.py:329`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/core/engineering/mission_dispatch.py#L329) returns 0 on the normal path, including when individual missions fail.
- **Mitigating factors:** None found for the silent period.
- **Outstanding verification:** Whether the stop was deliberate (owner). The last cycle's per-mission outcomes (owner, from the mission ledger, not reviewed here).
- **Future action:** FA-08; FA-07 for detection.

### ARCH-05 — Infisical client secret passed as a process argument

- **Severity:** MEDIUM.
- **Operational impact:** The Infisical universal-auth client secret appears in the command line of the `infisical login` process. Any local user who can read `/proc/<pid>/cmdline` during the login can read it. Whether `hidepid` is set on `/proc` is **UNKNOWN**.
- **Classification:** VERIFIED (pattern in source). Live exposure: UNKNOWN.
- **Evidence:** PR #610 §16.4 CB-04; §16.9 FA-04.
- **Code location:** [`platform-runtime/lib-infisical.sh:60`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/platform-runtime/lib-infisical.sh#L60) to line 62 (`--client-secret=` is an argument).
- **Mitigating factors:** The login is short-lived. The secret is loaded from the Infisical machine identity, not stored in the repository.
- **Outstanding verification:** `hidepid` mount option on `/proc` (owner or read-only mount check). Whether the Infisical CLI supports a non-argument input for the secret.
- **Future action:** FA-04.

### ARCH-06 — API key accepted in the query string

- **Severity:** MEDIUM–HIGH if URIs are logged; LOW otherwise.
- **Operational impact:** A key placed in a URL can appear in access logs and browser history. The reverse proxy's log filter does not redact URIs for this route.
- **Classification:** VERIFIED (acceptance in code). INFERRED (logging of the key on the live host). Not tested.
- **Evidence:** PR #610 §16.3, §16.4 CB-05.
- **Code location:** [`app.js:88`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/core/command-centre/backend/app.js#L88) (`req.headers['x-api-key'] || req.query.api_key`). The Caddy log filters are in `deploy/caddy/Caddyfile.v3` (PR #610 §16.4 reports lines near 154 and 287; not re-read in this baseline).
- **Mitigating factors:** The header path is preferred. Clients are the Vercel LCARS server and local services (per the Caddy comment at `Caddyfile.v3:46–48`).
- **Outstanding verification:** Whether any client uses the query form (owner, code search). Whether Caddy access logs contain query strings (owner, read-only log sample reviewed for key shape without printing values).
- **Future action:** FA-02.

### ARCH-07 — Redis credential exposed during discovery (SEC-DR-01)

- **Severity:** HIGH for future remediation (preserved from PR #610 §4B).
- **Operational impact:** A Redis `--requirepass` value appeared in container command metadata and in the discovery session's output. Redis publishes no host port, so network access is limited to containers on the Infisical Docker network and Docker-level principals.
- **Classification:** VERIFIED (exposure; the value itself is not reproduced in any document). Whether the credential is still active and accepted: **UNKNOWN**. Other copies in transcripts or logs: UNKNOWN.
- **Evidence:** PR #610 §4A.7, §4B SEC-DR-01, §16.4 (register), §16.9 FA-19. Restic history may hold the old value under the retention policy (§4B).
- **Code location:** The Redis command template in [`deploy/infisical/docker-compose.yml`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/infisical/docker-compose.yml) uses variable interpolation, not a literal. The value appeared in the running container's command metadata, which is outside the repository.
- **Mitigating factors:** No host port; not reachable from outside the VM.
- **Outstanding verification:** Owner rotation after scoping exposure; confirmation that the old value is rejected after rotation.
- **Future action:** FA-19.

### ARCH-08 — Backend uses the Supabase service-role key for all queries

- **Severity:** HIGH (privilege boundary).
- **Operational impact:** The service-role key bypasses row-level security. Compromise of the single API key gate (ARCH-01, ARCH-06) therefore reaches the database with service-role privileges.
- **Classification:** VERIFIED (code references). Live RLS state: UNKNOWN (see ARCH-17).
- **Evidence:** PR #610 §16.1 item 9; §16.3; §16.4 CB-02.
- **Code location:** [`core/command-centre/backend/connectors/supabase-connector.js:16`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/core/command-centre/backend/connectors/supabase-connector.js#L16) reads the service-role key from the environment (variable name only). Other call sites are listed in PR #610 §16.4.
- **Mitigating factors:** The key is read from the environment, not hard-coded in the repository.
- **Outstanding verification:** Whether the environment that holds the key is the one specified in ARCH-09 (UNKNOWN for the deployed unit).
- **Future action:** FA-09.

### ARCH-09 — Command Centre secrets loaded from a repo-root `.env`, outside Infisical

- **Severity:** MEDIUM–HIGH (bypasses the secret store for the most sensitive key).
- **Operational impact:** The Command Centre service starts `node app.js` directly with no Infisical wrapper. Its secrets come from `dotenv` files, including the repo-root `.env`. About 19 other units also have no wrapper (ARCH-16 scope).
- **Classification:** VERIFIED (unit and loader source). Live `.env` content: not read.
- **Evidence:** PR #610 §16.4 CB-03, CB-16; §16.9 FA-03.
- **Code location:** [`deploy/command-centre.service`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/command-centre.service) `ExecStart` runs `node app.js`. [`app.js:19–20`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/core/command-centre/backend/app.js#L19) loads `dotenv` from the repo-root and backend `.env` paths.
- **Mitigating factors:** The `.env` is gitignored (`.gitignore:7–9`).
- **Outstanding verification:** Whether the deployed `.env` holds the same key as Infisical (UNKNOWN, not compared).
- **Future action:** FA-03.

### ARCH-10 — Replacement-VM recovery is evidence-partial

- **Severity:** HIGH (recovery).
- **Operational impact:** A complete VM loss can be recovered only if three owner-held secrets are available (restic password, Google OAuth client, Infisical keys). The Infisical compose used for reconstruction is a reconstruction, and two copies differ. Several persistent locations are not in the backup (see ARCH-12 and PR #610 §16.2). A full restoration to a clean host has not been demonstrated.
- **Classification:** VERIFIED (dependencies and path list). Custody of the owner secrets: **UNKNOWN**. Full restoration: **UNKNOWN** (partial tests only, documented as DOCUMENTED in PR #610 §8.2).
- **Evidence:** PR #610 §4, §4A, §6, §7, §12, §16.2.
- **Code location:** [`deploy/starship-backup.sh:42–43`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/starship-backup.sh#L42) (repository and password file), [`:206–219`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/starship-backup.sh#L206) (path list).
- **Mitigating factors:** Nightly encrypted off-box snapshots (ARCH-22 in §5). Runbook exists (`knowledge/missions/starship-backup-restore-runbook.md`). Documented Infisical and Supabase tests on 2026-10-09.
- **Outstanding verification:** A full restore to a scratch host, and a complete recovery rehearsal. Both need owner authorization.
- **Future action:** FA-18; a new WP-04 item (see §3.4). No numbered FA exists for the full rehearsal.

### ARCH-11 — Supabase `archive` schema is outside the nightly dump

- **Severity:** HIGH for data recoverability (silent coverage reduction).
- **Operational impact:** Migration `0249` moves seven tables to an `archive` schema. The nightly dump includes only `public`, `auth`, `storage` and `supabase_migrations`. Their data therefore remains only in the live Supabase project. The 11-03 to 11-06 decrease in dump entries (92 lines) is consistent with this move, but not confirmed.
- **Classification:** VERIFIED (script filter; migration statements; absence of the seven tables from the 11-06 dump). Application date of `0249`: **self-reported only**, in commit `98ba1cf6a` ("Already applied"). Database history: **UNKNOWN**.
- **Evidence:** PR #610 §8.4 (TOC reconciliation), §16.2, §16.7 C6–C7.
- **Code location:** [`deploy/starship-backup.sh:67`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/starship-backup.sh#L67) (schema filter). Migration [`0249_archive_revs_tables.sql`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/core/infrastructure/supabase/migrations/0249_archive_revs_tables.sql) (executed `SET SCHEMA archive` statements at lines 21–27; a comment at line 12). Commit [`98ba1cf6a`](https://github.com/timjardenross/TJRHQ/commit/98ba1cf6a0b593404c2da294b559e4486ec38fd5).
- **Mitigating factors:** The move is a move, not a drop (no executed DROP statements). The live project retains the data.
- **Outstanding verification:** Migration history query by the owner (Q5). Whether the `archive` schema is part of any other backup (UNKNOWN).
- **Future action:** FA-15.

### ARCH-12 — Git stash-only commits and uncommitted work are outside every backup

- **Severity:** MEDIUM–HIGH (irreplaceable local state, small in volume).
- **Operational impact:** Stash commits (21 entries; 57 stash-only commits) are not reachable from any branch, tag or remote-tracking ref. The bundle covers `refs/heads` only (`--branches`), and `.git` is excluded from restic. Stash-only commits, the live checkout's uncommitted change, and any tags not pushed to GitHub are lost on VM loss. Branch heads with no `origin` counterpart number 153.
- **Classification:** VERIFIED (ref and object counts; bundle command; path list). Stash content: not inspected. Whether the tags and branches exist on GitHub: **UNKNOWN** (remote inventory prohibited in this review).
- **Evidence:** PR #610 §6, §16.2, §16.7 (C-series for tag coverage), §16.10 items 5 and 6.
- **Code location:** [`deploy/starship-backup.sh:144–145`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/starship-backup.sh#L144) (bundle command and verify).
- **Mitigating factors:** Branch heads are in the bundle (VERIFIED). Stashes are local by design.
- **Outstanding verification:** Owner decision on each stash (keep, apply, drop). GitHub state for tags and unpushed branches (owner).
- **Future action:** No numbered FA exists for stash capture. Proposed new WP-04 item (see §3.4). Owner decision required.

### ARCH-13 — Alert-delivery failures are not detected, and some units have no alert path

- **Severity:** HIGH for operational visibility.
- **Operational impact:** The failure-alert script returns 0 when sending fails. The alert unit itself has no `OnFailure=`. Six of the 43 service files in `deploy/` carry `OnFailure=`. Units without one include the dispatch, deadman's switch, verification and delivery units. The watchdog is itself unwatched.
- **Classification:** VERIFIED (script return paths; unit coverage count by grep). Live Telegram delivery: **UNKNOWN**; no test was sent (prohibited). Journal has zero "alert send failed" lines in 14 days (VERIFIED).
- **Evidence:** PR #610 §16.5 (matrix and answers (c)–(d)); §16.9 FA-07.
- **Code location:** [`tools/alert_on_systemd_failure.py`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/tools/alert_on_systemd_failure.py): the send-failure branch prints at line 202 and returns 0 at line 203; alert state is recorded only after a successful send (line 204). Unit: [`deploy/alert-on-failure@.service`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/alert-on-failure@.service).
- **Mitigating factors:** Failure alerts exist for the critical backup and deploy units. Cooldowns are logged.
- **Outstanding verification:** An authorized single test alert (owner-approved, cooldown respected). Confirmation that the Captain's chat is reachable.
- **Future action:** FA-07.

### ARCH-14 — Unpinned images and incomplete deployment reconstruction

- **Severity:** MEDIUM.
- **Operational impact:** Postgres and Redis images are referenced by tag, and the tags have moved. The running containers use untagged images that no longer match the current tags. No documented rollback exists for Infisical, Postgres or Ollama.
- **Classification:** VERIFIED (image IDs and tags; compose references). Restorability of identical images: UNKNOWN.
- **Evidence:** PR #610 §4A.2 rows 4–5, §4A.5 F2–F3, §16.5.
- **Code location:** [`deploy/infisical/docker-compose.yml`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/infisical/docker-compose.yml) (`postgres:15-alpine`, `redis:7-alpine`; Infisical image pinned by digest). Backup script image reference (`postgres:17`, line 66).
- **Mitigating factors:** The Infisical application image is pinned by digest.
- **Outstanding verification:** Whether the repository compose or the private copy reproduces the running stack (UNKNOWN, PR #610 §4A.2 verdict).
- **Future action:** FA-17.

### ARCH-15 — Audit and operational traceability gaps

- **Severity:** MEDIUM.
- **Operational impact:** No single identifier joins a backup run, a deployment and an approval across journal, git and database records. The backup journal records snapshot IDs but not the script commit. The bundle step logs only size and ref count. The approval record store could not be located (the `CaptainApprovalQueue` class has no tracked match). Journal retention is near its cap.
- **Classification:** VERIFIED (absence of shared keys in the reviewed sources). Approval record store: **UNKNOWN**. Journal retention limit effect: UNKNOWN.
- **Evidence:** PR #610 §16.6 (audit inventory and correlation); §8.5.5 (count is not a coverage measure).
- **Code location:** [`deploy/starship-backup.sh:144–146`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/starship-backup.sh#L144). `deploy/auto-deploy.sh` logs a commit SHA pair on each pull.
- **Mitigating factors:** The Supabase `audit_events` table exists with a 90-day prune (per PR #610 §16.6; live table not read).
- **Outstanding verification:** Where owner approvals are recorded (owner). Retention of `escalation_events` and `command_memory_records` (UNKNOWN).
- **Future action:** FA-21, FA-25.

### ARCH-16 — LCARS mutating routes lack Captain role checks

- **Severity:** HIGH if sign-up is open; MEDIUM otherwise.
- **Operational impact:** Some mutating routes (decisions, settings, paid text-to-speech) check only that a Supabase session exists. Any authenticated user would pass if sign-up is enabled.
- **Classification:** VERIFIED (route-level guard absence, by review). Sign-up setting: **UNKNOWN** (no Supabase configuration file is in the repository).
- **Evidence:** PR #610 §16.3 (LCARS rows); §16.4 CB-13; §16.9 FA-11.
- **Code location:** LCARS application routes under `lcars-portal/` (route list in PR #610 §16.3). Session check in [`lcars-portal/src/middleware.ts:145`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/lcars-portal/src/middleware.ts#L145) (specialist-reported; line read in this baseline's preparation).
- **Mitigating factors:** Most routes add their own guard. A mobile bearer path uses `requireCaptainWrite()`.
- **Outstanding verification:** Supabase sign-up setting (owner, dashboard).
- **Future action:** FA-11.

### ARCH-17 — Supabase row-level security posture is not verified live

- **Severity:** HIGH if the PostgREST API exposes the tables; UNKNOWN otherwise.
- **Operational impact:** Migrations show a permissive anon read policy on two intelligence tables (`0035`), and several tables created without `ENABLE ROW LEVEL SECURITY` in the migrations reviewed. Anon-key reachability is not confirmed.
- **Classification:** VERIFIED (migration history). INFERRED (absence of RLS on several tables, from the migration text). Live `pg_tables.rowsecurity` and `pg_policies`: **UNKNOWN**; database access was prohibited in this review.
- **Evidence:** PR #610 §16.4 CB-08, CB-09; §16.9 FA-10.
- **Code location:** `core/infrastructure/supabase/migrations/0035*` (anon read); migrations `0001`, `0024`, `0026`, `0124`, `0125`, `0126` (tables without RLS enable, per review).
- **Mitigating factors:** Service-role access is server-side (ARCH-08).
- **Outstanding verification:** Owner-run read-only queries (`pg_policies`, `pg_tables.rowsecurity`) and the PostgREST exposure setting.
- **Future action:** FA-10.

### ARCH-18 — SEC-01 Caddy containment: live state unknown

- **Severity:** HIGH if containment is absent; UNKNOWN otherwise.
- **Operational impact:** The Caddy configuration contains the SEC-01 v3 block text marked "NOT DEPLOYED" (in the repository and in the live file). Whether the blocks are active in the live Caddy configuration cannot be determined by grep.
- **Classification:** VERIFIED (marker text in both files). Active state: **UNKNOWN**.
- **Evidence:** PR #610 §16.4 CB-15; §16.8 (SEC-01 preserved); §16.9 FA-14.
- **Code location:** [`deploy/caddy/Caddyfile.v3`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/caddy/Caddyfile.v3) (SEC-01 block, marker text). [`deploy/caddy/README-v3.md`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/caddy/README-v3.md) line 1 ("NOT DEPLOYED").
- **Mitigating factors:** SEC-01 gates G3, G4 and G5 were closed with recorded validation (§5). The current live Caddyfile is byte-identical to the repository's `Caddyfile.v3` at the time of the review (`cmp`, PR #610 §13).
- **Outstanding verification:** Owner reads the live Caddy configuration and confirms which blocks are active.
- **Future action:** FA-14.

---

## 3. Five work packages

The five work packages are the stable working-plan structure. They are planning units only. None is authorized for implementation. Each lists its findings, evidence, dependencies, proposed deliverables, acceptance criteria, rollback and verification requirements, and owner authorization.

### 3.1 WP-01 — API Security & Credential Protection

- **Objective:** Remove unauthenticated and over-permissive credential paths; move secrets to the managed store; contain the Redis exposure.
- **Included findings:** ARCH-01, ARCH-05, ARCH-06, ARCH-07, ARCH-09, plus the context-service and TTS fail-open items (PR #610 CB-07, FA-24) and the unused Caddy drop-in (CB-06, FA-23).
- **Existing evidence:** PR #610 §16.1 items 1, 5, 6; §16.3; §16.4 CB-01 to CB-07; §4B SEC-DR-01.
- **Dependencies:** Owner decision on rotation (ARCH-07). Infisical health (FA-03). LCARS server configuration for the key path (FA-01).
- **Proposed future deliverables:** A key-free `/api/config` (or its removal); query-string acceptance removed; secrets read through the Infisical wrapper for the Command Centre unit; client secret passed without argv; Redis credential moved to a file or secret store; context and TTS services fail closed.
- **Acceptance criteria (for eventual implementation):** No endpoint returns a credential. The key is not accepted in a URL. No secret appears in any process command line. Each service reads its secrets from the managed store. Health checks pass after each change.
- **Rollback and verification:** Each change has a documented revert. Verification by local requests with expected 401 responses, service health checks, and log review for key shape without printing values.
- **Owner authorization required:** Yes, for every change in this package and for any credential rotation.

### 3.2 WP-02 — Deployment Governance & Owner Authorization

- **Objective:** Make production change authorized by a reviewed, protected path, and make every Captain-only action enforced at the route or service that performs it.
- **Included findings:** ARCH-02, ARCH-08, ARCH-11 (owner decision on archive), ARCH-12 (GitHub state), ARCH-13 (approval boundary, see WP-03), ARCH-16, ARCH-17, ARCH-18. Also the messaging authorization gaps (ARCH-09 in part; Telegram per chat; Slack research, PR #610 CB-11 and CB-12).
- **Existing evidence:** PR #610 §16.1 items 2, 9, 10; §16.3; §16.4 CB-02, CB-08 to CB-15.
- **Dependencies:** GitHub owner admin rights (branch protection). Supabase owner access (RLS queries, sign-up setting). WP-01 for the service-role path.
- **Proposed future deliverables:** Branch protection and required reviews on `main`. An environment with approval for production deploys. A CI-status gate in the deploy path. Captain role checks on mutating routes. Least-privilege database access per route. Telegram user-ID allowlist. Slack authorization. Confirmed live SEC-01 state.
- **Acceptance criteria:** No commit reaches production without a recorded approval and passing checks. Each mutating route rejects non-Captain identities in a test. No route depends on the service-role key where a per-user client would suffice.
- **Rollback and verification:** Deploy gate can be disabled by the owner with a logged decision. Route changes verified by negative tests in a non-production environment.
- **Owner authorization required:** Yes. This package changes who can ship and who can act. It cannot be implemented by an agent alone.

### 3.3 WP-03 — Job Reliability & Alerting

- **Objective:** Make every critical job's failure visible, make alert delivery failures visible, and remove silent stops.
- **Included findings:** ARCH-03, ARCH-04, ARCH-13. Also the auto-deploy stash and `set -e` fetch path (PR #610 §16.5, FA-22) and the unbounded `hq-evolution` restarts (FA-27).
- **Existing evidence:** PR #610 §16.5 (failure matrix and answers (a)–(f)); §16.1 items 3–4.
- **Dependencies:** WP-02 for the deploy path. The owner's decision on the dispatch stop (ARCH-04).
- **Proposed future deliverables:** Backup script exit propagation and retained `pg_dump` stderr. Alert send failures that exit non-zero and are observable. An alert path for every critical unit. Bounded restarts. A watchdog for the deadman's switch. A stop-detection check for scheduled timers.
- **Acceptance criteria:** A forced failure of each component produces a non-zero exit and an alert, in a dry-run or staging context. Stopped timers appear in a monitored list.
- **Rollback and verification:** Dry-run mode (`DRY_RUN=1`) for backup changes. A single authorized test alert with cooldown respected.
- **Owner authorization required:** Yes, including any test alert and any change to the dispatch schedule.

### 3.4 WP-04 — Backup Completeness & Disaster Recovery

- **Objective:** Make a complete VM loss recoverable from documented sources, and prove it with a rehearsal on a scratch host.
- **Included findings:** ARCH-10, ARCH-11 (archive coverage), ARCH-12 (stash and tag capture), ARCH-14 (pinning and reconstruction). Also off-VM custody of recovery credentials (Q1) and the old repository fallback (Q10).
- **Existing evidence:** PR #610 §4, §4A, §6, §7, §8.4, §8.5, §12, §16.2.
- **Dependencies:** WP-01 for credential rotation (ARCH-07). WP-02 for Supabase migration history (ARCH-11). Owner custody confirmation (FA-18).
- **Proposed future deliverables:** Path-list changes to cover `/root/.claude`, the two memory stores, and any owner-chosen `outputs/` items (FA-28). Coverage for the `archive` schema, if the owner decides it should be dumped (FA-15). A stash and tag capture (new item; see §9). Pinned image digests (FA-17). A full restore rehearsal to a scratch host, with a timed runbook and row-count comparison.
- **Acceptance criteria:** A rehearsal restores the full path list to a clean host, the restored Infisical returns the expected secret count, the restored Supabase dump restores with matching row counts, and the Command Centre starts. Each documented gap is either covered or accepted by the owner in writing.
- **Rollback and verification:** The rehearsal runs on a throwaway host only. Verification by the steps above.
- **Owner authorization required:** Yes. Every restore, restic or rclone operation, and any remote-repository access needs separate authorization.

### 3.5 WP-05 — Auditability & Operational Assurance

- **Objective:** Make approvals, agent executions, deployments and alerts traceable to a common identifier, and retained long enough to review.
- **Included findings:** ARCH-15, plus the alert-state residue (FA-26) and the journal retention question (FA-25).
- **Existing evidence:** PR #610 §16.6 (audit and traceability inventory; correlation; assurance matrix).
- **Dependencies:** WP-02 (approval records). WP-03 (alert records). WP-04 (backup manifests).
- **Proposed future deliverables:** A per-run path manifest and script commit in each backup log line (FA-21). Deploy records that carry the commit SHA and the approving identity. A shared correlation key across backup, deploy and approval records. Retention decisions for audit, escalation and command records.
- **Acceptance criteria:** Given a deployed commit, the approval, the pre-deploy backup and the resulting alert history can be found from one identifier.
- **Rollback and verification:** Logs are additive; changes are reviewed against a sample.
- **Owner authorization required:** Yes, for any change to retention and for any access to audit content.

---

## 4. Dependency and execution sequence

This is a **proposed** sequence. It is not permission to execute. Each step needs the owner's separate authorization.

1. **Contain API and credential exposure risks** (WP-01): remove the `/api/config` key disclosure, stop accepting keys in URLs, and move secrets off process arguments and off the repository `.env`. Rotate the Redis credential and any key that the review shows to have been exposed. This step has no hard dependency, but it should precede any work that exposes new endpoints.
2. **Establish production authorization and deployment controls** (WP-02): branch protection, environments and CI gating on the deploy path; Captain role checks; service-role least privilege; messaging authorization. Depends on step 1 for the key path and on owner access to GitHub and Supabase.
3. **Make operational failures detectable** (WP-03): backup exit propagation, alert send failures, the dispatch stop decision, and stopped-timer detection. Depends on step 2 for the deploy path, and on the owner's decision on the dispatch stop.
4. **Close recovery coverage gaps and prove restoration** (WP-04): path-list changes, the `archive` decision, stash and tag capture, pinned images, and a full rehearsal on a scratch host. Depends on owner custody confirmation (Q1) and on the Supabase migration history (ARCH-11).
5. **Complete audit and assurance improvements** (WP-05): correlation keys, manifests and retention. Depends on steps 2 to 4 for the records it correlates.

**Dependencies between packages:** WP-01 → WP-02 (key path); WP-02 → WP-03 (deploy path, approval records); WP-03 → WP-04 (alert path for backup failures); WP-04 → WP-05 (manifests); WP-02 → WP-05 (approval records). WP-04 is partly independent of the others and can proceed in parallel on the owner's custody confirmation.

---

## 5. Existing verified improvements

These items are real and verified. They are not evidence of complete security or complete disaster recovery. Each caveat is stated.

- **SEC-01 administrative closure and validation.** The gates G3, G4 and G5 were recorded as closed in [`8d44f1cdd`](https://github.com/timjardenross/TJRHQ/commit/8d44f1cdda633028403d146c0fdf43e84ec43d68), merged through PRs [#607](https://github.com/timjardenross/TJRHQ/commit/ea5d6f519f1674069bd108ea05679da900680192) and [#608](https://github.com/timjardenross/TJRHQ/commit/4bc1260b4e76d47db55786488c3bb92a11809ada). The earlier gate work includes PR [#606](https://github.com/timjardenross/TJRHQ/commit/f8e5f9b119dcfc48b8876c75960ec71fd10b11ee). **Caveat:** the live Caddy containment state is unknown (ARCH-18), and the validation evidence is documentary, not re-tested here.
- **PR #609 deployment.** PR #609 is merged into `main` at [`9b7e35c9c`](https://github.com/timjardenross/TJRHQ/commit/9b7e35c9c7469215e98641685951a5dc34eec81b). It installs the weekly integrity check. **Caveat:** the GitHub check results for PR #609 were reported in PR #610 but were not re-queried for this baseline.
- **Nightly backup operation.** Runs finished OK in the journal on each night from 2026-11-01 to 2026-11-08 (PR #610 §16.6 A1, verified in the journal). The backup script was committed in [`42ea6c89b`](https://github.com/timjardenross/TJRHQ/commit/42ea6c89b3d1fe4593af0f3f45b38eb0eec998b5) and related commits. **Caveat:** an OK run does not prove every component was captured (ARCH-03).
- **Successful sampled restic integrity checks.** The 2026-11-05 verification (1% sample) and the 2026-11-08 check (1 in 20 packs) reported no errors (PR #610 §8.2, documented). **Caveat:** sampled, not a full read of the repository.
- **Successful isolated file restore.** Three files were restored to a scratch directory and compared (PR #610 §8.2, documented in [`docs/operations/restic-backup-integrity.md`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/docs/operations/restic-backup-integrity.md)). **Caveat:** three small files, not a full restore.
- **First weekly integrity run passing.** Completed Sunday 2026-11-08 at 11:30 AEDT. The journal shows "no errors were found", 12 of 12 snapshots and 4 of 52 packs read (PR #610 §16.6 A6, corrected in §16.7 C1). **Caveat:** the run is a sample, and the integrity doc does not yet record the result.
- **Backup-path count change explained as increased coverage.** The journal count fell from 96 to 38 because a script change replaced per-unit lines with one line for `/etc/systemd/system`, and added `/opt/deploy-guard`, `/etc/sysstat` and `journald.conf.d` (PR #610 §8.5; script history at [`dbbfbae1a`](https://github.com/timjardenross/TJRHQ/commit/dbbfbae1a05adc80e3036d1575ed929d05cbcc32)). **Caveat:** the 11-04 unit count is inferred, and the change applies from the 11-05 run onward.
- **Coolify decommissioning and removal from the active recovery chain.** The live Caddy configuration and repository comments record the decommission on 2026-09-26 (`deploy/caddy/Caddyfile.v3` lines 25–28 and 172–174 at [`9b7e35c9c`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/caddy/Caddyfile.v3#L25)). No TJRHQ code path depends on Coolify (PR #610 §4A.3). **Caveat:** Coolify residue remains on the VM (volumes and `/data/coolify`), and its key material is an owner decision (FA-20).

---

## 6. Unresolved decisions

Each item is an open question. Items marked "owner" need owner input, not VM inspection.

| # | Decision or question | Why it matters | Owner or evidence needed |
|---|---|---|---|
| 1 | **Owner custody of off-VM recovery credentials** (restic password, Google OAuth client, Infisical keys) | Without them, no backup can be read after VM loss | Owner confirms presence and currency, without sharing values |
| 2 | **GitHub branch protection on `main`** (required reviews, status checks, environments) | Determines whether ARCH-02 is an owner-approval boundary | Owner reads GitHub settings |
| 3 | **Actual live Caddy security configuration** (which SEC-01 blocks are active; ARCH-18) | Determines write containment at the edge | Owner reads the live Caddyfile |
| 4 | **Live Supabase RLS and sign-up settings** (ARCH-16, ARCH-17) | Determines whether anon or sign-up paths reach data | Owner runs read-only `pg_policies` and `pg_tables.rowsecurity` queries and checks the sign-up setting |
| 5 | **Migration `0249` application status** (ARCH-11) | Decides whether the archive data is outside backup | Owner reads Supabase migration history. Commit message says "Already applied" (self-reported) |
| 6 | **Backup coverage for the `archive` schema** (ARCH-11) | Decides whether the nightly dump should include it | Owner decision after #5 |
| 7 | **Whether mission dispatch inactivity was intentional** (ARCH-04) | Decides whether the stop is a defect or a decision | Owner decision |
| 8 | **Whether the exposed Redis credential remains active** (ARCH-07) | Decides urgency of rotation | Owner, after scoping exposure |
| 9 | **Full replacement-VM restoration not yet demonstrated** (ARCH-10) | Recovery is unproven until a rehearsal runs | Owner authorizes a scratch-host rehearsal |
| 10 | Whether the old repository `rclone:gdrive:starship-backups` still exists (PR #610 Q10) | Possible fallback for backups | Owner |
| 11 | Whether tags, branches and stashes exist on GitHub (PR #610 Q6) | Determines loss from VM failure | Owner or GitHub admin (remote inventory prohibited in review) |
| 12 | Whether the Command Centre `.env` holds the same key as Infisical (ARCH-09) | Determines which secret is live | Owner, using a comparison method that does not print values |
| 13 | Supabase Storage objects and Vault contents (PR #610 Q13) | Determines whether these need backup | Owner dashboard |
| 14 | Coolify key material and residue retention (PR #610 Q18, Q19) | Determines whether `/data/coolify` is kept | Owner decision |
| 15 | Approval record store (ARCH-15) | Determines whether approvals are auditable | Owner, and code owner for the approval flow |

---

## 7. Governance

**This document approves the review as a planning baseline only.**

It does not authorize:

- Production changes.
- Credential rotation.
- Database modifications.
- Deployment or service restarts.
- Backup or restore operations.
- PR merges.
- Implementation of any future action.

Changes to this baseline require a reviewed Git commit and a pull request. Status changes (for example, from "planning" to "execution") require a separate owner decision recorded in the repository.

---

## 8. Evidence references

**Primary evidence record**

- PR #610: [timjardenross/TJRHQ#610](https://github.com/timjardenross/TJRHQ/pull/610)
- Evidence commit: [`e61abcffc5b01cf9875697e27acd3e907d7a21d8`](https://github.com/timjardenross/TJRHQ/commit/e61abcffc5b01cf9875697e27acd3e907d7a21d8)
- Evidence document at the evidence commit: [`docs/operations/disaster-recovery-gap-assessment-2026-11-08.md`](https://github.com/timjardenross/TJRHQ/blob/e61abcffc5b01cf9875697e27acd3e907d7a21d8/docs/operations/disaster-recovery-gap-assessment-2026-11-08.md)

**Production commit and source files** (permalinks to `9b7e35c9c7469215e98641685951a5dc34eec81b`)

- Command Centre: [`core/command-centre/backend/app.js`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/core/command-centre/backend/app.js); [`deploy/command-centre.service`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/command-centre.service).
- Deployment: [`deploy/auto-deploy.sh`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/auto-deploy.sh); [`deploy/auto-deploy.service`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/auto-deploy.service).
- Backup: [`deploy/starship-backup.sh`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/starship-backup.sh); [`docs/operations/restic-backup-integrity.md`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/docs/operations/restic-backup-integrity.md).
- Dispatch: [`core/engineering/mission_dispatch.py`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/core/engineering/mission_dispatch.py).
- Infisical: [`platform-runtime/lib-infisical.sh`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/platform-runtime/lib-infisical.sh); [`deploy/infisical/docker-compose.yml`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/infisical/docker-compose.yml).
- Messaging: [`core/platform/telegram_access.py`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/core/platform/telegram_access.py); [`platform-runtime/commands/research_command.py`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/platform-runtime/commands/research_command.py).
- Caddy: [`deploy/caddy/Caddyfile.v3`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/caddy/Caddyfile.v3); [`deploy/caddy/README-v3.md`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/deploy/caddy/README-v3.md).
- Supabase: [`core/infrastructure/supabase/migrations/0249_archive_revs_tables.sql`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/core/infrastructure/supabase/migrations/0249_archive_revs_tables.sql); [`core/command-centre/backend/connectors/supabase-connector.js`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/core/command-centre/backend/connectors/supabase-connector.js).
- Runbook: [`knowledge/missions/starship-backup-restore-runbook.md`](https://github.com/timjardenross/TJRHQ/blob/9b7e35c9c7469215e98641685951a5dc34eec81b/knowledge/missions/starship-backup-restore-runbook.md).

**Prior security and backup changes** (permanent commit links)

- SEC-01 closure: [`8d44f1cdd`](https://github.com/timjardenross/TJRHQ/commit/8d44f1cdda633028403d146c0fdf43e84ec43d68); PR #607 merge [`ea5d6f519`](https://github.com/timjardenross/TJRHQ/commit/ea5d6f519f1674069bd108ea05679da900680192); PR #608 merge [`4bc1260b4`](https://github.com/timjardenross/TJRHQ/commit/4bc1260b4e76d47db55786488c3bb92a11809ada); PR #606 merge [`f8e5f9b11`](https://github.com/timjardenross/TJRHQ/commit/f8e5f9b119dcfc48b8876c75960ec71fd10b11ee).
- PR #609 (weekly integrity): [`9b7e35c9c`](https://github.com/timjardenross/TJRHQ/commit/9b7e35c9c7469215e98641685951a5dc34eec81b); integrity script commit [`42ea6c89b`](https://github.com/timjardenross/TJRHQ/commit/42ea6c89b3d1fe4593af0f3f45b38eb0eec998b5).
- Nightly backup (Supabase cadence): [`c4c59bdba`](https://github.com/timjardenross/TJRHQ/commit/c4c59bdbad15ae524007232d669be9690d463ba3); Google OAuth client switch: [`543ab9312`](https://github.com/timjardenross/TJRHQ/commit/543ab931220fbb06b8ea08fe6cf6706b04ff6184).
- Path-list change: [`dbbfbae1a`](https://github.com/timjardenross/TJRHQ/commit/dbbfbae1a05adc80e3036d1575ed929d05cbcc32); venv freeze: [`7a8dd3b84`](https://github.com/timjardenross/TJRHQ/commit/7a8dd3b84f03b9401c45ab9b3d749f11b38a337a).
- Archive migration: [`98ba1cf6a`](https://github.com/timjardenross/TJRHQ/commit/98ba1cf6a0b593404c2da294b559e4486ec38fd5).
- Infisical compose history: [`e218bd7c2`](https://github.com/timjardenross/TJRHQ/commit/e218bd7c2a98c19ed30fb530f3d14e799f960930) (recovered 2026-10-04), [`846b2aa31`](https://github.com/timjardenross/TJRHQ/commit/846b2aa311b3b59d586ba557c3716d09ec8e79ff) (pinned digest, project name).

**Reader note.** The links above are commit-specific, so they remain valid even if branches move. The PR #610 links depend on the commit being retained on GitHub. The baseline is intended to be understandable without access to the VM: each finding states its evidence in the text, and the evidence document carries the command outputs and file line numbers.

---

## 9. Evidence traceability to the existing action register (FA-01 to FA-29)

This mapping links each baseline finding to the existing actions in PR #610 §16.9. The FA numbers are the originals; they have not been renumbered or duplicated. Where no existing action covers a baseline finding, the mapping says so, and the item is proposed as a **new** work item. New items do not receive FA numbers in this document.

### Baseline findings → existing actions

| Baseline finding | Existing action(s) | Note |
|---|---|---|
| ARCH-01 `/api/config` disclosure | FA-01 | |
| ARCH-02 deploy without gate | FA-05 | Also FA-22 for the stash path in auto-deploy |
| ARCH-03 backup exit propagation | FA-06 | |
| ARCH-04 dispatch inactivity | FA-08 | Detection: FA-07 |
| ARCH-05 Infisical argv secret | FA-04 | |
| ARCH-06 query-string key | FA-02 | |
| ARCH-07 Redis credential | FA-19 | |
| ARCH-08 service-role use | FA-09 | |
| ARCH-09 Command Centre env outside Infisical | FA-03 | Also FA-03 covers unwrapped units (CB-16) |
| ARCH-10 replacement-VM recovery | FA-18 | Full rehearsal: **no existing action**; proposed new WP-04 item |
| ARCH-11 `archive` exclusion | FA-15 | Owner decision on dump scope; FA-29 for Storage and Vault scope |
| ARCH-12 stash and tag capture | **No existing action** | Proposed new WP-04 item; owner decision on each stash (PR #610 §9) |
| ARCH-13 alert delivery | FA-07 | Also FA-26 for the residue, FA-27 for unbounded restarts |
| ARCH-14 unpinned images | FA-17 | Also FA-16 (byte-identity checks) |
| ARCH-15 traceability | FA-21, FA-25 | |
| ARCH-16 LCARS role checks | FA-11 | |
| ARCH-17 RLS posture | FA-10 | |
| ARCH-18 SEC-01 live state | FA-14 | |

### Existing actions → baseline work packages

| FA | Action (short) | Work package |
|---|---|---|
| FA-01 | Remove key from `/api/config`; bind to localhost | WP-01 |
| FA-02 | Stop query-string keys; redact URIs | WP-01 |
| FA-03 | Wrap Command Centre and other units with Infisical | WP-01 |
| FA-04 | Pass Infisical client secret safely | WP-01 |
| FA-05 | Branch protection; deploy approval; CI gate | WP-02 |
| FA-06 | Backup exit propagation; retain `pg_dump` stderr | WP-03 |
| FA-07 | Alert send failures observable; alert-path coverage | WP-03 |
| FA-08 | Decide dispatch stop | WP-03 |
| FA-09 | Per-route least-privilege database client | WP-02 |
| FA-10 | Owner RLS and PostgREST checks | WP-02 |
| FA-11 | Captain role checks | WP-02 |
| FA-12 | Slack research authorization | WP-02 |
| FA-13 | Telegram user-ID allowlist | WP-02 |
| FA-14 | Confirm live SEC-01 Caddy state | WP-02 |
| FA-15 | Migration `0249` status; archive backup policy | WP-04 |
| FA-16 | Byte-identity checks after changes | WP-04 (verification discipline) |
| FA-17 | Pin images; document rollback | WP-04 |
| FA-18 | Confirm credential custody | WP-04 |
| FA-19 | Redis rotation | WP-01 |
| FA-20 | Coolify residue and `.env` permissions | WP-04 |
| FA-21 | Per-run manifest and commit in logs | WP-05 |
| FA-22 | Auto-deploy stash and `set -e` fetch path | WP-03 |
| FA-23 | Remove unused Caddy drop-in | WP-01 |
| FA-24 | Context service fail-closed | WP-01 |
| FA-25 | Journal retention decision | WP-05 |
| FA-26 | Owner reviews alert-state residue (do not clear) | WP-05 |
| FA-27 | Bound `hq-evolution` restarts | WP-03 |
| FA-28 | Decide backup scope for `/root/.claude` and memory stores | WP-04 |
| FA-29 | Decide Supabase Storage and Vault backup scope | WP-04 |

**Gaps in the mapping (no existing action):** a full replacement-VM rehearsal (ARCH-10); stash and tag capture (ARCH-12); the approval record store (ARCH-15); the sign-up setting check (ARCH-16, owner question #4). These are proposed new items. They are not numbered here, and they are not authorized.

---

## 10. Quality checks (record of this baseline's preparation)

- The baseline reflects PR #610 at the evidence commit. Each material finding cites a PR #610 section and, where applicable, a production-commit permalink. Items that were checked only by a specialist, and not re-read by the lead, are cited as such in PR #610 §16.
- No credential value, token, password, fingerprint, connection string or sensitive database content appears in this document. Credentials are referenced by variable name and file only.
- All unresolved questions from PR #610 are visible in §6 or as UNKNOWN in the findings.
- The document contains no implementation authorization. Each work package states that owner authorization is required.
- Only the new documentation file is changed in this branch.
- Markdown links were checked for syntax; each link uses a full commit SHA.
