#!/usr/bin/env bash
# Single-executable shim for auto-deploy.sh's $SYSTEMCTL override point —
# "$SYSTEMCTL" restart "$svc" is quoted, so AUTO_DEPLOY_SYSTEMCTL must be
# one file, not "sudo scoped-restart.sh" as two words. See
# deploy/scoped-restart.sh for the actual allowlist check.
set -euo pipefail
exec sudo /opt/starship-endeavour/deploy/scoped-restart.sh "$@"
