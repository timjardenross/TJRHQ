#!/bin/bash
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTROL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$CONTROL_ROOT/.." && pwd)"
CONFIG_FILE="$CONTROL_ROOT/config/services.conf"
LOG_FILE="$CONTROL_ROOT/logs/ngrok.log"

touch "$LOG_FILE"

if [ -f "$CONFIG_FILE" ]; then
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"
else
  echo "Missing config file: $CONFIG_FILE"
  read -r -p "Press Enter to keep this pane open..."
  exit 1
fi

if [ -z "${REPO_ROOT:-}" ] || [ ! -d "${REPO_ROOT:-/dev/null}" ]; then
  REPO_ROOT="$PROJECT_ROOT"
fi

echo "========================================"
echo "USS TJR Control Deck - NGROK Tunnel"
echo "========================================"
echo "Log: $LOG_FILE"
echo "Project root: $PROJECT_ROOT"
echo ""
echo "NGROK exposes a local service externally. Only run this when needed."
echo "Configured local port: $NGROK_PORT"
echo ""

if ! command -v ngrok >/dev/null 2>&1; then
  echo "ngrok is not installed or is not on PATH."
  echo "Install ngrok and authenticate locally with:"
  echo "ngrok config add-authtoken <token>"
  echo "Do not store ngrok tokens in this repository."
  read -r -p "Press Enter to keep this pane open..."
  exit 1
fi

echo "Starting ngrok: ngrok http $NGROK_PORT"
echo ""

# NGROK_COMMAND is configurable, but defaults to: ngrok http ${NGROK_PORT}
bash -lc "$NGROK_COMMAND" 2>&1 | tee -a "$LOG_FILE"
echo ""
echo "ngrok exited."
read -r -p "Press Enter to keep this pane open..."
