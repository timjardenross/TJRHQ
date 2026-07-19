#!/bin/bash
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Starting USS TJR Control Deck..."
echo "Control directory: $SCRIPT_DIR"
echo ""

exec "$SCRIPT_DIR/tmux/usstjr-session.sh"
