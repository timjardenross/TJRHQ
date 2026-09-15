#!/usr/bin/env bash
# Scoped, allowlist-checked `systemctl restart` — the only command the
# non-root `deploy` user is allowed to run as root (see
# /etc/sudoers.d/deploy-restart). auto-deploy.sh calls this instead of
# a raw `systemctl restart $svc` so the allowlist lives in one place
# (this script + auto-deploy-services.conf) rather than being duplicated
# into sudoers as one line per service — extending the restart allowlist
# only ever means editing auto-deploy-services.conf, never touching
# sudoers again.
#
# 2026-09-15 adversarial review: auto-deploy.service ran the whole
# git-pull + npm-build + restart pipeline as root with no privilege
# scoping — full root blast radius for a pull-based deploy pipeline that
# only ever needs to restart a small fixed set of services. This script
# plus the `deploy` system user (repo chgrp'd, not chowned, so the ~30
# other root-run cron/systemd jobs sharing this tree keep working
# untouched) closes that gap.
#
# 2026-09-15 SECOND adversarial pass: that fix was defeated — this file
# sat inside the same git tree `deploy` can write to (group-writable
# dirs + `git merge --ff-only` on every pull), so anything landing on
# main, or `deploy` itself, could rewrite the exact script sudoers
# trusted, closing the loop back to root. THIS COPY IS NOW SOURCE ONLY —
# reviewed here via normal PRs/git history, but sudo no longer executes
# it. The enforced copy lives at /opt/deploy-guard/scoped-restart.sh
# (root:root, mode 750, outside any `deploy`-writable path). After a
# reviewed change lands here, a human with root must run
# deploy/sync-deploy-guard.sh to promote it — never automate that step
# from the deploy account or a git/CI hook, or this fix is defeated
# again the same way.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICES_CONF="$REPO_ROOT/deploy/auto-deploy-services.conf"

# Drop-in replacement for $SYSTEMCTL in auto-deploy.sh, which calls
# "$SYSTEMCTL" restart "$svc" — so this takes the same (verb, unit) shape
# as systemctl itself rather than a bespoke CLI, needing zero changes to
# auto-deploy.sh (AUTO_DEPLOY_SYSTEMCTL is already its own env override
# point). Only the "restart" verb is supported — this script has no other
# reason to exist.
VERB="${1:-}"
UNIT="${2:-}"

if [ "$VERB" != "restart" ] || [ -z "$UNIT" ]; then
  echo "usage: scoped-restart.sh restart <unit>" >&2
  exit 2
fi

is_allowed() {
  # lcars-portal.service is hardcoded (auto-deploy.sh's own unconditional
  # restart-on-frontend-change path, not part of the conf-driven list).
  [ "$UNIT" = "lcars-portal.service" ] && return 0
  [ -f "$SERVICES_CONF" ] || return 1
  while IFS= read -r line; do
    svc="$(echo "$line" | sed 's/#.*//' | xargs || true)"
    [ -n "$svc" ] && [ "$svc" = "$UNIT" ] && return 0
  done < "$SERVICES_CONF"
  return 1
}

if ! is_allowed; then
  echo "scoped-restart.sh: '$UNIT' is not in the auto-deploy restart allowlist ($SERVICES_CONF) — refusing" >&2
  exit 1
fi

exec systemctl restart "$UNIT"
