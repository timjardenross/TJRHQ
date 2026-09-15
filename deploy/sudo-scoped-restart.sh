#!/usr/bin/env bash
# Single-executable shim for auto-deploy.sh's $SYSTEMCTL override point —
# "$SYSTEMCTL" restart "$svc" is quoted, so AUTO_DEPLOY_SYSTEMCTL must be
# one file, not "sudo scoped-restart.sh" as two words. See
# deploy/scoped-restart.sh for the actual allowlist check (that file is
# the human-reviewed SOURCE; sudo actually trusts and executes the
# promoted copy at /opt/deploy-guard/scoped-restart.sh — see its header
# and deploy/sync-deploy-guard.sh for why they're no longer the same
# file).
set -euo pipefail
exec sudo /opt/deploy-guard/scoped-restart.sh "$@"
