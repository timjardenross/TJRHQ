# Knowledge Record — CI Performance & Merge Latency Optimisation, 2026-09-19

| Field | Value |
|---|---|
| Title | Split serial `pre-commit` job into parallel gates, fixed detect-secrets' own runtime cause, added fail-closed merge gate |
| Date | 2026-09-19 |
| Priority | P1 |
| Branch/PR | `ci-performance-merge-latency`, PR #264 |
| Isolation | Mission 3 / Mission 4 branches, worktrees, and PRs were never read or touched. Branch protection was NOT changed — deferred until Mission 3 merges and Captain approves. |

## BEFORE

**Workflow architecture**: 3 workflows (`python-ci.yml`, `lcars-portal-ci.yml`,
`scorecard.yml`). Concurrency-cancellation groups and Scorecard's push-trigger
removal were already fixed by a same-day prior change — verified present, not
re-touched here.

**Critical path**: the `pre-commit` job ran gitleaks → detect-secrets → bandit →
ruff-check as **serial steps in one job**. Measured live on an uncontaminated PR
run (35421419775, mission3's own push — read-only observation):

| Step | Duration |
|---|---|
| gitleaks (blocking) | 33s |
| detect-secrets (advisory, `continue-on-error`) | **23m24s** |
| bandit (blocking) | 28s |
| ruff-check (blocking) | 7s |
| **Total job** | **24m42s** |

Every other job in the workflow (test matrix, vulture, pip-audit, semgrep,
promptfoo, actionlint, changes) finished within 4 minutes. The advisory
detect-secrets step — which gates nothing — was the entire reason two real
blocking gates (bandit, ruff-check) and the job itself took 20+ minutes.

**Typical merge latency**: matched the mission's own reported 20-25 minutes
almost exactly (24m42s measured).

## ROOT CAUSES (ranked by impact)

1. **Serial job structure (dominant, ~95% of the bottleneck)**: an advisory,
   non-blocking check sat as a step *ahead of* two real blocking checks in the
   same job, so nothing behind it could finish until it did.

2. **detect-secrets' own runtime cause (newly diagnosed, not previously found)**:
   `.pre-commit-config.yaml`'s `exclude:` regex on the detect-secrets hook
   (added 2026-09-15 specifically to skip the 563MB `data/self-improvement/
   runs/*/evidence.json` tree) only applies when detect-secrets runs *through*
   `pre-commit run` — pre-commit does the file-list filtering, the tool has no
   config-file exclude of its own. This CI step calls the bare `detect-secrets
   scan` CLI directly (a deliberate, documented workaround for a batching bug
   in `pre-commit run --all-files` on this hook), so the 2026-09-15 exclude was
   silently not applying to CI at all — it was re-scanning the full 611-file/
   563MB tree every single run. Verified live: `git ls-files data/
   self-improvement/runs | wc -l` = 611, `du -ch` = 563M. Also found no
   `--no-verify`/`-n` flag, meaning every candidate finding triggered a live
   network verification call — unnecessary latency for a scan that only cares
   whether a finding is new vs. already-baselined.

3. **Branch-protection governance gap (documented, not a latency cause)**:
   `gh api repos/.../branches/main/protection` shows `required_status_checks.
   contexts: ["check"]` — only the LCARS Portal CI `check` job (~99s) is
   actually GitHub-enforced on `main`. No repository rulesets exist either.
   This means the historical ~20-25 minute "PR blocked" experience is a
   **team-practice trust gate**, not a **GitHub-enforced merge gate** — see
   "Two different metrics" below.

4. **Dependabot fan-out (external, Phase B, not attributed to the primary
   fix)**: a burst of ~12 Dependabot PRs fired within the same ~20s window
   during this mission's own discovery phase, each spawning a full Python CI
   run that took 45-65min wall clock from pure runner-queue congestion, not
   workflow logic. `.github/dependabot.yml` has 9+ pip ecosystem entries all on
   `interval: weekly` with no stagger or `groups:` consolidation. Real problem,
   deliberately kept separate — the clean (non-storm) run used for the primary
   diagnosis was unconfounded by this.

## CHANGES

In `.github/workflows/python-ci.yml`:

1. Replaced the single `pre-commit` job with 4 parallel jobs, each restoring
   the same `~/.cache/pre-commit` cache key (no extra install cost, just
   parallel restores instead of one serial build):
   - `precommit-secrets` (gitleaks, blocking) — same command as before
   - `precommit-security` (bandit `-ll`, blocking) — same command as before
   - `precommit-lint` (ruff-check, blocking) — same command as before
   - `detect-secrets-advisory` (advisory, `continue-on-error: true`) — same
     tool/baseline/`check_new_secrets.py` logic, now also passing
     `--exclude-files` (mirroring the pre-commit-level exclude) and
     `--no-verify`

2. Added `merge-gate`, a stable, non-matrix-dependent required-check context
   (needs `[changes, actionlint, precommit-secrets, precommit-security,
   precommit-lint, test]`, `if: always()`). Fails closed:
   - Every unconditional required job must be `success` — `failure`,
     `cancelled`, or `skipped` all fail the gate.
   - The conditional `test` job (matrix-driven, path-aware) accepts `success`
     unconditionally, and accepts `skipped` **only when proven legitimate** —
     the gate re-checks `changes`' own matrix output and confirms it was
     actually empty, rather than trusting the `skipped` status string alone.
     An unexplained skip (matrix non-empty but test didn't run) fails the
     gate.
   - Advisory jobs (`detect-secrets-advisory`, `vulture`, `pip-audit`,
     `semgrep`, `promptfoo`) are deliberately excluded from `needs` — they
     never gated the merge decision before this change and still don't.

**Not changed**: branch protection (deferred — see "Deferred" below),
`scorecard.yml`, concurrency groups, the 3 blocking hooks' actual rules
(same commands/args, different job placement only), detect-secrets'
plugins/baseline/new-vs-baselined logic (only its file-scope and
verification-call behavior changed).

## AFTER

Two live PR runs on the new architecture (PR #264), both natural samples (no
manufactured cache invalidation):

| Run | detect-secrets | precommit-secrets/security/lint | test matrix | merge-gate green at |
|---|---|---|---|---|
| 1 (35422873933) | 70s | 35s / 39s / 21s (parallel) | 2m05s | **T+2m14s** |
| 2 (35423575400, warm) | 2m05s | 39s / 39s / 15s (parallel) | 1m40s | **T+2m00s** |

Both comfortably beat the <10min target and the 5-8min stretch target —
observed range ~2 minutes end-to-end. detect-secrets itself dropped from
23m24s to ~1-2min (the exclude fix eliminated the root cause of its slowness,
not just its position in the critical path).

**Merge-gate fail-closed semantics — all 4 required scenarios proven**:

| Scenario | Method | Result |
|---|---|---|
| Blocking job success | Live run 35422873933/35423575400 | Gate: success |
| Blocking job failure | Live run 35423084334 (deliberate ruff violation, reverted immediately after) | Gate: failure |
| Legitimate conditional skip | Local simulation of the exact gate script (a genuinely empty-matrix live case wasn't reachable within this PR — see "Deferred", item 2) | Gate: success |
| Unexpected skip (non-empty matrix but skipped) | Local simulation of the exact gate script | Gate: failure |

No real secrets were injected to test the secrets gate — orchestration
semantics only, per the Captain's explicit instruction.

## SECURITY / QUALITY — coverage preserved

- gitleaks, bandit (`-ll`), ruff-check: identical commands, identical args,
  identical pass/fail rules. Only job placement changed (serial steps →
  parallel jobs).
- detect-secrets: identical plugins, identical baseline, identical
  new-vs-baselined logic in `tools/check_new_secrets.py`. `--exclude-files`
  restores the scope the 2026-09-15 exclude was already supposed to have
  (removing already-deliberately-excluded generated evidence dumps, not
  narrowing real coverage). `--no-verify` skips a live network
  double-check of candidate findings' "is this key still active" status —
  detection itself (regex/entropy matching against the baseline) is
  unaffected.
- No branch-protection change — the pre-existing enforcement level (only
  `check`) is neither weakened nor strengthened by this PR.

## TWO DIFFERENT METRICS (Captain's explicit framing — must not be conflated)

- **GitHub-enforced mergeability**: what branch protection actually requires
  today. Currently just `check` (LCARS, ~99s). Unchanged by this mission.
- **TJR HQ trustworthy merge readiness**: the full set of controls the team
  actually waits on before trusting a merge — test matrix + pre-commit gates
  + LCARS check. This mission's work targets *this* metric's speed (24m42s →
  ~2min). Closing the gap between the two — making trustworthy-readiness
  GitHub-enforced via the new `merge-gate` context — is a separate, deferred
  step requiring Captain approval after Mission 3 merges.

## PATH-AWARE MATRIX (as observed, not redesigned this mission)

| Change type | `test` matrix | Blocking pre-commit jobs | Advisory jobs |
|---|---|---|---|
| Python (`core/`, `platform-runtime/`, etc.) | Runs relevant entries | Always run (repo-wide) | Always run (repo-wide) |
| Frontend (`lcars-portal/`) | Empty (no Python match) — LCARS workflow's own jobs run instead | Always run | Always run |
| Mixed | Runs relevant entries | Always run | Always run |
| Docs-only (root-level, no filter match) | **Should be empty — see Deferred item 2 for a caveat found while testing this** | Always run | Always run |
| Migration/core-security | Runs `core` entry | Always run | Always run |

Pre-commit's 3 blocking hooks and the 5 advisory jobs are not path-filtered at
all (always run repo-wide) — unchanged by this mission, and not a latency
problem at their current ~1-2min-each cost, so left alone per the "don't
optimise a 20s job while a real blocker remains" principle.

## DEFERRED

1. **Branch-protection change** (add `Python CI / merge-gate` to required
   contexts): explicitly deferred until Mission 3 has merged and the Captain
   approves. This mission does not schedule or assume that approval.

2. **`changes` job's `core` path filter appears to over-match**: while testing
   the legitimate-skip scenario, `.github/workflows/python-ci.yml` (a
   workflow-file-only change, no `core/**` files touched) was observed
   matching the `core` filter (`dorny/paths-filter@v3` logged `.github/
   workflows/python-ci.yml [modified]` under "Filter core = true"). This is
   pre-existing `changes`-job behavior, unrelated to this mission's edits, and
   not a latency problem (it just runs one extra ~2min test-matrix entry) —
   flagged for a future path-filter-correctness pass, not fixed here. It's
   also why the merge-gate's legitimate-skip path was proven via local script
   simulation rather than a live empty-matrix run within this PR.

3. **Dependabot fan-out staggering** ("Phase B" per the mission plan): add
   `schedule.day`/`time` spread and `groups:` consolidation to
   `.github/dependabot.yml`. Real, measured problem (12 simultaneous PRs, each
   45-65min wall clock from runner congestion) but deliberately not bundled
   into this PR's attribution.

4. **Why detect-secrets' underlying regex/entropy scan is itself somewhat
   slow even after the exclude fix** (~1-2min for 3,294 tracked files):
   not investigated further — the bounded investigation found the dominant,
   obvious, safe cause (563MB reintroduced by the CLI-vs-pre-commit exclude
   gap) and fixing it already resolved the merge-latency KPI. Remaining
   ~1-2min is well within budget and not chased further.

## TECHNICAL DEBT

- The `changes` job's `core` filter's apparent over-matching (item 2 above).
- detect-secrets/CI-environment flakiness on 2 pre-existing IBM Cloud IAM Key
  fixture findings occasionally failing to re-detect (tracked pre-existing in
  #189, not touched by this mission).
- Dependabot fan-out (item 3 above).
- The real gap behind 16/18 cited `ADR-NNN` numbers having no backing file
  (pre-existing, unrelated to this mission, noted here only because branch-
  protection/governance was touched in discovery).

## CONFIDENCE

High. Every latency claim in this record is a live-measured number from real
GitHub Actions runs (35421419775 before, 35422873933 and 35423575400 after),
not an estimate. All 4 merge-gate fail-closed scenarios were proven (2 live,
2 via exact-script local simulation, documented above with the reason the
other 2 couldn't be reached live within this PR). Security/quality coverage
was verified command-by-command against the pre-change job, not assumed.
