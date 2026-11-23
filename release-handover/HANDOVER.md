# VM release handover — #661 → #658 → #662  (READ-ONLY until the Captain approves)

## 0. Rules for the VM agent
- Allowed now: the read-only checks in §3. Nothing else.
- **Do not**: merge, `git pull/fetch/checkout/commit` in `/opt/starship-endeavour`, restart/stop/start any service, edit any unit/env/config file, run `apt`/`pip` installs, set any variable, trigger any brief/scheduler job, send any message, or roll back — until the Captain explicitly approves that specific action.
- Development stays on the Mac. A code defect found here is **returned to the Mac with evidence** (command, output, commit, journal excerpt with no secrets/personal content). Never patched or committed on the VM: `auto-deploy.sh` aborts on a modified tracked tree.
- Never print environment values. The provided scripts report presence only; do not `cat` env files or `/proc/*/environ`.
- Get this handover with a **separate clone outside the deploy tree** (the deploy checkout is never fetched or touched):
  `git clone --depth 1 --branch claude/vm-release-handover-7n6u2j https://github.com/timjardenross/TJRHQ.git /tmp/release-handover-repo && cp -r /tmp/release-handover-repo/release-handover /tmp/release-handover && chmod +x /tmp/release-handover/*.sh`
  The scripts do not depend on the PR code, so the preflight works before any merge. This branch is not part of the release and must never be merged.

## 1. Frozen candidates (verified, CI green on exactly these heads)
| Order | PR | Head | Contents |
|---|---|---|---|
| 1 | #661 | `40364379` | Privacy containment: default-deny external AI for personal health data, local-only routing, XO fallback wording, work-email capacity-block removal |
| 2 | #658 | `08c75d12` | Editorial comms brief, behind `COMMS_EDITORIAL_V2` (off) |
| 3 | #662 | `77f9aef8` | Shared V1 evidence foundation (all `BRIEF_EVIDENCE_V1*` off) + weekly capacity correction (`BRIEF_CAPACITY_QUALITY_V1`, off) |

Main tip when frozen: `9be606d0`. **#662's branch contains #661 and #658 as ancestors.** Merges must therefore use a **merge commit** (not squash, not rebase), or #662 will conflict/duplicate. Mechanism: merge to `main` → `auto-deploy.timer` (every 5 min) fast-forwards `/opt/starship-endeavour` and restarts the ten services. Each merge = one production deployment. Restarts are expected.

Declared ten services (`deploy/auto-deploy-services.conf`; this is repo intent, so reconcile against `systemctl`): context-service, intelligence-scheduler, mint-server, model-router, self-improvement-dashboard, tg-capacitybot, tg-resiliencebot, human-systems-scheduler, command-centre, tg-xo.

## 2. Expected production state (throughout, after every merge)
Absent in every source: `HEALTH_LLM_EXTERNAL_ALLOWED`, `COMMS_EDITORIAL_V2`, `BRIEF_EVIDENCE_V1`, `BRIEF_EVIDENCE_V1_MORNING`, `_WEEKLY`, `_COMMS`, `BRIEF_EVIDENCE_SNAPSHOT_PATH`, `BRIEF_CAPACITY_QUALITY_V1`.
Unchanged: schedules, recipients, Telegram/email content selection (apart from the accepted #661 removal of personal capacity/recovery/pain blocks from the work-mailbox email). No migration, retention action, snapshot file, report activation or external send.

## 3. Pre-deployment preflight (read-only; run now, return the output)
```
cd /tmp/release-handover
./preflight_baseline.sh   > baseline.txt   2>&1   # commit, tracked-tree cleanliness, timer, ten-service table, inventory reconciliation
./preflight_flags.sh      > flags.txt      2>&1; echo "flags exit=$?"       # presence only, running + effective configuration
./run_local_model_check.sh > model.txt     2>&1; echo "model exit=$?"       # uses the #661 diagnostic copy + tg-xo's OLLAMA_* settings only
```
What `preflight_flags.sh` covers (never searches repo docs/tests): systemd manager env, each unit's running process env, unit definition + drop-ins, `EnvironmentFile`s, `WorkingDirectory/.env`, repo-root `.env`.

Pass criteria:
- baseline: `HEAD` equals `main` tip (or the Captain-known deployed commit); **tracked tree clean**; `auto-deploy.timer` active; all ten units present and active/running (note any inactive one, don't fix it).
- flags: exit 0 (none present). Exit 1 → **STOP**. Exit 2 → reconcile unit inventory, report.
- model exit: **0** = local model available. **2 or 3** = degraded local model; acceptable for privacy only because deterministic fallback is covered (CI privacy/failure-path tests; confirmed again by smoke test S1–S3 after #661) — report it. **4** = **block release and investigate**.

Return to the Captain: baseline.txt, flags.txt, model.txt (+ exit codes) and any anomaly. Then **wait** for approval of the first merge.

## 4. Merge and deployment sequence (Captain approves each step separately)
For each step the Mac/Captain performs the merge (merge commit) and gives the VM agent the **expected merge-commit SHA**. The VM agent then only observes:
1. Wait for auto-deploy (≤ ~5–10 min). Run `./verify_deploy.sh <merge-sha> 300`.
2. Run the step's smoke tests (§5) as the service user (e.g. `sudo -u "$(systemctl show -p User --value intelligence-scheduler.service)"`) from `/opt/starship-endeavour`. If credentials are not found, report it; do not export secrets into the shell.
3. Report results and **stop**. Do not advance. The next merge needs a new approval.

`verify_deploy.sh` passes when: deployed commit == expected; tracked tree clean; all ten services `active/running`; **no service restarts again or leaves active/running during the settle window** (no crash loop — it does *not* require restart counts to equal pre-deployment values); no auto-deploy warnings ("needs a human", abort); flags scan clean; local-model diagnostic not exit 4.

## 5. Non-sending smoke tests (in-memory only; no Telegram, email, scheduler job or heartbeat)
Copy `smoke_privacy_flags.py` and `smoke_build_briefs.py` to the VM and run from the repo root:
```
cd /opt/starship-endeavour
python3 /tmp/release-handover/smoke_privacy_flags.py   # needs #661 code: default-deny, personal text blocked, only local model permitted, all new flags default OFF
python3 /tmp/release-handover/smoke_build_briefs.py    # builds Morning/Weekly/Comms text in memory, prints sizes/booleans only
```
- After **#661**: `smoke_privacy_flags.py` must print S1–S3 PASS (S4/S5 print SKIPPED until #658/#662 code is deployed — expected). `smoke_build_briefs.py` must pass.
- After **#658**: `smoke_build_briefs.py` passes; Comms still the legacy shape (S7 quiet or legacy).
- After **#662**: both scripts pass in full (S1–S7). `smoke_build_briefs.py` runs weekly generation, which may call the existing non-personal summarisation models (in-memory, may use tokens). It never sends.
Do not trigger real briefs, `run_job`, or `/comms`; they record heartbeats/memory or deliver.

## 6. Stop conditions (stop, take no corrective action, report)
Any variable in §2 present; local-model exit 4; deployed commit ≠ expected after ~15 min; tracked tree dirty; any of the ten services not active/running or restarting during the settle window; auto-deploy warnings; smoke test failure; any unexpected send, migration, retention action, snapshot file or DB write in logs; any personal-health content appearing in a log or outbound path.

## 7. Recovery (all require Captain approval before acting)
- **#658 / #662**: the Mac prepares a revert PR; Captain approves; merge; auto-deploy restores (flags are off, so low risk). The VM agent does not revert.
- **#661**: **never revert** (re-opens the privacy gap). If the local model is unavailable: personal text already falls back to deterministic output. Diagnose read-only; any restart/pull of the local model or service needs approval. **Never set `HEALTH_LLM_EXTERNAL_ALLOWED`.**
- **Crash loop after a merge**: capture `journalctl -u <unit> -n 80 --no-pager` (screen for secrets/personal content), report, hold. Captain decides revert vs fix; the fix is made on the Mac.

## 8. Actions requiring Captain approval (exhaustive)
1. Accept the preflight results (§3).
2. Mark #661 ready and merge it (merge commit) — then verify (§4).
3. Merge #658 after #661 verification — then verify.
4. Merge #662 after #658 verification — then verify.
5. Any service restart, config/env change, local-model action, revert or rollback.
6. (Later, separately) activating any brief, editorial or capacity flag.
