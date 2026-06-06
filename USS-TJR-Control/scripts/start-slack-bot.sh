#!/bin/bash
# USS TJR Control Deck — Slack Bot startup script.
# MSN-0013: Hardened to activate venv, load .env, and set PYTHONPATH.
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTROL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$CONTROL_ROOT/.." && pwd)"
CONFIG_FILE="$CONTROL_ROOT/config/services.conf"
LOG_FILE="$CONTROL_ROOT/logs/slack-bot.log"

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
echo "USS TJR Control Deck - Slack Bot"
echo "========================================"
echo "Log: $LOG_FILE"
echo "Working directory: $SLACK_BOT_DIR"
echo ""

# --- Pre-flight checks -------------------------------------------------------

if [ ! -d "$SLACK_BOT_DIR" ]; then
  echo "[ERROR] Slack Bot directory not found: $SLACK_BOT_DIR"
  echo "        Check REPO_ROOT and SLACK_BOT_DIR in config/services.conf."
  read -r -p "Press Enter to keep this pane open..."
  exit 1
fi

VENV_ACTIVATE="$SLACK_BOT_DIR/.venv/bin/activate"
if [ ! -f "$VENV_ACTIVATE" ]; then
  echo "[ERROR] Python venv not found: $VENV_ACTIVATE"
  echo "        Run: cd $SLACK_BOT_DIR && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  read -r -p "Press Enter to keep this pane open..."
  exit 1
fi

ENV_FILE="$SLACK_BOT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "[ERROR] .env file not found: $ENV_FILE"
  echo "        Copy slack-bot/.env.example to slack-bot/.env and populate secrets."
  read -r -p "Press Enter to keep this pane open..."
  exit 1
fi

# --- Launch ------------------------------------------------------------------

cd "$SLACK_BOT_DIR" || exit 1

echo "Starting Slack Bot..."
echo "  venv:   $VENV_ACTIVATE"
echo "  env:    $ENV_FILE"
echo "  cmd:    $SLACK_BOT_COMMAND"
echo ""

# Activate venv, load .env into environment, set PYTHONPATH, then run.
# SLACK_BOT_COMMAND from services.conf already encodes this sequence;
# this explicit wrapper ensures env is always loaded even if SLACK_BOT_COMMAND
# is overridden to a simpler form.
(
  # shellcheck disable=SC1090
  source "$VENV_ACTIVATE"
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  export PYTHONPATH="${SLACK_BOT_DIR}:${PYTHONPATH:-}"
  bash -c "python app.py"
) 2>&1 | tee -a "$LOG_FILE"

EXIT_CODE="${PIPESTATUS[0]}"
echo ""
if [ "$EXIT_CODE" -eq 0 ]; then
  echo "Slack Bot exited normally (exit 0)."
else
  echo "[WARN] Slack Bot exited with code $EXIT_CODE. Check log: $LOG_FILE"
fi
read -r -p "Press Enter to keep this pane open..."
