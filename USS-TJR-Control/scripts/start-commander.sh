#!/bin/bash
# USS TJR Control Deck — Commander startup script.
# MSN-0013: Hardened to activate venv, load .env, and set PYTHONPATH.
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

echo "========================================"
echo "USS TJR Control Deck - Commander"
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

# Commander shares the slack-bot venv
VENV_ACTIVATE="$COMMANDER_DIR/.venv/bin/activate"
if [ ! -f "$VENV_ACTIVATE" ]; then
  echo "[ERROR] Python venv not found: $VENV_ACTIVATE"
  echo "        Run: cd $COMMANDER_DIR && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  read -r -p "Press Enter to keep this pane open..."
  exit 1
fi

ENV_FILE="$COMMANDER_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "[ERROR] .env file not found: $ENV_FILE"
  echo "        Copy slack-bot/.env.example to slack-bot/.env and populate secrets."
  read -r -p "Press Enter to keep this pane open..."
  exit 1
fi

COMMANDER_SCRIPT="$COMMANDER_DIR/commander.py"
if [ ! -f "$COMMANDER_SCRIPT" ]; then
  echo "[WARN] commander.py not found at $COMMANDER_SCRIPT"
  echo "       The Commander service may not be implemented yet."
  read -r -p "Press Enter to keep this pane open..."
  exit 1
fi

# --- Launch ------------------------------------------------------------------

cd "$COMMANDER_DIR" || exit 1

echo "Starting Commander..."
echo "  venv:   $VENV_ACTIVATE"
echo "  env:    $ENV_FILE"
echo "  cmd:    python commander.py"
echo ""

(
  # shellcheck disable=SC1090
  source "$VENV_ACTIVATE"
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  export PYTHONPATH="${COMMANDER_DIR}:${PYTHONPATH:-}"
  bash -c "python commander.py"
) 2>&1 | tee -a "$LOG_FILE"

EXIT_CODE="${PIPESTATUS[0]}"
echo ""
if [ "$EXIT_CODE" -eq 0 ]; then
  echo "Commander exited normally (exit 0)."
else
  echo "[WARN] Commander exited with code $EXIT_CODE. Check log: $LOG_FILE"
fi
read -r -p "Press Enter to keep this pane open..."
