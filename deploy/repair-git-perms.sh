#!/usr/bin/env bash
# Keeps the shared checkout's .git/ writable by the `deploy` group, so
# auto-deploy.service (User=deploy) can keep fetching (2026-09-23).
#
# Root cause: the 2026-09-15 de-rooting of auto-deploy.service did a
# one-time `chgrp -R deploy` + setgid dirs, but nothing kept NEW entries
# group-writable afterwards. The ~30 root-run jobs sharing this tree
# (sync-self-improvement-state.service commits every 3 minutes,
# hq-evolution, self-improving-system, ...) create new loose-object
# fan-out dirs (.git/objects/xx/) and ref/log files with root's umask
# 022. setgid still hands them group `deploy`, but mode 2755 - so the
# next `git fetch` as `deploy` that needs to drop an object into one of
# those dirs dies with:
#   error: insufficient permission for adding an object to repository
#   database .git/objects
# It only fires when an incoming object hashes into a root-created
# fan-out dir, which is why it recurred roughly daily rather than on
# every run.
#
# Fix, two parts:
#   1. core.sharedRepository=group - git itself then makes every dir and
#      file it creates group-writable regardless of the caller's umask,
#      for root and `deploy` alike. This alone stops new breakage.
#   2. Repair anything already wrong (or created by a non-git writer):
#      only touches entries that are actually off, so it's cheap enough
#      to run before every auto-deploy cycle.
#
# Runs as ROOT via auto-deploy.service's `ExecStartPre=+`. Same rule as
# deploy/scoped-restart.sh: THIS COPY IS SOURCE ONLY. systemd executes
# the promoted copy at /opt/deploy-guard/repair-git-perms.sh (root:root,
# outside any `deploy`-writable path); promote with
# deploy/sync-deploy-guard.sh after review. Never point the unit at this
# in-repo copy - `deploy` can write to it.

set -euo pipefail

REPO_ROOT="${REPAIR_GIT_PERMS_REPO_ROOT:-/opt/starship-endeavour}"
GROUP="${REPAIR_GIT_PERMS_GROUP:-deploy}"
GIT_DIR="$REPO_ROOT/.git"
LOG_PREFIX="[repair-git-perms]"

# Running as root inside a tree `deploy` can write to: refuse a .git that
# isn't a plain directory, so a swapped-in symlink can't redirect the
# chgrp/chmod below onto some other path.
if [ -L "$GIT_DIR" ] || [ ! -d "$GIT_DIR" ]; then
  echo "$LOG_PREFIX ABORT: $GIT_DIR is not a plain directory" >&2
  exit 1
fi

if [ "$(git config --file "$GIT_DIR/config" --get core.sharedRepository || true)" != "group" ]; then
  git config --file "$GIT_DIR/config" core.sharedRepository group
  echo "$LOG_PREFIX set core.sharedRepository=group"
fi

# find -P (the default) never follows symlinks. Files with more than one
# hard link are skipped so a hard link planted into .git/ can't be used
# to chgrp/chmod a file elsewhere on the filesystem.
fixed="$(
  {
    find "$GIT_DIR" \( -type d -o \( -type f -links 1 \) \) ! -group "$GROUP" \
      -print -exec chgrp "$GROUP" {} +
    find "$GIT_DIR" -type d ! -perm -2070 -print -exec chmod g+rwxs {} +
    find "$GIT_DIR" -type f -links 1 ! -perm -g+r -print -exec chmod g+r {} +
    # Only owner-writable files get g+w - loose objects and packs are
    # read-only by design and stay that way.
    find "$GIT_DIR" -type f -links 1 -perm -u+w ! -perm -g+w -print -exec chmod g+w {} +
  } | sort -u | wc -l
)"

if [ "$fixed" -gt 0 ]; then
  echo "$LOG_PREFIX repaired group ownership/permissions on $fixed path(s) under $GIT_DIR"
fi
