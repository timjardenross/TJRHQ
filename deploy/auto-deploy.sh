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
#   1. Never touches a dirty working tree - a manual in-progress change on
#      this VM always wins over automation. Aborts loudly instead.
#   2. Fast-forward only. Never merges, never rebases, never resolves a
#      conflict. If history has diverged, stop and surface it - this repo's
#      main should only ever move forward from this VM's point of view.
#   3. Never runs `git push` - read-only against GitHub, this VM only ever
#      pulls.
#
# Service restarts are scoped by what actually changed:
#   - lcars-portal/ changes trigger `npm ci && npm run build` (a Next.js
#     production server is pre-compiled - restarting without rebuilding
#     would keep serving the OLD build) then a restart of that one service.
#   - Everything else in SERVICES_CONF (see auto-deploy-services.conf)
#     restarts unconditionally on ANY successful pull, rather than trying
#     to map changed file paths to services - that mapping is fragile and
#     easy to get wrong; these are lightweight bots/services that restart
#     in seconds under systemd's own supervision (Restart=always).
#   - The rest of this VM's automation (delivery-reconciler.timer,
#     hq-evolution.timer, etc.) needs NO restart at all: they're oneshot
#     jobs re-invoked fresh from disk on their own schedule, so they pick
#     up new code on their very next scheduled run automatically.
#
# A restart target that doesn't exist (wrong or stale unit name) just logs
# a warning and moves on - it never silently restarts the WRONG unit under
# a different name. See auto-deploy-services.conf's own header for why
# that list must be verified against this VM's actual `systemctl` output,
# not assumed from this repo's deploy/*.service filenames (confirmed
# drift: this repo's xo-bot.service file names a unit that isn't what
# actually runs - telegram-bots/xo/app.py's own restart command targets
# "tg-xo.service" instead).

set -euo pipefail

# Overridable via env for testing; production always runs with the defaults.
REPO_ROOT="${AUTO_DEPLOY_REPO_ROOT:-/opt/starship-endeavour}"
BRANCH="${AUTO_DEPLOY_BRANCH:-main}"
SERVICES_CONF="${AUTO_DEPLOY_SERVICES_CONF:-$REPO_ROOT/deploy/auto-deploy-services.conf}"
SYSTEMCTL="${AUTO_DEPLOY_SYSTEMCTL:-systemctl}"
LOG_PREFIX="[auto-deploy]"

cd "$REPO_ROOT"

if [ -n "$(git status --porcelain)" ]; then
  echo "$LOG_PREFIX ABORT: working tree is dirty - not pulling. Resolve manually." >&2
  exit 1
fi

git fetch origin "$BRANCH" --quiet

LOCAL_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git rev-parse "origin/$BRANCH")"

if [ "$LOCAL_SHA" = "$REMOTE_SHA" ]; then
  echo "$LOG_PREFIX up to date ($LOCAL_SHA) - nothing to do."
  exit 0
fi

CHANGED_FILES="$(git diff --name-only "$LOCAL_SHA" "$REMOTE_SHA")"

if ! git merge --ff-only "origin/$BRANCH"; then
  echo "$LOG_PREFIX ABORT: fast-forward failed (history diverged?) - needs a human." >&2
  exit 1
fi

echo "$LOG_PREFIX pulled $LOCAL_SHA -> $REMOTE_SHA"
echo "$CHANGED_FILES" | sed "s|^|$LOG_PREFIX   changed: |"

if echo "$CHANGED_FILES" | grep -q '^lcars-portal/'; then
  echo "$LOG_PREFIX lcars-portal/ changed - rebuilding"
  ( cd "$REPO_ROOT/lcars-portal" && npm ci --no-audit --no-fund && npm run build )
  echo "$LOG_PREFIX restarting lcars-portal.service"
  "$SYSTEMCTL" restart lcars-portal.service || echo "$LOG_PREFIX WARNING: restart failed for lcars-portal.service" >&2
fi

if [ -f "$SERVICES_CONF" ]; then
  while IFS= read -r line; do
    svc="$(echo "$line" | sed 's/#.*//' | xargs || true)"
    [ -z "$svc" ] && continue
    echo "$LOG_PREFIX restarting $svc"
    "$SYSTEMCTL" restart "$svc" || echo "$LOG_PREFIX WARNING: restart failed for $svc (wrong/stale unit name?)" >&2
  done < "$SERVICES_CONF"
fi

echo "$LOG_PREFIX done."
