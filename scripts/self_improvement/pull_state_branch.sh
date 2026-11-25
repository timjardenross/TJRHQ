#!/bin/bash
# Path-scoped intake of the live self-improvement state into the daily-cycle worktree (#757 step 1).
#
# Until now the worktree received the live tree's state files and run directories because
# deploy/sync-self-improvement-state.sh committed them to main and run_daily_cycle.sh merged origin/main. That job now
# publishes to the state branch (default state/self-improvement) instead, so this script copies ONLY the allowlisted
# state paths from origin/<state branch> into the worktree's working files. It never merges the state branch (its tree
# is a frozen copy of main from bootstrap time, so a merge would drag stale code in) and it does not stage or commit:
# the cycle's own git_commit(paths=...) does that, exactly as for files that arrived through a merge before.
#
# Usage: pull_state_branch.sh <worktree>        (env STATE_BRANCH / STATE_REMOTE override the defaults)
# Exit 0 always except usage errors: a missing branch or failed fetch is logged and the cycle continues on what it has
# (same "log it, don't block the cycle" contract as the origin/main merge in run_daily_cycle.sh).
set -uo pipefail
WORKTREE="${1:?usage: pull_state_branch.sh <worktree>}"
STATE_BRANCH="${STATE_BRANCH:-state/self-improvement}"
REMOTE="${STATE_REMOTE:-origin}"
RUNS_DIR="data/self-improvement/runs"
PATHS=(
  ".id-counters.json"
  "data/self-improvement/review/evolution_summary.json"
  "data/self-improvement/review/finding_staleness.jsonl"
  "data/self-improvement/review/opportunity_id_counter.txt"
  "data/self-improvement/review/opportunity_snapshot.json"
)
cd "$WORKTREE" || { echo "pull_state_branch: cannot cd to $WORKTREE" >&2; exit 2; }

if ! git fetch "$REMOTE" "+refs/heads/$STATE_BRANCH:refs/sync-state/pulled-tip" --quiet 2>/dev/null; then
  echo "WARNING: could not fetch $REMOTE/$STATE_BRANCH in $WORKTREE -- live state may be stale this cycle" >&2
  exit 0
fi
ref=refs/sync-state/pulled-tip
sel=()
for p in "${PATHS[@]}"; do
  git cat-file -e "$ref:$p" 2>/dev/null && sel+=("$p")
done
if git cat-file -e "$ref:$RUNS_DIR" 2>/dev/null; then sel+=("$RUNS_DIR"); fi
if [ "${#sel[@]}" -eq 0 ]; then
  echo "pull_state_branch: $REMOTE/$STATE_BRANCH holds none of the state paths - nothing to take"
  exit 0
fi
# --worktree only: files are updated on disk, the index is left alone.
if git restore --source="$ref" --worktree -- "${sel[@]}"; then
  echo "pull_state_branch: took ${#sel[@]} state path(s) from $REMOTE/$STATE_BRANCH ($(git rev-parse --short "$ref"))"
else
  echo "WARNING: could not apply state paths from $REMOTE/$STATE_BRANCH in $WORKTREE" >&2
fi
exit 0
