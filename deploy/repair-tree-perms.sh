#!/usr/bin/env bash
# Keeps lcars-portal/ writable by the `deploy` group, so auto-deploy.service
# (User=deploy) can keep running `npm ci && npm run build` there (2026-09-27).
#
# Root cause: same class of bug as repair-git-perms.sh's .git/ fix, just
# hit outside .git — something ran npm/vitest/an editor as root directly
# inside lcars-portal/ (a build, a manual `npm test`, a root-run agent
# session), creating files/dirs owned by root with the default umask
# (022, no group-write). setgid on node_modules/ still hands new entries
# group `deploy`, but mode ...r-x means `deploy` can read/traverse but
# not write/delete/recreate them. First hit: `npm ci` failed on
# node_modules/.vite/vitest ("EACCES ... unlink"), then again on
# .next/server/app-paths-manifest.json — confirmed 647 dirs + 1406 files
# under lcars-portal/ alone were root-owned and missing group-write at
# the time this was found.
#
# Scoped to lcars-portal/ only (not the whole repo, like repair-git-perms.sh
# is scoped to .git/ only) — that's the one directory auto-deploy.sh
# actually writes into as `deploy` (git pull writes go through .git/,
# already covered separately). A full-repo scan every 5-minute cycle
# would be needlessly expensive (23GB, ~350k files); lcars-portal alone
# is ~1.2GB / ~40k entries and scans in well under a second.
#
# Runs as ROOT via auto-deploy.service's `ExecStartPre=+`. Same rule as
# deploy/scoped-restart.sh and deploy/repair-git-perms.sh: THIS COPY IS
# SOURCE ONLY. systemd executes the promoted copy at
# /opt/deploy-guard/repair-tree-perms.sh (root:root, outside any
# `deploy`-writable path); promote with deploy/sync-deploy-guard.sh after
# review. Never point the unit at this in-repo copy - `deploy` can write
# to it.

set -euo pipefail

REPO_ROOT="${REPAIR_TREE_PERMS_REPO_ROOT:-/opt/starship-endeavour}"
GROUP="${REPAIR_TREE_PERMS_GROUP:-deploy}"
TARGET_DIR="$REPO_ROOT/lcars-portal"
LOG_PREFIX="[repair-tree-perms]"

# Running as root inside a tree `deploy` can write to: refuse a target
# that isn't a plain directory, so a swapped-in symlink can't redirect
# the chgrp/chmod below onto some other path.
if [ -L "$TARGET_DIR" ] || [ ! -d "$TARGET_DIR" ]; then
  echo "$LOG_PREFIX ABORT: $TARGET_DIR is not a plain directory" >&2
  exit 1
fi

# find -P (the default) never follows symlinks. Files with more than one
# hard link are skipped so a hard link planted into the tree can't be
# used to chgrp/chmod a file elsewhere on the filesystem. Only entries
# NOT already owned by `deploy` are touched — deploy-owned files/dirs
# (the normal case, e.g. everything npm itself creates as `deploy`) are
# already writable by their own owner and don't need a group grant.
fixed="$(
  {
    find "$TARGET_DIR" -path "$TARGET_DIR/.git" -prune -o \
      -type d ! -user deploy ! -perm -020 -print -exec chgrp "$GROUP" {} \; -exec chmod g+rwxs {} \;
    find "$TARGET_DIR" -path "$TARGET_DIR/.git" -prune -o \
      -type f -links 1 ! -user deploy -perm -u+w ! -perm -g+w -print -exec chgrp "$GROUP" {} \; -exec chmod g+w {} \;
  } | sort -u | wc -l
)"

if [ "$fixed" -gt 0 ]; then
  echo "$LOG_PREFIX repaired group ownership/permissions on $fixed path(s) under $TARGET_DIR"
fi
