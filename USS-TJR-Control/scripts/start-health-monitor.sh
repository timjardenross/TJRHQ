#!/bin/bash
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTROL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$CONTROL_ROOT/.." && pwd)"
CONFIG_FILE="$CONTROL_ROOT/config/services.conf"
LOG_FILE="$CONTROL_ROOT/logs/health-monitor.log"

touch "$LOG_FILE"

if [ -f "$CONFIG_FILE" ]; then
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"
else
  echo "Missing config file: $CONFIG_FILE"
  read -r -p "Press Enter to keep this pane open..."
  exit 1
fi

echo "========================================"
echo "USS TJR Control Deck - Health Monitor"
echo "========================================"
echo "Log: $LOG_FILE"
echo "Project root: $PROJECT_ROOT"
echo ""

if command -v "$HEALTH_MONITOR_TOOL" >/dev/null 2>&1; then
  echo "Starting configured health monitor: $HEALTH_MONITOR_TOOL"
  "$HEALTH_MONITOR_TOOL" 2>&1 | tee -a "$LOG_FILE"
elif command -v btop >/dev/null 2>&1; then
  echo "Starting btop"
  btop 2>&1 | tee -a "$LOG_FILE"
elif command -v htop >/dev/null 2>&1; then
  echo "Starting htop"
  htop 2>&1 | tee -a "$LOG_FILE"
else
  echo "btop/htop not found. Starting simple local watch loop."
  while true; do
    clear
    date
    echo ""
    echo "tmux sessions:"
    tmux ls 2>/dev/null || echo "No tmux sessions found"
    echo ""
    echo "Listening ports:"
    lsof -i -P -n | grep LISTEN || true
    sleep 5
  done 2>&1 | tee -a "$LOG_FILE"
fi

echo ""
echo "Health monitor exited."
read -r -p "Press Enter to keep this pane open..."
