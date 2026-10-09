# USS-TJR-MSN-0412 Stream 1: Save VM-only code (knowledge record)

Source plan: `knowledge/missions/VM-OPTIMISE-ZERO-COST-PLAN-20261009.md` (PR #354).
Date: 2026-10-09. Labels: MEASURED / INFERENCE / TO BE VERIFIED.

## What changed

| Change | Evidence |
|---|---|
| Minted USS-TJR-MSN-0412 from the shared checkout's local counter (MSN 411 -> 412). The file stays uncommitted. | MEASURED: `.id-counters.json` `{"DEC":123,"MSN":412}` |
| Created worktree `/opt/wt-MSN-0412-s1`, branch `msn-0412-s1-code-to-github`, from `origin/main` 52e955489. | MEASURED: `git worktree list` |
| Bundled all local branches: `/root/starship-branches-20261009.bundle` (23 MB, mode 600, 159 refs). | MEASURED: `git bundle verify` = "complete history" |
| Pushed `USS-TJR-MSN-0403-tev1-suppression-audit` (tip a30000c26). No PR. | MEASURED: local and remote SHA equal |
| Pushed `claude/wire-deepeval-quality-scoring-20260912` (tip ab9c93bd3, one doc commit). No PR. | MEASURED: local and remote SHA equal |

Distinct commits on no remote: 66 at start, 63 after the two pushes (MEASURED).

## Scans

- gitleaks v8.30.1, `--redact`, over `origin/main..<branch>` for the 36 branches with new commits: 70 commits scanned, 0 findings.
- gitleaks over the 59 existing modified and untracked files: 0 findings.
- Scope limit: secrets only (default ruleset). Content was not reviewed for personal or sensitive material.

## Decisions (Captain)

- Bundle-only: `claude/hq-evolution-opportunity-dedup-staleness-20260912` (#108), `claude/arize-phoenix-tracing-live-20260912` (#109), `fix/pin-arize-phoenix` (#177), `self-improvement`, the eight branches whose patches are already on main, and all `mistral/*` branches.
- #177 reasoning: the commit's own change is `typing_extensions==4.15.0 -> >=4.16.0`; main pins `==4.16.0`. The rest of the diff is branch-base staleness (563 commits behind main).
- `.id-counters.json` is not committed from the worktree. `deploy/sync-self-improvement-state.sh` owns committing it. origin/main has no MSN id above 0395, so max(local, main) = MSN 412, DEC 123 and the local file is already correct.
- None of the 65 uncommitted changes are committed. `Missions/Engineering-Handoffs/` and `.id-counters.json` are added to the Stream 2 backup list.

## Skipped and why

- `self-improvement` (11 commits on no remote): live service branch; pushing from a second place could race the service. Protected by the bundle.
- Plan acceptance wording "No local-only commits remain" is not met by design; 63 commits stay bundle-only.

## Findings for follow-up

1. `sync-self-improvement-state.service` has committed nothing since 2026-09-22 (last `auto-sync tracked state files` commit 4d50b91e8). Every logged run since 2026-10-06 (135) ended "dirty tree includes non-allowlisted files - leaving for a human", exit 0, so no alert fired. Blockers: six deleted handoff files, `mission_dispatch_log.jsonl` (not in `STATE_FILES`), and `mission-index.txt` (since 2026-10-09). MEASURED.
2. `auto-deploy.sh` is not blocked by these paths; its `DIRTY_CHECK_EXCLUDES` already tolerates them. The cost is that state never reaches main (main's `.id-counters.json` is stale at 395/4). MEASURED from script text.
3. No job commits `Missions/Engineering-Handoffs/`. `mission_dispatch.py` and `batch_coding.py` contain no git add/commit/push. Both services run successfully. TO BE VERIFIED beyond the files grepped.
4. `mistral/*` branches hold Mistral-generated code patches made by `core/engineering/providers/github_pr.py`. None of the 57 local `mistral/*` branches exist on GitHub. TO BE VERIFIED why the push/draft-PR step is not landing.
5. The GitHub repo is public (unauthenticated API returns `private: false`). Anything pushed is world-readable.
6. Why `self-improvement` leaves 11 commits unpushed (read-only follow-up after Stream 2).
7. Sync-script fix, variant B (`mission_dispatch_log.jsonl` tolerated, not committed): draft PR #356, branch `msn-0412-s1b-sync-unblock`. Dry-run against a scratch clone: the original script declines; the new one commits only the 4 STATE_FILES, leaves the other 8 dirty paths alone, and still refuses an unrelated dirty tracked file. Not installed on the VM; waits for merge and auto-deploy.
8. Sync timer cadence: 135 runs logged since 2026-10-06 against about 1,580 expected at a 3-minute cadence. TO BE VERIFIED whether the timer was off for part of the period.

## Follow-ups recorded (not acted on)

- `self-improvement` branch: 11 commits on no remote; read-only investigation after Stream 2.
- `github_pr.py`: the `mistral/*` branches never reach GitHub (0 of 57 present).
- No job commits `Missions/Engineering-Handoffs/`.
- Sync timer logged-run shortfall (item 8).
- Plan acceptance wording amended (docs PR, 2026-10-10): "No VM-only commits remain without an off-box copy (GitHub, or the verified bundle in the restic backup)."

## Open Captain decision

- Public vs private repo: not yet chosen. Until chosen, nothing describing a live vulnerability, host/IP address or personal/health detail goes into any commit or PR.

## Update 2026-10-10

- Finding 1 (sync job silent since 2026-09-22) is resolved: the sync fix from PR #356 is live and the job committed state files again on 2026-10-10.
- The same job then caused a divergence while auto-deploy was wedged; see "Follow-ups (recorded 2026-10-10)" in the plan file and PR #361 for the prevention fix.
