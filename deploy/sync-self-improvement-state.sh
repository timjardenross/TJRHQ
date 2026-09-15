#!/bin/bash
# Keeps 4 known, mechanically-rewritten tracked state files in sync with
# origin/main so they never block auto-deploy.sh's dirty-tree guard.
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
set -euo pipefail

REPO_ROOT="${SYNC_STATE_REPO_ROOT:-/opt/starship-endeavour}"
BRANCH="${SYNC_STATE_BRANCH:-main}"
LOG_PREFIX="[sync-self-improvement-state]"

STATE_FILES=(
  ".id-counters.json"
  "data/self-improvement/review/evolution_summary.json"
  "data/self-improvement/review/finding_staleness.jsonl"
  "data/self-improvement/review/opportunity_id_counter.txt"
)

cd "$REPO_ROOT"

dirty_tracked="$(git status --porcelain --untracked-files=no)"

if [ -z "$dirty_tracked" ]; then
  echo "$LOG_PREFIX nothing dirty - nothing to do."
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

echo "$LOG_PREFIX auto-syncing known self-improvement state files"
git add "${STATE_FILES[@]}"
git commit --quiet -m "chore(self-improvement): auto-sync tracked state files

Automated commit by sync-self-improvement-state.service - these 4 files
are mechanically rewritten every self-improvement cycle and would
otherwise permanently block auto-deploy.sh's dirty-tree guard."

git fetch origin "$BRANCH" --quiet
if ! git merge --ff-only "origin/$BRANCH" --quiet 2>/dev/null; then
  echo "$LOG_PREFIX WARNING: local history diverged from origin/$BRANCH before push - leaving commit local, needs a human." >&2
  exit 1
fi

git push origin "$BRANCH" --quiet
echo "$LOG_PREFIX done."
