#!/bin/bash
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/config/services.conf"
SESSION_NAME="usstjr"

echo "========================================"
echo "USS TJR Control Deck Status"
echo "========================================"
echo ""

if command -v tmux >/dev/null 2>&1; then
  echo "tmux: installed ($(command -v tmux))"
  if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "Session '$SESSION_NAME': running"
  else
    echo "Session '$SESSION_NAME': not running"
  fi
  echo ""
  echo "Current tmux sessions:"
  tmux ls 2>/dev/null || echo "No tmux sessions found"
else
  echo "tmux: not installed"
  echo "Session '$SESSION_NAME': unavailable"
fi

echo ""
if command -v ngrok >/dev/null 2>&1; then
  echo "ngrok: installed ($(command -v ngrok))"
else
  echo "ngrok: not installed"
fi

if command -v jq >/dev/null 2>&1; then
  echo "jq: installed ($(command -v jq))"
else
  echo "jq: not installed"
fi

if command -v btop >/dev/null 2>&1; then
  echo "btop: installed ($(command -v btop))"
elif command -v htop >/dev/null 2>&1; then
  echo "htop: installed ($(command -v htop))"
else
  echo "btop/htop: not installed"
fi

echo ""
echo "Configured service ports:"
if [ -f "$CONFIG_FILE" ]; then
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"
  echo "PAPERCLIP_PORT=${PAPERCLIP_PORT:-not set}"
  echo "NGROK_PORT=${NGROK_PORT:-not set}"
else
  echo "Missing config file: $CONFIG_FILE"
fi

echo ""
echo "Configured service paths:"
if [ -f "$CONFIG_FILE" ]; then
  echo "SLACK_BOT_DIR=${SLACK_BOT_DIR:-not set}"
  echo "COMMANDER_DIR=${COMMANDER_DIR:-not set}"
  echo "PAPERCLIP_DIR=${PAPERCLIP_DIR:-not set}"
fi
