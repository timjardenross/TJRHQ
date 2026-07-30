#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTROL_DIR="$(cd "$SCRIPT_DIR" && pwd)"

echo "Starting USS TJR Control Deck..."
echo "Control directory: $CONTROL_DIR"

cd "$CONTROL_DIR" || {
  echo "ERROR: Could not find USS-TJR-Control at: $CONTROL_DIR"
  echo "Press any key to close..."
  read -n 1
  exit 1
}

exec "$CONTROL_DIR/start.command"
