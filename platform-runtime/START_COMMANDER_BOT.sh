#!/bin/bash
# DEPRECATED DUPLICATE:
# Canonical launcher lives at USS-TJR-Control/scripts/start-commander.sh.
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$DIR/START_BOT_WITH_RESEARCH.sh" commander
