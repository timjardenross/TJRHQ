# VM Optimise: Zero-Cost Remediation Plan

Outcome of the 2026-10-09 VM discovery and future-readiness assessment.
The verdict is **OPTIMISE: keep the VM.** The Captain's budget rule is
**no increase in spend**, so every step in this plan costs €0.

## Mission Header

- **Mission ID:** to be minted on the VM with `python3 tools/mint_id.py MSN`
  before starting. It isn't minted here because the VM's
  `.id-counters.json` has uncommitted changes, and minting in a second
  checkout would collide.
- **Priority:** P1 (data protection, access, health-data handling)
- **Source:** the 2026-10-09 VM assessment (Steps 1–7) and the Captain's
  answers:
  - Single operator.
  - Best-effort availability.
  - Hybrid AI, with cloud calls allowed only after redaction.
  - No budget increase.
  - REVS moves to TJR Mind Body later.

## Pre-flight

1. [x] **Existing-entry check.** This mission adds one backup timer and
   possibly one migration.
   - Backups: no backup tooling exists today. The VM session searched for
     `rsync|restic|borg|rclone|pg_dump|snapshot` in cron, systemd and spool
     and found none.
   - Supabase pruning already exists, so don't duplicate it. Live
     `cron.job` has seven jobs:
     - `prune_domain_heartbeats_daily`
     - `prune_core_events_daily`
     - `prune_verification_state_daily`
     - `prune_intelligence_source_health_daily`
     - `prune_audit_events_daily`
     - `uss_tjr_daily_heartbeat`
     - `uss_tjr_daily_snapshot`

     (Migration `0221_prune_high_churn_log_tables.sql` creates four of the
     five prune jobs.)
   - Scheduler rule: the backup job is a **systemd timer**, not a new
     APScheduler instance (AGENTS.md "Scheduled jobs").
2. [x] **Premise verification.** Checked 2026-10-09:
   - Supabase organisation plan = `free` (Management API). Free plans have
     no restorable backups
     (https://supabase.com/docs/guides/platform/backups).
   - Database size is 419 MB against the Free plan's 500 MB read-only
     limit (https://supabase.com/docs/guides/platform/database-size).
     Migration 0221 records 83% on 2026-09-20; it is 84% now. Net growth is
     slow because the prune jobs are working.
   - `idx_processing_chunks_embedding_hnsw`:
     - 69 MB, `idx_scan = 0` since stats reset on 2026-05-22, which is
       before the project existed.
     - No `public` SQL function references `processing_chunks`.
     - Only `0042_document_processing_pipeline.sql` creates the index.
       `lcars-portal/src/lib/knowledgeLibraryDecide.ts` reads the column
       but runs no similarity search on it.
   - `processing_chunks` has no new rows since 2026-08-23. 760 documents in
     `awaiting_review` hold 18,503 of its chunks.
   - `core/llm/provider_chain.py` `call_gemini`/`call_mistral` apply no
     redaction. `llm_guardrails` is imported only by the router,
     `intelligence/scheduler.py` and the Mistral batch providers.
     `tools/health-osint/health_signal_synthesis.py` calls the provider
     chain directly. `health_signal_curation.py` falls back to it when the
     router fails.
   - SSH has `PermitRootLogin yes` and `PasswordAuthentication yes`
     (effective). fail2ban shows 89 failures and 13 bans.
3. [x] **Explicitly not in scope:** see below.

## Explicitly Not In Scope

- **Anything that costs money:** Supabase Pro, PITR, a VM resize or
  upgrade, a GPU, paid monitoring. Ruled out by the Captain's budget rule.
- **Deleting anything** on the VM: orphaned Coolify volumes,
  `.env.bak-*`, `/root` staging dirs, Ollama models. Inventory only. Each
  deletion needs its own Captain decision, made after backups exist.
- **REVS migration** to TJR Mind Body, including the crisis-fallback
  latency fix (R11). Tracked for that migration.
- **Off-box uptime alerting.** The Captain rated it LOW.
- **Re-architecting Ollama access** beyond the logging and gating in
  Stream 6.

## Scope / Streams

Work in an **isolated worktree** on the VM. Never use the shared
`/opt/starship-endeavour` checkout (AGENTS.md "Concurrent session git
safety"). Before any change, take a Contabo snapshot if your plan includes
one at no charge (check in the customer panel; don't buy one).

### Stream 0: Captain checks (today, ~15 min, no tools)

1. Supabase dashboard → Authentication → Sign In / Providers. Confirm
   **"Allow new users to sign up" is OFF**. If it's on, turn it off. The
   portal admits any valid session.
2. Confirm that all 3 `auth.users` accounts are yours (Authentication →
   Users). If one isn't, remove it and change your password.
3. Contabo panel: note your plan's price, and whether snapshots are
   included for free.

**Done when:** sign-up is off, accounts are confirmed, and the price is
recorded.

### Stream 1: Save the code that exists only on the VM (week 1)

The VM has 66 commits on 8 local branches with no remote, plus 65
uncommitted changes in the shared checkout.

1. Scan for secrets **before pushing**. gitleaks is free and runs from
   Docker:
   ```bash
   cd /opt/starship-endeavour
   for b in $(git branch --format='%(refname:short)' --no-merged origin/main); do
     docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:latest \
       git /repo --log-opts="origin/main..$b" --redact --no-banner || echo "FINDINGS on $b"
   done
   ```
   Any finding means you remove the secret from that branch's history
   *before* pushing, and rotate the secret.
2. Push each clean branch: `git push -u origin <branch>`.
3. The 65 uncommitted changes:
   - Create a worktree.
   - Copy only the intended edits onto a new branch named after the
     mission ID.
   - Scan and push.
   - Don't commit `.id-counters.json` blindly. It's the ID registry, so
     reconcile it with `main` first.

**Done when:** `git log --branches --not --remotes` is empty, and
`git status` in the shared checkout shows only known runtime files.

### Stream 2: Encrypted off-box backups at €0 (week 1)

**Tooling:** `restic` (encrypted, deduplicated) plus `rclone` as the
transport. Both are free (`apt install restic rclone`).

**Target**, in this order of preference:

- **A. Google Drive.** You already have the account: 15 GB free. Use
  `rclone config` → "drive", then a restic repo at
  `rclone:gdrive:starship-backups`.
- **B. Backblaze B2 or Cloudflare R2 free tier.** About 10 GB free
  (check current limits before choosing; either may require a card on
  file).
- **C. Your Mac pulls nightly** over SSH with `rsync`. Free, but it only
  works while the Mac is on.

Expected size is well under 2 GB with retention, which fits any of the
three.

**What to back up, daily:**

| Item | How |
|---|---|
| Supabase database | `supabase db dump --db-url "$SUPABASE_DB_URL" -f supabase.sql` plus a `--data-only` dump (or `pg_dump` 17). URL comes from Infisical at runtime and is never written to disk |
| Infisical database | `docker exec infisical-db-1 pg_dump -U <user> <db>` → file |
| Infisical encryption keys | `ENCRYPTION_KEY` / `AUTH_SECRET` from Infisical's own env file. **Stored separately, in your password manager, NOT in the restic repo.** Without them, the Infisical dump can't be decrypted |
| VM-only state | `data/self-improvement/review/`, `outputs/delivery_ledger.txt`, all `.env*` files, `/etc/caddy`, `/etc/systemd/system/*.service|*.timer`, `ufw` rules (`ufw status numbered > ufw.txt`), crontabs |
| restic repo password | Password manager only |

**Schedule:**
- A systemd `.service` plus `.timer`, daily at 02:40 local. This sits
  clear of the 02:17 `memory-nightly-consolidation` and the 03:00
  `hq-evolution` jobs.
- Retention: `restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 3 --prune`.

**Failure signal:** on a non-zero exit, send one Telegram message through
the existing XO notification path. That adds no new scheduler and costs
nothing.

**Test restore (mandatory; the stream isn't done without it):**
1. `restic restore latest --target /tmp/restore-test`.
2. Load `supabase.sql` into a throwaway `postgres:17` container. Compare
   table counts with live (`select count(*) from information_schema.tables where table_schema='public'`).
3. Load the Infisical dump into a throwaway Infisical stack using the
   keys from the password manager. Confirm one known secret *name*
   resolves.
4. Delete `/tmp/restore-test`.

**Done when:** two consecutive nightly runs have succeeded, and one test
restore of both databases has passed.

### Stream 3: Lock down SSH (week 1, after Stream 2's first backup)

1. Confirm you can log in **with a key** in a second terminal. Keep the
   current session open throughout.
2. Create `/etc/ssh/sshd_config.d/00-hardening.conf`:
   ```
   PasswordAuthentication no
   KbdInteractiveAuthentication no
   PermitRootLogin prohibit-password
   ```
   The `00-` prefix matters. sshd uses the first value it reads, and
   Ubuntu cloud images ship `50-cloud-init.conf`, which can set
   `PasswordAuthentication yes`.
3. `sshd -t && systemctl reload ssh`. Then, from a **new** terminal:
   - Key login works.
   - `ssh -o PubkeyAuthentication=no root@host` is refused.
   - Check the effective values: `sshd -T | grep -Ei 'passwordauth|permitroot'`.
4. Fallback: the Contabo VNC console. Rollback: delete the file and
   reload.
5. Remove the stale Coolify ufw rules (8000, 6001:6002). Nothing listens
   on them: `ufw status numbered`, then `ufw delete <n>`.

**Done when:** `sshd -T` shows `passwordauthentication no`, a password
login is refused, and the stale rules are gone.

### Stream 4: Supabase headroom at €0 (week 2)

Current state: 419 MB of 500 MB.

1. **Drop the unused vector index** (69 MB, zero scans ever). Do it as a
   migration file, `core/infrastructure/supabase/migrations/NNNN_drop_unused_processing_chunks_hnsw.sql`,
   with the rollback in its header. Use the next free number; it was 0229
   when this was written, so check `ls` first.
   ```sql
   -- Rollback: re-run the create index from 0042_document_processing_pipeline.sql
   drop index if exists public.idx_processing_chunks_embedding_hnsw;
   ```
   Before applying, record `pg_get_indexdef` and re-confirm
   `idx_scan = 0`. Expected result: about 350 MB (70%).
2. **Backlog decision (Captain):** 760 documents have sat in
   `awaiting_review` since August, holding about 76 MB of chunks. Either
   review or exclude them in bulk. If you exclude them, deleting their
   `processing_chunks` frees most of the 76 MB. That's your call; it's not
   automated here.
3. **Watch:**
   - Add a weekly size line to an existing brief or report
     (`pg_database_size`).
   - Alert at 450 MB.
   - `intelligence_events` (about 11k rows per 28 days, no retention) is
     the main remaining grower. Set a retention window only if the
     database trends back above 80%.

**Done when:** the database is at or below 75% and the weekly size line is
visible.

### Stream 5: Cloud calls only after redaction (weeks 2–3)

This enforces the Q4 rule: cloud calls only after redaction.

1. Make `core/llm/provider_chain.py` `call_gemini` and `call_mistral` run
   the same `core.security.llm_guardrails` input and output checks the
   router uses, **failing closed** like `_FAIL_OPEN` in the router. This
   one change covers every direct caller, including both health-osint
   tools.
2. Add tests:
   - The guard is invoked.
   - The call is refused when the guard is unavailable.
   - Text over the spaCy length limit is chunked or refused, never sent
     raw (the E088 case).
3. `glm-*:cloud`: restrict it to an explicit non-sensitive task allowlist
   in the router until it's guarded.
4. Confirm the status of `health-signal-curation`: no logged calls since
   2026-09-27. Find out whether it's retired, moved, or failing silently.

**Done when:**
- Tests pass in CI.
- `grep -rn "call_gemini\|call_mistral"` shows no unguarded path.
- One real health-osint run shows redaction in its trace.

### Stream 6: Boot reliability and visibility (weeks 3–4)

1. Change `platform-runtime/run-with-infisical.sh` and
   `run-with-infisical-bot.sh` to wait for Infisical before fetching:
   - Poll the local Infisical status endpoint.
   - Wait up to 120 s with backoff.
   - Then fetch, and fail loudly if it's still down.

   Target: 0 "failed to fetch secrets" errors after the next reboot
   (currently 68 in 14 days).
2. Log every local Ollama request:
   - Add a shared helper that writes the same `call_log.jsonl` shape the
     router writes.
   - Use it in `provider_chain.call_ollama` and `platform-runtime/llm.py`
     first. Those two cover most of the 25+ direct callers.
3. Increase sysstat retention: set `HISTORY=28` in `/etc/sysstat/sysstat`.
   (Checked 2026-10-09: already `HISTORY=90`, so no change is needed.)
4. During a busy period, run
   `timeout 3600 pidstat -u -l 15 | awk 'NR<4 || $8>=25'` and record the
   cause of the CPU bursts.

**Done when:** a reboot is clean, local calls appear in the log, and the
burst cause is named.

The "0 errors" target counts the wrappers' "refusing to start" lines, not
raw CLI errors: the readiness probe hides the CLI's stderr.

### Days 61–90: review only

- Re-run the sizing on 30–60 days of sysstat data. Decide on the VM plan
  at renewal, with downsizing allowed only if the RAM peak stays below
  12 GiB.
- Review the local models: the 24B model hits its 300 s timeout on more
  than half of calls. Inventory them; delete nothing without a decision.
- Reassess REVS relocation and off-box alerting if any trigger has fired:
  - other users gain access
  - REVS goes live
  - time-sensitive reliance
  - "production-ready"

## Follow-ups (recorded 2026-10-10)

Recorded, not acted on unless a line says otherwise.

**Before REVS moves or goes live**
- Before `tg-revs` is ever unmasked: revoke the REVS Telegram token once
  more and store the new one directly in Infisical (the current one passed
  through a chat session). It stays masked until then.
- Decide the `crisis_layer2` fallback: a guarded cloud call takes about
  45-90 s (see `telegram-bots/revs/README.md`).

**Secret-rotation batch (not urgent)**
- Supabase database password and service key, GitHub token, Infisical
  admin credential, the other Telegram bot tokens, and the Infisical Redis
  password (it was printed into a tool output once during Stream 6
  inspection; the Redis container publishes no port).
- Names and counts only in any record. Never values.

**Deploy and sync reliability (incident of 2026-10-09/10)**
- What happened: four directories had been created as `root:deploy` mode
  2755 on Oct 3, so `deploy` could not write into them. The fast-forward
  failed half-way, left tracked and untracked files half-applied, and every
  later tick aborted. While auto-deploy was wedged, the sync job committed
  state files onto the stale local `main`, so local and origin diverged.
  Fixed by hand on 2026-10-10: permissions corrected, the half-written
  files removed after a byte-identical check, the three state commits
  replayed onto `origin/main` and pushed.
- Find what created those four directories as `root:deploy` 2755 on Oct 3
  (a root session's umask, or a script) so it cannot recur. Report only.
- `auto-deploy.sh` should clean up after a failed fast-forward: restore the
  half-written tracked files and remove the half-written untracked ones
  that match the target, so one permission error cannot wedge every later
  deploy. Report only; no change yet.
- Sync job: fetch and fast-forward before committing, skip with a warning
  if it cannot (PR #361). Merge before it is installed.
- Sync timer logged far fewer runs than its cadence implies; check whether
  it was off for part of the period.

**Backup and Supabase**
- Alert when a service sees the Supabase restriction error body (the
  Oct 2-5 `exceed_egress_quota` restriction went unnoticed for days).
- Check the dump and test dumps against the Free-plan egress cap in the
  Supabase dashboard (TO BE VERIFIED by the Captain).
- Backup-freshness alert.
- Use our own Google OAuth client for the restic remote.
- Lengthen the restic password.
- Roles-only export of the Supabase database.
- Add `HEAD` to the git bundle.

**Open**
- An unexplained login on Oct 7 is still unresolved (details in
  `/root/private-knowledge`, not here).

## Cost

| Stream | Cost |
|---|---|
| 0–6 | €0 (restic, rclone, gitleaks and sysstat are free; Google Drive's 15 GB is already yours) |
| Net change to monthly spend | **€0** |

## Acceptance

- [ ] Portal sign-up is off, and all 3 accounts are confirmed as the
      Captain's.
- [ ] No VM-only commits remain without an off-box copy (GitHub, or the
      verified bundle in the restic backup). Everything was secret-scanned
      before push.
- [x] Nightly encrypted off-box backups of Supabase, Infisical and the
      VM-only state have run (first unattended run OK 2026-10-10 02:40,
      3 snapshots, nothing removed, no alert). The Infisical keys are held separately. One
      test restore of each database has passed.
- [ ] SSH is key-only, with password and root-password login refused.
- [ ] The Supabase database is at or below 75% of the Free limit, with a
      weekly size line.
- [ ] No cloud LLM path bypasses `llm_guardrails`, and the tests prove it.
- [ ] A reboot produces no Infisical fetch failures.
- [ ] Spend is unchanged.

## Reporting

- One knowledge record per stream in `knowledge/missions/`, using the
  minted mission ID.
- Lessons-Learned entry: "Free-plan systems of record need their own
  backups."
- SUOC Platform Registry: add the backup capability (Stream 2) as a new
  platform capability. No other registry changes.
