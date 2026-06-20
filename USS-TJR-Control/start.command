#!/bin/bash
# USS TJR Control Deck — Start
# MSN-0013: Added pre-flight summary before handing off to tmux session script.
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/config/services.conf"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "========================================"
echo "USS TJR Control Deck — Starting"
echo "========================================"
echo ""

# Load config for path validation
if [ -f "$CONFIG_FILE" ]; then
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"

  # If the config still points at a machine-specific path, fall back to the
  # repo location derived from this script so the control deck can start on a VM.
  if [ -z "${REPO_ROOT:-}" ] || [ ! -d "${REPO_ROOT:-/dev/null}" ]; then
    REPO_ROOT="$PROJECT_ROOT"
    SLACK_BOT_DIR="$REPO_ROOT/slack-bot"
    COMMANDER_DIR="$REPO_ROOT/slack-bot"
    PAPERCLIP_DIR="$HOME/.paperclip"
  fi

  # Quick pre-flight: warn if critical paths are missing
  ABORT=false

  if [ ! -d "${SLACK_BOT_DIR:-}" ]; then
    echo "[ERROR] Slack Bot directory not found: ${SLACK_BOT_DIR:-SLACK_BOT_DIR not set}"
    echo "        Fix REPO_ROOT in config/services.conf."
    ABORT=true
  fi

  if [ ! -f "${SLACK_BOT_DIR:-/dev/null}/.venv/bin/activate" ]; then
    echo "[ERROR] Python venv missing: ${SLACK_BOT_DIR:-}/.venv"
    echo "        Run: cd ${SLACK_BOT_DIR:-<slack-bot dir>} && python3 -m venv .venv && pip install -r requirements.txt"
    ABORT=true
  fi

  if [ ! -f "${SLACK_BOT_DIR:-/dev/null}/.env" ]; then
    echo "[ERROR] .env missing: ${SLACK_BOT_DIR:-}/.env"
    echo "        Copy slack-bot/.env.example to slack-bot/.env and populate secrets."
    ABORT=true
  fi

  if [ "$ABORT" = true ]; then
    echo ""
    echo "Startup aborted. Fix the errors above, then run start.command again."
    read -r -p "Press Enter to close..."
    exit 1
  fi

  echo "  Repo root:     ${REPO_ROOT:-$SCRIPT_DIR/..}"
  echo "  Slack Bot:     $SLACK_BOT_DIR"
  echo "  Commander:     $COMMANDER_DIR"
  echo "  Paperclip:     ${PAPERCLIP_DIR} (optional)"
  echo ""
else
  echo "[WARN] Config file not found: $CONFIG_FILE"
  echo "       Proceeding — individual scripts will report missing config."
  echo ""
fi

echo "Launching tmux session..."
echo ""
exec "$SCRIPT_DIR/tmux/usstjr-session.sh"
