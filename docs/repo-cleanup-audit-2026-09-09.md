# Repository Cleanup Audit — 2026-09-09

Non-destructive audit of `timjardenross/TJRHQ`: branches, remote-tracking refs, commit
history, and pull requests. No branches, refs, or history were modified to produce this
report — every finding below was derived from read-only `git`/GitHub API queries.

## 1. Repository snapshot

- **Default branch:** `main` (protected)
- **Total branches (incl. `main`):** 64 — all remote-only; only `main` and this audit
  branch exist locally
- **`.git` size:** 20 MB — small; **no history rewrite is warranted on size grounds**
- **Merge strategy in use:** squash-merge for most feature PRs (main commits carry a
  trailing `(#NN)`), plus some regular merge commits (`Merge pull request #NN from ...`)
- **Total PRs:** 96 — 89 merged, 3 closed-unmerged, 4 open (all opened 2026-09-08/09,
  none stale)
- **Every PR targets `main`** — no stray base branches

## 2. Branch cleanup

### 2a. Safe to delete now (35) — merged, and the branch tip is a git ancestor of `main`

Deleting these removes zero unique work; `main` already contains every commit.

```
claude/batch-coding-pr-error-surfacing
claude/briefs-uplift-canonical-ylf7gi
claude/captains-chair-lifeos-redesign-syd9ev
claude/dazzling-carson-36c6d9
claude/engineering-review-one-click-link
claude/fix-mission-error-object-string
claude/fix-workbench-registry-drift
claude/hq-evolution-ai-implementation-dispatch
claude/hq-evolution-capability-9iya96
claude/hq-evolution-create-mission-notice
claude/hq-evolution-dedup-reconsideration-fix
claude/hq-evolution-evidence-strength-backfill
claude/hq-evolution-mark-implemented-ui
claude/hq-evolution-remediation-bridge-fix
claude/hq-evolution-remediation-visibility
claude/hq-evolution-stale-outcome-counts-fix
claude/hq-status-workbench-4mb0o0
claude/hq-v1-integration-qa
claude/hqn-status-investigation-7aokis
claude/human-execution-loop-9dl3m3
claude/human-systems-report-9xzjf8
claude/investigate-failures-c902sf
claude/lifeos-wall-tablet-components-av68zt
claude/mission-dispatch-retry-on-failure
claude/missions-workbench-review-40ae8p   # backed PRs #85,88,89,90,92,93 — all merged
claude/resilience-signal-details-q820pn
claude/reverse-concept-research-en3o9w
claude/self-improvement-collector-policy-fixes
claude/supabase-egress-bandwidth-iwo07v
claude/tjr-hq-settings-tab-g2wrko          # backed PRs #32,#33 — both merged
claude/trends-llm-summary-improve-bdprfv
claude/vibrant-agnesi-19be81
mistral/ENG-HANDOFF-SD-FND-001-20260906210248
mistral/ENG-HANDOFF-SD-FND-003-20260906210543
mistral/ENG-HANDOFF-USS-TJR-MSN-1788771576677-20260907091818
```

### 2b. Safe to delete now (21) — squash-merged into `main`, confirmed via PR API + spot-checked commit match

`git branch -r --no-merged` does **not** list these as merged, because their PRs were
squash-merged (main carries a new commit with message `<title> (#NN)`, not the original
branch commits — this is expected and correct GitHub behavior, not a sign of lost work).
Confirmed via the GitHub API (`merged_at` set for every PR below) and spot-checked two
of them by grepping their commit subject on `main` (both found, e.g. `claude/ready-room-error-j0wl9d` → `bffb28e3 ... Ready Room (#43)` on `main`).

```
claude/advisory-workbench-redesign-5eowy6        (PR #34)
claude/agent-status-workbench-ui-usage-y7hx0p    (PR #78)
claude/artifact-viewer-surface-upstream-errors   (PR #77)
claude/create-mission-for-approved-opportunities (PR #75)
claude/ecstatic-haslett-918e17                   (PR #95)
claude/engineering-handoff-progress              (PR #62)
claude/fix-homesessions-midnight-flake           (PR #60)
claude/fix-missions-rls-authenticated            (PR #70)
claude/fix-model-router-latency-analysis         (PR #74)
claude/fix-revs-service-name                     (PR #65)
claude/glm-5-3-mistral-eval-a0o8gk               (PR #87)
claude/hq-evolution-fix-false-pr-opened-text     (PR #59)
claude/interrupt-now-visibility-c7klhd           (PR #82)
claude/lifeos-hub-notification-clicks-xnz8oo     (PR #61)
claude/llm-cost-governance-token-capture         (PR #79)
claude/ready-room-error-j0wl9d                   (PR #43)
claude/restart-self-improvement-dashboard-on-deploy (PR #80)
claude/state-validation-exclude-vendored-dirs    (PR #81)
claude/surface-create-mission-error-detail       (PR #67)
claude/vm-auto-deploy                            (PR #63)
mistral/ENG-HANDOFF-SD-FND-002-20260907210537    (PR #76)
```

### 2c. Safe to delete now (1) — closed & unmerged, self-labeled disposable

```
mistral/diagnostic-test-delete-me-2   # PR #55: "Diagnostic probe 2 (safe to close/delete)"
```

### 2d. Probably safe, but verify first (2) — very stale, large divergence from `main`

```
claude/content-workbench-e2e            (PRs #12, #24 — both merged)
claude/content-workbench-portfolio-tab  (PRs #16, #23 — both merged)
```

Both are ~1 month old (last commit 2026-08-11) and diverge from current `main` by
~1,290 unique commits in each direction — far more than any other branch. This is
consistent with these being pre-refactor snapshots that predate a large `lcars-portal`
rework, and I confirmed the Content Workbench code they introduced is present on `main`
today (`lcars-portal/src/app/api/content-workbench/...` exists). Recommend a final
`git diff main...<branch> --stat` glance (or just trusting the GitHub "Merged" badge on
#12/#16/#23/#24) before deleting — flagged separately rather than bucketed with 2a/2b
purely because the divergence size is an outlier worth a human's eyes.

### 2e. Must keep — open PRs in progress (4)

```
claude/eager-golick-eb8e4d                          → PR #96 (open, ready, non-draft)
claude/ui-review-reorganize-69wjp5                  → PR #86 (open, draft)
mistral/ENG-HANDOFF-USS-TJR-MSN-1788844167855-...   → PR #83 (open, draft, Mistral auto-handoff)
mistral/ENG-HANDOFF-USS-TJR-MSN-1788844175339-...   → PR #84 (open, draft, Mistral auto-handoff)
```

None are stale (all created 2026-09-08/09). Do not delete until each PR is merged or
explicitly closed.

### 2f. Local / remote-tracking branches

Only `main` and this audit branch exist as local branches; everything else is a
remote-tracking ref (`origin/...`). There are **no stale local branches** and no
orphaned remote-tracking refs beyond the branches already categorized above — a
`git fetch --prune` (already run for this audit) keeps local refs in sync with what
actually exists on `origin`.

## 3. Commit / push cleanup

- **No accidental large or secret commits found.** The 15 largest blobs in history are
  generated artifacts (`**/graphify-out/graph.json`, a `USS-TJR-Control/logs/health-monitor.log`
  at various sizes, a PDF, `package-lock.json`s) — nothing sensitive, and the repo is
  only 20 MB total, so **history rewriting (filter-repo/BFG) is not justified**.
- `logs/` and `*.log` are already gitignored, and `health-monitor.log` is **not**
  tracked in current `main` — it only exists in old history, which is harmless to leave
  alone.
- `**/graphify-out/graph.json` **is** currently tracked on `main` (13 files, largest
  5.3 MB) and looks like a generated/derived artifact rather than source. Recommend
  adding `**/graphify-out/` to `.gitignore` and removing the tracked copies in a normal
  follow-up commit (not a history rewrite — just delete-and-commit going forward) if
  these are indeed regenerable build output. This is a forward-looking hygiene item, not
  an urgent cleanup.
- No force-pushes, no rewritten public history, no evidence of leaked credentials in the
  scanned blob list.

## 4. Pull request cleanup

- **Open (4):** #83, #84 (Mistral draft handoffs, review-only), #86 (draft UI fix), #96
  (ready-for-review dead-code removal). All fresh (≤1 day old) — no action needed beyond
  normal review.
- **Closed & unmerged (3):** #6, #17 (branches already deleted — nothing to do), #55
  (branch still present, see 2c above — safe to delete).
- **Branches reused across multiple PRs** (not duplicates, just the same branch pushed
  to repeatedly before each merge — harmless, but worth noting so future stacked work
  uses a fresh branch per topic where practical):
  - `claude/missions-workbench-review-40ae8p` → PRs #85, #88, #89, #90, #92, #93
  - `claude/tjr-hq-settings-tab-g2wrko` → PRs #32, #33
  - `claude/captains-chair-lifeos-redesign-syd9ev` → PRs #40, #46
  - `claude/content-workbench-e2e` → PRs #12, #24
  - `claude/content-workbench-portfolio-tab` → PRs #16, #23
  - (Older, already-branch-deleted cases: `claude/core-event-bus-degradation-s99fk8` →
    #2/#5/#7, `claude/content-workbench-modal-ai-review` → #14/#15 — no action needed.)
- **No PRs target a non-`main` base**, so no rebase-target cleanup is needed.
- **Recommendation:** enable "Automatically delete head branches" in
  **Settings → General → Pull Requests** — most of the old (July/August) merged PRs
  already have no leftover branch, suggesting this was on at some point or branches were
  swept manually; the Sept 6–9 backlog above suggests it's currently off or lagging.

## 5. Exact commands

**Re-verify a branch is safe before deleting (do this per branch, or spot-check a sample):**
```bash
git fetch origin --prune
git branch -r --merged origin/main | grep <branch>        # confirms literal ancestor (bucket 2a)
git log origin/main --oneline --grep="<PR title fragment>" -i   # confirms squash-merge landed (bucket 2b)
gh pr view <PR-number> --repo timjardenross/TJRHQ --json state,merged,mergeCommit
```

**Delete a remote branch (reversible — GitHub keeps the commit reachable via the PR's
`merged_at` SHA and via any fork/reflog for ~90 days, but treat this as effectively
permanent for planning purposes):**
```bash
git push origin --delete <branch-name>
```

**Bulk-delete every branch in bucket 2a + 2b + 2c in one pass** (review the list first —
this is the one destructive step in this whole audit):
```bash
for b in \
  claude/batch-coding-pr-error-surfacing claude/briefs-uplift-canonical-ylf7gi \
  claude/captains-chair-lifeos-redesign-syd9ev claude/dazzling-carson-36c6d9 \
  claude/engineering-review-one-click-link claude/fix-mission-error-object-string \
  claude/fix-workbench-registry-drift claude/hq-evolution-ai-implementation-dispatch \
  claude/hq-evolution-capability-9iya96 claude/hq-evolution-create-mission-notice \
  claude/hq-evolution-dedup-reconsideration-fix claude/hq-evolution-evidence-strength-backfill \
  claude/hq-evolution-mark-implemented-ui claude/hq-evolution-remediation-bridge-fix \
  claude/hq-evolution-remediation-visibility claude/hq-evolution-stale-outcome-counts-fix \
  claude/hq-status-workbench-4mb0o0 claude/hq-v1-integration-qa claude/hqn-status-investigation-7aokis \
  claude/human-execution-loop-9dl3m3 claude/human-systems-report-9xzjf8 claude/investigate-failures-c902sf \
  claude/lifeos-wall-tablet-components-av68zt claude/mission-dispatch-retry-on-failure \
  claude/missions-workbench-review-40ae8p claude/resilience-signal-details-q820pn \
  claude/reverse-concept-research-en3o9w claude/self-improvement-collector-policy-fixes \
  claude/supabase-egress-bandwidth-iwo07v claude/tjr-hq-settings-tab-g2wrko \
  claude/trends-llm-summary-improve-bdprfv claude/vibrant-agnesi-19be81 \
  mistral/ENG-HANDOFF-SD-FND-001-20260906210248 mistral/ENG-HANDOFF-SD-FND-003-20260906210543 \
  mistral/ENG-HANDOFF-USS-TJR-MSN-1788771576677-20260907091818 \
  claude/advisory-workbench-redesign-5eowy6 claude/agent-status-workbench-ui-usage-y7hx0p \
  claude/artifact-viewer-surface-upstream-errors claude/create-mission-for-approved-opportunities \
  claude/ecstatic-haslett-918e17 claude/engineering-handoff-progress claude/fix-homesessions-midnight-flake \
  claude/fix-missions-rls-authenticated claude/fix-model-router-latency-analysis claude/fix-revs-service-name \
  claude/glm-5-3-mistral-eval-a0o8gk claude/hq-evolution-fix-false-pr-opened-text \
  claude/interrupt-now-visibility-c7klhd claude/lifeos-hub-notification-clicks-xnz8oo \
  claude/llm-cost-governance-token-capture claude/ready-room-error-j0wl9d \
  claude/restart-self-improvement-dashboard-on-deploy claude/state-validation-exclude-vendored-dirs \
  claude/surface-create-mission-error-detail claude/vm-auto-deploy \
  mistral/ENG-HANDOFF-SD-FND-002-20260907210537 \
  mistral/diagnostic-test-delete-me-2 \
; do
  git push origin --delete "$b"
done
```

**After manual verification, delete bucket 2d separately:**
```bash
git push origin --delete claude/content-workbench-e2e
git push origin --delete claude/content-workbench-portfolio-tab
```

**Do NOT run** (explicitly out of scope / risky — flagged, not recommended):
```bash
git push origin --delete claude/eager-golick-eb8e4d                                       # PR #96 open
git push origin --delete claude/ui-review-reorganize-69wjp5                               # PR #86 open
git push origin --delete mistral/ENG-HANDOFF-USS-TJR-MSN-1788844167855-20260908051851     # PR #83 open
git push origin --delete mistral/ENG-HANDOFF-USS-TJR-MSN-1788844175339-20260908052135     # PR #84 open
# No force-push, reset --hard, or history rewrite is recommended anywhere in this audit.
```

## 6. Final verification checklist

- [ ] `git fetch origin --prune` run immediately before deleting anything (avoid acting
      on stale branch state)
- [ ] For each branch in 2a: `git branch -r --merged origin/main` still lists it
- [ ] For each branch in 2b: its PR shows `"merged": true` via `gh pr view <n> --json merged`
      (or the green "Merged" badge in the GitHub UI)
- [ ] Branches in 2e (open PRs #83/#84/#86/#96) are **not** in the deletion batch
- [ ] Bucket 2d (`content-workbench-e2e`, `content-workbench-portfolio-tab`) diffed or
      spot-checked before deleting
- [ ] After deletion, `git fetch origin --prune && git branch -r | wc -l` shows the
      expected reduced count (64 → ~7: `main` + the 4 open-PR branches + any newly
      opened since)
- [ ] Re-run `mcp`/`gh pr list --state open` and confirm the 4 open PRs are still intact
      and their branches still resolve
- [ ] No local branches were touched (only `main` and the audit branch existed locally
      to begin with)
- [ ] No commit was amended, rebased, or force-pushed anywhere in this repo as part of
      this audit
