#!/usr/bin/env bash
# Thin wrapper: run the live cycle on the VM as the service user with the xo bot's Infisical environment.
# Usage: tools/ops/run_live_cycle.sh [--dry-run | --drill-missed-brief | ...]   (arguments pass straight through)
set -euo pipefail
ROOT="${STARSHIP_ROOT:-/opt/starship-endeavour}"
cd "$ROOT"
exec "$ROOT/platform-runtime/run-with-infisical-bot.sh" xo -- "$ROOT/platform-runtime/.venv/bin/python" -m tools.ops.run_live_cycle "$@"
