#!/usr/bin/env bash
# Promotes the human-reviewed deploy/scoped-restart.sh and
# deploy/auto-deploy-services.conf in this repo to the root-only,
# non-deploy-writable copies that sudo actually trusts
# (/opt/deploy-guard/*) — see deploy/scoped-restart.sh's 2026-09-15
# SECOND-pass header for why these can no longer be the same file.
#
# MUST be run manually by a human with root, AFTER reviewing `git diff`
# on both source files. Never wire this into auto-deploy.sh, a git hook,
# or anything the `deploy` account can trigger — doing so recreates the
# exact self-escalation loop this split was built to close.

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "sync-deploy-guard.sh: must be run as root" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_SCRIPT="$REPO_ROOT/deploy/scoped-restart.sh"
SRC_CONF="$REPO_ROOT/deploy/auto-deploy-services.conf"
DST_DIR="/opt/deploy-guard"

echo "About to promote:"
echo "  $SRC_SCRIPT -> $DST_DIR/scoped-restart.sh"
echo "  $SRC_CONF -> $DST_DIR/auto-deploy-services.conf"
echo
echo "Diff of script (excluding the source-only 'THIS COPY IS NOW SOURCE ONLY' banner):"
diff -u "$DST_DIR/scoped-restart.sh" "$SRC_SCRIPT" || true
echo
echo "Diff of allowlist conf:"
diff -u "$DST_DIR/auto-deploy-services.conf" "$SRC_CONF" || true
echo
read -r -p "Proceed with promotion? [y/N] " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
  echo "Aborted." >&2
  exit 1
fi

install -o root -g root -m 750 "$SRC_SCRIPT" "$DST_DIR/scoped-restart.sh"
install -o root -g root -m 640 "$SRC_CONF" "$DST_DIR/auto-deploy-services.conf"
bash -n "$DST_DIR/scoped-restart.sh"
echo "Promoted. Note: the source file's own header banner (marking it source-only) is now also present in the enforced copy's comments — harmless, it's just a comment."
