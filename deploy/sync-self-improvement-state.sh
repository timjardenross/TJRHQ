#!/bin/bash
# Publishes the mechanically-rewritten self-improvement state files, plus new data/self-improvement/runs/
# directories, to a DEDICATED STATE BRANCH (default state/self-improvement) - never to main.
#
# 2026-11-25 (#757 step 1): this job used to commit on main and `git push origin main` every 3 minutes, which
# (a) blocks any "require a pull request" rule on main and (b) fast-forwarded the live working tree. It now:
#   - builds the commit with a TEMPORARY INDEX and `git commit-tree`, on top of the previous state-branch tip
#     (bootstrap: the current origin/main tip, so the first run uploads nothing large because runs/ already matches);
#   - pushes `<commit>:refs/heads/<state branch>` (never forced, never main);
#   - never touches the live working tree, its index, HEAD, the checked-out branch or local main, so it needs no
#     release-window deferral, no "behind origin" handling and no branch check any more.
# The live tree keeps these tracked files modified relative to main (auto-deploy's dirty check already tolerates
# them). Consumers read the state from the state branch: the daily self-improvement cycle takes the paths from it
# (scripts/self_improvement/pull_state_branch.sh); remote agents read origin/<state branch>.
#
# History of the allowlist: 2026-09-15 the state files were permanently dirty and tripped auto-deploy's dirty-tree
# guard; 451 untracked run directories (494MB) piled up before a committer covered them. Both are still covered:
# the allowlist below is explicit, nothing else is ever published.
#
# Safety rails (fail closed, exit 1 so the OnFailure alert fires):
#   - STATE_BRANCH must look like state/<name>; main (or anything else) is refused, so a bad env cannot push to main.
#   - The tree the state branch is built on must carry the Vercel branch guard for state/** (lcars-portal/vercel.json
#     git.deploymentEnabled "state/**": false). Vercel reads that file from the pushed commit, and the state branch
#     tree is frozen at the bootstrap tip, so bootstrapping from a main without the guard would create a preview
#     deployment on every push (a 3-minute cadence would exhaust the daily allowance). SYNC_STATE_REQUIRE_VERCEL_GUARD=0
#     disables the check (tests only).
#   - A rejected push (someone else moved the branch) is retried once from a fresh fetch; nothing local is updated
#     before a push succeeds, so a failure leaves no half-done state, only an unreferenced commit object.
set -euo pipefail

REPO_ROOT="${SYNC_STATE_REPO_ROOT:-/opt/starship-endeavour}"
MAIN_BRANCH="${SYNC_STATE_MAIN_BRANCH:-main}"          # bootstrap source only; this job never writes it
STATE_BRANCH="${SYNC_STATE_BRANCH:-state/self-improvement}"
REMOTE="${SYNC_STATE_REMOTE:-origin}"
REQUIRE_VERCEL_GUARD="${SYNC_STATE_REQUIRE_VERCEL_GUARD:-1}"
LOG_PREFIX="[sync-self-improvement-state]"
RUNS_DIR="data/self-improvement/runs"

STATE_FILES=(
  ".id-counters.json"
  "data/self-improvement/review/evolution_summary.json"
  "data/self-improvement/review/finding_staleness.jsonl"
  "data/self-improvement/review/opportunity_id_counter.txt"
  "data/self-improvement/review/opportunity_snapshot.json"
)
# Deliberately NOT published (owner elsewhere): data/self-improvement/review/mission_dispatch_log.jsonl (high churn,
# nightly off-box backup) and Missions/Engineering-Handoffs/ (human-owned). They are simply never read here.

die() { echo "$LOG_PREFIX $*" >&2; exit 1; }

case "$STATE_BRANCH" in
  state/?*) ;;
  *) die "refusing: STATE_BRANCH '$STATE_BRANCH' is not of the form state/<name> (this job must never write main)." ;;
esac
case "$STATE_BRANCH" in *..*|*' '*|*'~'*|*'^'*|*':'*|*'\\'*) die "refusing: unsafe branch name '$STATE_BRANCH'." ;; esac
[ "$STATE_BRANCH" != "$MAIN_BRANCH" ] || die "refusing: state branch equals main."

cd "$REPO_ROOT"

# Refresh the tracked snapshot of open opportunities (opportunities.jsonl itself is untracked on purpose) so it rides
# along with the other state files. Best-effort: a failed export must never stop the sync.
python3 scripts/self_improvement/export_opportunity_snapshot.py \
  || echo "$LOG_PREFIX WARNING: opportunity snapshot export failed - continuing." >&2

# Temporary index: the live index is never read or written.
TMP_INDEX="$(mktemp -u "${TMPDIR:-/tmp}/sync-state-index.XXXXXX")"
trap 'rm -f "$TMP_INDEX" "$TMP_INDEX.lock" "$TMP_INDEX".newruns "$TMP_INDEX".knownruns "$TMP_INDEX".freshruns "$TMP_INDEX".push.err' EXIT
git_tmp() { GIT_INDEX_FILE="$TMP_INDEX" git "$@"; }

# Sets PARENT (commit to build on) and PARENT_KIND; exit 1 on any fetch problem.
resolve_parent() {
  local rc=0
  git ls-remote --exit-code --heads "$REMOTE" "refs/heads/$STATE_BRANCH" >/dev/null 2>&1 || rc=$?
  if [ "$rc" = 0 ]; then
    git fetch "$REMOTE" "+refs/heads/$STATE_BRANCH:refs/sync-state/remote-tip" --quiet \
      || die "WARNING: could not fetch $REMOTE/$STATE_BRANCH - nothing published this run."
    PARENT="$(git rev-parse refs/sync-state/remote-tip)"; PARENT_KIND="state branch tip"
  elif [ "$rc" = 2 ]; then
    git fetch "$REMOTE" "+refs/heads/$MAIN_BRANCH:refs/sync-state/remote-main" --quiet \
      || die "WARNING: could not fetch $REMOTE/$MAIN_BRANCH to bootstrap $STATE_BRANCH - nothing published this run."
    PARENT="$(git rev-parse refs/sync-state/remote-main)"; PARENT_KIND="bootstrap from $MAIN_BRANCH tip"
  else
    die "WARNING: could not reach $REMOTE (ls-remote rc=$rc) - nothing published this run."
  fi
}

# Builds a candidate commit; sets NEW_COMMIT (empty when there is nothing new). Reads working-tree files only.
build_commit() {
  resolve_parent
  if [ "$REQUIRE_VERCEL_GUARD" = 1 ] && git cat-file -e "$PARENT:lcars-portal/vercel.json" 2>/dev/null; then
    git show "$PARENT:lcars-portal/vercel.json" | grep -q '"state/\*\*"[[:space:]]*:[[:space:]]*false' \
      || die "refusing: $PARENT_KIND ($PARENT) has no \"state/**\": false in lcars-portal/vercel.json - pushing would create Vercel previews every run. Merge the guard to main first."
  fi
  rm -f "$TMP_INDEX"
  git_tmp read-tree "$PARENT"
  local present=() f
  for f in "${STATE_FILES[@]}"; do
    [ -f "$f" ] && present+=("$f")
  done
  # --ignore-removal: a file missing locally never deletes it from the state branch.
  if [ "${#present[@]}" -gt 0 ]; then git_tmp add --ignore-removal -- "${present[@]}"; fi
  # Run directories are written once and never modified, so only files the parent does not already hold are added.
  # (A fresh temporary index has no stat cache: hashing every existing run file every 3 minutes would read the whole,
  # ever-growing runs/ tree each time.) Untracked-in-live-tree is found via the live index stat cache, read-only.
  if [ -d "$RUNS_DIR" ]; then
    local newfiles="${TMP_INDEX}.newruns" known="${TMP_INDEX}.knownruns" fresh="${TMP_INDEX}.freshruns"
    git ls-files -o --exclude-standard -z -- "$RUNS_DIR" | sort -z >"$newfiles"
    git_tmp ls-files -z -- "$RUNS_DIR" | sort -z >"$known"
    comm -z -23 "$newfiles" "$known" >"$fresh"
    if [ -s "$fresh" ]; then git_tmp add --ignore-removal --pathspec-from-file="$fresh" --pathspec-file-nul; fi
    rm -f "$newfiles" "$known" "$fresh"
  fi
  local new_tree parent_tree
  new_tree="$(git_tmp write-tree)"
  parent_tree="$(git rev-parse "$PARENT^{tree}")"
  NEW_COMMIT=""
  if [ "$new_tree" = "$parent_tree" ]; then return 0; fi
  # Identity: use the repo's configured one, else a fixed automation identity (never fail on a missing config).
  git config user.name >/dev/null 2>&1 || export GIT_AUTHOR_NAME="${GIT_AUTHOR_NAME:-sync-self-improvement-state}" GIT_COMMITTER_NAME="${GIT_COMMITTER_NAME:-sync-self-improvement-state}"
  git config user.email >/dev/null 2>&1 || export GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL:-sync-self-improvement-state@localhost}" GIT_COMMITTER_EMAIL="${GIT_COMMITTER_EMAIL:-sync-self-improvement-state@localhost}"
  NEW_COMMIT="$(git commit-tree "$new_tree" -p "$PARENT" -m "chore(self-improvement): auto-sync tracked state files and new run dirs

Automated state commit by sync-self-improvement-state.service on the state branch $STATE_BRANCH.
Never merged to main; consumers take the allowlisted state paths from this branch.")"
}

build_commit
if [ -z "$NEW_COMMIT" ]; then
  echo "$LOG_PREFIX no state change vs $PARENT_KIND ($PARENT) - nothing to do."
  exit 0
fi

push_commit() { git push "$REMOTE" "$NEW_COMMIT:refs/heads/$STATE_BRANCH" --quiet 2>"${TMP_INDEX}.push.err"; }
echo "$LOG_PREFIX publishing state to $REMOTE/$STATE_BRANCH ($PARENT_KIND $PARENT -> $NEW_COMMIT)"
if ! push_commit; then
  echo "$LOG_PREFIX push rejected or failed ($(tr '\n' ' ' <"${TMP_INDEX}.push.err")) - retrying once from a fresh fetch." >&2
  build_commit
  if [ -z "$NEW_COMMIT" ]; then
    rm -f "${TMP_INDEX}.push.err"; echo "$LOG_PREFIX state already published by another writer - nothing to do."; exit 0
  fi
  if ! push_commit; then
    err="$(tr '\n' ' ' <"${TMP_INDEX}.push.err")"; rm -f "${TMP_INDEX}.push.err"
    die "WARNING: push to $REMOTE/$STATE_BRANCH failed twice ($err) - nothing published; next run retries from scratch."
  fi
fi
rm -f "${TMP_INDEX}.push.err"
echo "$LOG_PREFIX done ($NEW_COMMIT on $STATE_BRANCH; $MAIN_BRANCH, HEAD, index and working tree untouched)."
