#!/usr/bin/env bash
set -euo pipefail

# USS-TJR-MSN-0377: self-improving-system.service's ExecStart used to run
# orchestrator.py directly against /opt/starship-endeavour -- the SAME
# checkout every interactive Claude session on this host also uses for its
# own feature-branch work. orchestrator.py's git_commit() (auto_remediation.
# py) refuses to commit unless that checkout is on `self-improvement`
# (LL-146/LL-149's fail-closed fix), which is correct in isolation but
# meant the checkout needed to coincidentally be on that exact branch at
# 04:30 every day -- something nothing in this repo's actual usage pattern
# ever guaranteed. Real result: zero cycle-artifact commits landed between
# LL-149 shipping (2026-09-12) and this fix, ~64 cycles silently refused.
# See knowledge/missions/USS-TJR-MSN-0377-knowledge-record.md.
#
# Fix: give this service its own dedicated git worktree, permanently
# checked out on `self-improvement`, never touched by any human/session --
# so the branch-mismatch check in git_commit() now always passes by
# construction instead of by coincidence. Fast-forwarded from origin/main
# first so evidence collection still reflects live code; a failed
# fetch/merge is logged but does not block the cycle (it just runs against
# whatever the worktree already has, same as any other day the timer's
# RandomizedDelaySec means it doesn't run at the instant a merge failure
# might be transient).

MAIN_REPO="/opt/starship-endeavour"
WORKTREE="/opt/starship-endeavour-self-improvement"
VENV_PYTHON="$MAIN_REPO/scripts/self_improvement/.venv/bin/python3"

if [ ! -d "$WORKTREE/.git" ] && [ ! -f "$WORKTREE/.git" ]; then
  echo "Creating dedicated self-improvement worktree at $WORKTREE"
  git -C "$MAIN_REPO" worktree add "$WORKTREE" self-improvement
fi

cd "$WORKTREE"

if ! git fetch origin main; then
  echo "WARNING: git fetch origin/main failed in $WORKTREE -- evidence may be stale this cycle" >&2
elif ! git merge --ff-only origin/main; then
  echo "WARNING: fast-forward from origin/main failed in $WORKTREE (diverged?) -- evidence may be stale this cycle" >&2
fi

exec "$VENV_PYTHON" "$WORKTREE/scripts/self_improvement/orchestrator.py" \
  --repo-root "$WORKTREE" \
  --data-root "$WORKTREE/data/self-improvement" \
  "$@"
