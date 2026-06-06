#!/bin/bash
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTROL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$CONTROL_ROOT/.." && pwd)"
CONFIG_FILE="$CONTROL_ROOT/config/services.conf"
LOG_FILE="$CONTROL_ROOT/logs/commander.log"

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
echo "USS TJR Control Deck - Commander"
echo "========================================"
echo "Log: $LOG_FILE"
echo "Project root: $PROJECT_ROOT"
echo ""

if [ ! -d "$COMMANDER_DIR" ]; then
  echo "Commander directory not found: $COMMANDER_DIR"
  echo "Update config/services.conf with the correct path and command."
  read -r -p "Press Enter to keep this pane open..."
  exit 1
fi

cd "$COMMANDER_DIR" || exit 1
echo "Starting Commander: $COMMANDER_COMMAND"
echo "Working directory: $(pwd)"
echo ""

# Replace COMMANDER_COMMAND in config/services.conf when the real command changes.
bash -lc "$COMMANDER_COMMAND" 2>&1 | tee -a "$LOG_FILE"
echo ""
echo "Commander exited."
read -r -p "Press Enter to keep this pane open..."
