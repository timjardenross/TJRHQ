#!/bin/bash
# USS TJR Control Deck — Commander Bot startup script.
# Commander runs the same app.py codebase as the main Slack Bot but uses
# .env.commander to load the Commander Bot's own token pair.
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTROL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$CONTROL_ROOT/.." && pwd)"
CONFIG_FILE="$CONTROL_ROOT/config/services.conf"
LOG_FILE="$CONTROL_ROOT/logs/commander.log"

mkdir -p "$(dirname "$LOG_FILE")"
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
if [ -z "${COMMANDER_DIR:-}" ] || [ ! -d "${COMMANDER_DIR:-/dev/null}" ]; then
  COMMANDER_DIR="$REPO_ROOT/platform-runtime"
fi

echo "========================================"
echo "USS TJR Control Deck — Commander Bot"
echo "========================================"
echo "Log: $LOG_FILE"
echo "Working directory: $COMMANDER_DIR"
echo ""

# --- Pre-flight checks -------------------------------------------------------

if [ ! -d "$COMMANDER_DIR" ]; then
  echo "[ERROR] Commander directory not found: $COMMANDER_DIR"
  echo "        Check REPO_ROOT and COMMANDER_DIR in config/services.conf."
  read -r -p "Press Enter to keep this pane open..."
  exit 1
fi

VENV_ACTIVATE="$COMMANDER_DIR/.venv/bin/activate"
if [ ! -f "$VENV_ACTIVATE" ]; then
  echo "[ERROR] Python venv not found: $VENV_ACTIVATE"
  echo "        Run: cd $COMMANDER_DIR && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  read -r -p "Press Enter to keep this pane open..."
  exit 1
fi

# Commander uses .env.commander (separate token pair from the main Slack Bot)
ENV_FILE="$COMMANDER_DIR/.env.commander"
if [ ! -f "$ENV_FILE" ]; then
  echo "[ERROR] .env.commander not found: $ENV_FILE"
  echo "        Populate $ENV_FILE with SLACK_BOT_TOKEN and SLACK_APP_TOKEN for the Commander Bot."
  read -r -p "Press Enter to keep this pane open..."
  exit 1
fi

APP_SCRIPT="$COMMANDER_DIR/app.py"
if [ ! -f "$APP_SCRIPT" ]; then
  echo "[ERROR] app.py not found at $APP_SCRIPT"
  read -r -p "Press Enter to keep this pane open..."
  exit 1
fi

# --- Launch ------------------------------------------------------------------

cd "$COMMANDER_DIR" || exit 1

echo "Starting Commander Bot..."
echo "  venv:   $VENV_ACTIVATE"
echo "  env:    $ENV_FILE"
echo "  cmd:    python app.py"
echo ""

(
  # shellcheck disable=SC1090
  source "$VENV_ACTIVATE"
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  export PYTHONPATH="${PROJECT_ROOT}:${COMMANDER_DIR}:${PYTHONPATH:-}"
  bash -c "python app.py"
) 2>&1 | tee -a "$LOG_FILE"

EXIT_CODE="${PIPESTATUS[0]}"
echo ""
if [ "$EXIT_CODE" -eq 0 ]; then
  echo "Commander Bot exited normally (exit 0)."
else
  echo "[WARN] Commander Bot exited with code $EXIT_CODE. Check log: $LOG_FILE"
fi
read -r -p "Press Enter to keep this pane open..."
