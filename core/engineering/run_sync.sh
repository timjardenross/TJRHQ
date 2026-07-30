#!/usr/bin/env bash
# Auto-progress approved engineering handoffs: PENDING -> DELIVERED (+ draft PR).
#
# Runs `batch_coding sync` (the Mistral chat.complete path; the Batch API is
# 402/billing-blocked) over every PENDING handoff. Triggered two ways (hybrid,
# Captain decision to cross D-054 for the build pipeline):
#   * inline  — fired fire-and-forget by the Slack approval handler (app.py)
#   * timer   — batch-coding-sync.timer sweeps every 15min as a catch-up net
#
# flock makes the two safe to overlap: only one sync runs at a time; a losing
# invocation exits 0 immediately and the next timer sweep (<=15min) picks up
# anything it skipped. Extra args are forwarded to the sync subcommand (e.g.
# `run_sync.sh --dry-run` to test the plumbing with no side effects).
set -euo pipefail

REPO_ROOT=/opt/starship-endeavour
VENV_PY="$REPO_ROOT/platform-runtime/.venv/bin/python"   # only venv with mistralai
LOCK=/run/lock/batch-coding-sync.lock
LOG=/var/log/batch-coding-sync.log

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "$(date -Is) [run_sync] another sync holds the lock; skipping" >>"$LOG"
  exit 0
fi

cd "$REPO_ROOT"
echo "$(date -Is) [run_sync] start (args: $*)" >>"$LOG"
"$VENV_PY" -m core.engineering.batch_coding sync "$@" >>"$LOG" 2>&1
rc=$?
echo "$(date -Is) [run_sync] done (rc=$rc)" >>"$LOG"
exit $rc
