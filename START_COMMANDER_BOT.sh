#!/bin/bash
# DEPRECATED DUPLICATE:
# Canonical launcher lives at USS-TJR-Control/scripts/start-commander.sh.
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$SCRIPT_DIR/USS-TJR-Control/scripts/start-commander.sh"
