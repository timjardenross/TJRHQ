#!/bin/bash
# Pull-based auto-deploy for the VM half of this platform (2026-09-07).
#
# Merging a PR on GitHub only ever updated main - nothing on this VM ever
# checked GitHub, so every backend fix required the Captain to SSH in and
# `git pull` by hand (confirmed: no webhook receiver, no self-hosted GitHub
# Actions runner, no auto-deploy script anywhere in this repo before this
# one). The frontend (lcars-portal) already closes this loop automatically
# via Vercel; this closes the other half, on the same polling-timer pattern
# every other job on this VM already uses (see auto-deploy.timer) rather
# than exposing a new inbound webhook endpoint.
#
# Safety rules, in order:
#   1. Never touches a working tree with uncommitted changes to a TRACKED
#      file - a manual in-progress edit on this VM always wins over
#      automation. Aborts loudly instead. Untracked files are not checked
#      here (see the dirty-check below for why - they can't be endangered
#      by a fast-forward pull the way a modified tracked file can).
#   2. Fast-forward only. Never merges, never rebases, never resolves a
#      conflict. If history has diverged, stop and surface it - this repo's
#      main should only ever move forward from this VM's point of view.
#   3. Never runs `git push` - read-only against GitHub, this VM only ever
#      pulls.
#
# 2026-09-21 (staleness rework — see memory
# auto-deploy-skips-restart-on-local-commits-2026-09-21): this used to
# ONLY restart services inside the "we just pulled a new commit" branch,
# which is exactly the case a commit made DIRECTLY ON THIS VM (the normal
# in-place Claude-session workflow) never hits — that commit is already
# at HEAD locally the moment it's made, so there is nothing to pull, so
# nothing ever restarted. Diagnosed live: intelligence-scheduler.service
# ran for 2 days on a pre-rename AttentionDecision class after a same-VM
# commit renamed one of its fields, and only surfaced when its weekly
# drill job finally exercised the mismatch.
#
# Fix: service restarts are now driven by STALENESS (does the unit's own
# `ActiveEnterTimestamp` predate the newest relevant commit already on
# disk), checked unconditionally on every run of this script regardless
# of whether a pull happened this cycle. This one mechanism now covers
# both cases:
#   - a real `git pull` landing new commits (the newest commit's time
#     moves forward, almost certainly past every running service's start
#     time) - same effective behaviour as the old "restart on any pull";
#   - a commit already made directly on this VM before this script ever
#     ran (no pull needed - HEAD hasn't moved, but the commit's own
#     timestamp is still newer than a long-running service's start time).
#
# Service scoping:
#   - lcars-portal.service: staleness measured against the newest commit
#     touching `lcars-portal/` specifically (it needs `npm ci && npm run
#     build` first, not just a restart - a Next.js production server is
#     pre-compiled).
#   - Everything else in SERVICES_CONF (see auto-deploy-services.conf):
#     staleness measured against the newest commit anywhere in the repo,
#     same "don't try to map file paths to services" reasoning the old
#     unconditional-restart comment gave - these are lightweight
#     bots/services that restart in seconds under systemd's own
#     supervision (Restart=always).
#   - The rest of this VM's automation (delivery-reconciler.timer,
#     hq-evolution.timer, etc.) needs NO restart at all: they're oneshot
#     jobs re-invoked fresh from disk on their own schedule, so they pick
#     up new code on their very next scheduled run automatically.
#
# A restart target that doesn't exist (wrong or stale unit name, or one
# that has simply never been started so has no ActiveEnterTimestamp) just
# logs a warning and moves on - it never silently restarts the WRONG unit
# under a different name. See auto-deploy-services.conf's own header for
# why that list must be verified against this VM's actual `systemctl`
# output, not assumed from this repo's deploy/*.service filenames
# (confirmed drift: this repo's xo-bot.service file names a unit that
# isn't what actually runs - telegram-bots/xo/app.py's own restart
# command targets "tg-xo.service" instead).

set -euo pipefail

# Overridable via env for testing; production always runs with the defaults.
REPO_ROOT="${AUTO_DEPLOY_REPO_ROOT:-/opt/starship-endeavour}"
BRANCH="${AUTO_DEPLOY_BRANCH:-main}"
SERVICES_CONF="${AUTO_DEPLOY_SERVICES_CONF:-$REPO_ROOT/deploy/auto-deploy-services.conf}"
SYSTEMCTL="${AUTO_DEPLOY_SYSTEMCTL:-systemctl}"
LOG_PREFIX="[auto-deploy]"

cd "$REPO_ROOT"

# --untracked-files=no: a new untracked file (several live processes on this
# VM drop one, e.g. self-improvement/mission-dispatch handoff docs, before a
# separate job commits it later) can't be endangered by a fast-forward pull -
# it isn't part of the tree git is fast-forwarding. The one real edge case
# (an incoming commit adds a file at that same untracked path) is still
# caught: `git merge --ff-only` below refuses to clobber an untracked file
# and fails loudly, which is exactly the existing "fast-forward failed"
# abort path. What this check still must catch is an uncommitted EDIT to an
# already-tracked file - that's the one thing a pull could actually stomp on.
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "$LOG_PREFIX ABORT: working tree is dirty (uncommitted changes to tracked files) - not pulling, not checking staleness this cycle. Resolve manually." >&2
  exit 1
fi

git fetch origin "$BRANCH" --quiet

LOCAL_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git rev-parse "origin/$BRANCH")"

if [ "$LOCAL_SHA" = "$REMOTE_SHA" ]; then
  echo "$LOG_PREFIX up to date ($LOCAL_SHA) - nothing to pull."
else
  if ! git merge --ff-only "origin/$BRANCH"; then
    echo "$LOG_PREFIX ABORT: fast-forward failed (history diverged?) - needs a human." >&2
    exit 1
  fi
  echo "$LOG_PREFIX pulled $LOCAL_SHA -> $REMOTE_SHA"
  git diff --name-only "$LOCAL_SHA" "$REMOTE_SHA" | sed "s|^|$LOG_PREFIX   changed: |"
fi

# ── Staleness-driven restarts (runs every cycle, pull or no pull) ──────────

# Epoch seconds a unit last became active, or empty if it's never been
# started (unknown/stale unit name) - `systemctl show` never errors even
# for a name that doesn't exist, it just returns an empty value, so this
# stays consistent with the existing "wrong/stale unit name just logs a
# warning" contract.
unit_active_since_epoch() {
  local ts
  ts="$("$SYSTEMCTL" show -p ActiveEnterTimestamp --value "$1" 2>/dev/null || true)"
  [ -z "$ts" ] && return 1
  date -d "$ts" +%s 2>/dev/null || return 1
}

# Epoch seconds of the newest commit touching the given path (or the whole
# repo if no path given) - 0 if the path has no history at all.
newest_commit_epoch() {
  git log -1 --format=%ct -- "${1:-.}" 2>/dev/null || echo 0
}

LP_COMMIT_TS="$(newest_commit_epoch lcars-portal)"
if LP_START_TS="$(unit_active_since_epoch lcars-portal.service)"; then
  if [ "$LP_COMMIT_TS" -gt "$LP_START_TS" ]; then
    echo "$LOG_PREFIX lcars-portal.service is stale (running since before the newest lcars-portal/ commit) - rebuilding"
    ( cd "$REPO_ROOT/lcars-portal" && npm ci --no-audit --no-fund && "$REPO_ROOT/platform-runtime/run-with-infisical.sh" npm run build )
    # 2026-09-21: OLLAMA_MODEL_DEFAULT misconfig (misspelled secret key ->
    # code fell back to a model Ollama doesn't have) silently killed AI
    # Review/Polish/Generate for an unknown period - no error, no crash, just
    # honest-fallback scaffold mode forever. Fail the deploy loudly here
    # instead of restarting into the same silent failure again.
    echo "$LOG_PREFIX checking OLLAMA_MODEL_DEFAULT against Ollama's pulled models"
    if ! "$REPO_ROOT/platform-runtime/run-with-infisical.sh" "$REPO_ROOT/platform-runtime/check-ollama-model-default.sh"; then
      echo "$LOG_PREFIX ABORT: OLLAMA_MODEL_DEFAULT is missing or unavailable - not restarting lcars-portal.service into a broken AI config. Needs a human." >&2
      exit 1
    fi
    echo "$LOG_PREFIX restarting lcars-portal.service"
    "$SYSTEMCTL" restart lcars-portal.service || echo "$LOG_PREFIX WARNING: restart failed for lcars-portal.service" >&2
  fi
else
  echo "$LOG_PREFIX WARNING: lcars-portal.service has no ActiveEnterTimestamp (never started / wrong unit name?) - skipping staleness check for it" >&2
fi

if [ -f "$SERVICES_CONF" ]; then
  REPO_COMMIT_TS="$(newest_commit_epoch)"
  while IFS= read -r line; do
    svc="$(echo "$line" | sed 's/#.*//' | xargs || true)"
    [ -z "$svc" ] && continue
    if svc_start_ts="$(unit_active_since_epoch "$svc")"; then
      if [ "$REPO_COMMIT_TS" -gt "$svc_start_ts" ]; then
        echo "$LOG_PREFIX $svc is stale (running since before the newest repo commit) - restarting"
        "$SYSTEMCTL" restart "$svc" || echo "$LOG_PREFIX WARNING: restart failed for $svc (wrong/stale unit name?)" >&2
      fi
    else
      echo "$LOG_PREFIX WARNING: $svc has no ActiveEnterTimestamp (never started / wrong unit name?) - skipping staleness check for it" >&2
    fi
  done < "$SERVICES_CONF"
fi

echo "$LOG_PREFIX done."
