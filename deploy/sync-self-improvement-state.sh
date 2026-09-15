#!/bin/bash
# Keeps 4 known, mechanically-rewritten tracked state files — plus new
# data/self-improvement/runs/ directories (see below) — in sync with
# origin/main so neither ever blocks auto-deploy.sh's dirty-tree guard.
#
# Root cause (2026-09-15): the self-improvement system (hq-evolution /
# opportunity_store / id_registry) writes to these tracked files on every
# cycle. auto-deploy.sh correctly refuses to pull over ANY dirty tracked
# file - that's a deliberate safety rule protecting real manual edits -
# but these 4 paths are never a manual edit, so they were permanently
# tripping that guard and firing repeated OnFailure Telegram alerts.
#
# This is a narrow, explicit allowlist - NOT a general "auto-commit
# whatever's dirty" job. If anything else is dirty alongside these files,
# this script does nothing and leaves it for a human, same as auto-deploy.sh
# would.
#
# 2026-09-15 second adversarial pass: data/self-improvement/runs/*/ (a
# NEW directory per cycle, not a dirty tracked file) was never covered by
# the check above at all — untracked paths don't trip auto-deploy.sh's
# tracked-file dirty check, so they didn't block deploys, but they also
# never got committed. 451 of them (494MB) piled up over ~2 days despite
# a docs claim that they'd been "reconciled by committing" — that commit
# was a one-time catch-up with nothing keeping pace with new cycles.
# Extended this script to also stage and commit brand-new run
# directories every time it runs, so the backlog can't re-form. Existing
# tracked files under runs/ (there shouldn't be any — each run directory
# is written once, never modified after) still fall through to the
# tracked-file check below and abort for a human, same as any other
# unexpected dirty state.
set -euo pipefail

REPO_ROOT="${SYNC_STATE_REPO_ROOT:-/opt/starship-endeavour}"
BRANCH="${SYNC_STATE_BRANCH:-main}"
LOG_PREFIX="[sync-self-improvement-state]"
RUNS_DIR="data/self-improvement/runs"

STATE_FILES=(
  ".id-counters.json"
  "data/self-improvement/review/evolution_summary.json"
  "data/self-improvement/review/finding_staleness.jsonl"
  "data/self-improvement/review/opportunity_id_counter.txt"
)

cd "$REPO_ROOT"

dirty_tracked="$(git status --porcelain --untracked-files=no)"
new_run_dirs="$(git status --porcelain --untracked-files=all -- "$RUNS_DIR" | grep '^??' || true)"

if [ -z "$dirty_tracked" ] && [ -z "$new_run_dirs" ]; then
  echo "$LOG_PREFIX nothing dirty and no new run directories - nothing to do."
  exit 0
fi

only_allowlisted=true
while IFS= read -r line; do
  [ -z "$line" ] && continue
  path="${line:3}"
  match=false
  for allowed in "${STATE_FILES[@]}"; do
    if [ "$path" = "$allowed" ]; then
      match=true
      break
    fi
  done
  if [ "$match" = false ]; then
    only_allowlisted=false
    break
  fi
done <<< "$dirty_tracked"

if [ "$only_allowlisted" = false ]; then
  echo "$LOG_PREFIX dirty tree includes non-allowlisted files - leaving for a human (same policy as auto-deploy.sh)."
  echo "$dirty_tracked"
  exit 0
fi

# 2026-09-15 second adversarial pass: this script had no check that
# $REPO_ROOT was actually on $BRANCH before committing - the exact
# "hq-evolution commits to whatever branch is checked out" bug class
# already fixed in auto_remediation.py (see its
# current_branch != self.expected_branch guard) but missed here because
# this script was added the same day, after that fix landed. Without
# this, a human/agent on a feature branch in this shared checkout with
# the 4 allowlisted files dirty would get this timer's commit silently
# landed on their branch, then `git push origin main` pushing the local
# main ref regardless of what's checked out - a stranded, mis-attributed
# commit and a confusing push.
current_branch="$(git rev-parse --abbrev-ref HEAD)"
if [ "$current_branch" != "$BRANCH" ]; then
  echo "$LOG_PREFIX refusing to commit: checked out on '$current_branch', expected '$BRANCH' - leaving dirty state for a human." >&2
  exit 1
fi

echo "$LOG_PREFIX auto-syncing known self-improvement state files"
if [ -n "$dirty_tracked" ]; then
  git add "${STATE_FILES[@]}"
fi
if [ -n "$new_run_dirs" ]; then
  git add "$RUNS_DIR"
fi
git commit --quiet -m "chore(self-improvement): auto-sync tracked state files and new run dirs

Automated commit by sync-self-improvement-state.service - the 4 tracked
state files are mechanically rewritten every self-improvement cycle, and
new $RUNS_DIR/*/ directories are written once per cycle. Both would
otherwise permanently block auto-deploy.sh's dirty-tree guard (state
files) or silently accumulate as an ever-growing untracked backlog (run
dirs, see 2026-09-15 second adversarial pass note above)."

git fetch origin "$BRANCH" --quiet
if ! git merge --ff-only "origin/$BRANCH" --quiet 2>/dev/null; then
  echo "$LOG_PREFIX WARNING: local history diverged from origin/$BRANCH before push - leaving commit local, needs a human." >&2
  exit 1
fi

git push origin "$BRANCH" --quiet
echo "$LOG_PREFIX done."
