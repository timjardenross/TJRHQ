#!/bin/bash
# DEPRECATED DUPLICATE:
# Canonical launchers live at USS-TJR-Control/scripts/.
# Start both Slack bots in a single terminal.
# Each bot runs as a subprocess with its own isolated environment.
# Output is prefixed: [BOT] for the main bot, [CMD] for Commander.
# Ctrl+C kills both cleanly.

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

VENV="$SCRIPT_DIR/.venv/bin/activate"
ENV_BOT="$SCRIPT_DIR/.env"
ENV_CMD="$SCRIPT_DIR/.env.commander"

# --- Pre-flight --------------------------------------------------------------

if [ ! -f "$VENV" ]; then
  echo "[ERROR] venv not found: $VENV"
  echo "        Run: cd slack-bot && python3 -m venv .venv && pip install -r requirements.txt"
  exit 1
fi

if [ ! -f "$ENV_BOT" ]; then
  echo "[ERROR] .env not found: $ENV_BOT"
  exit 1
fi

if [ ! -f "$ENV_CMD" ]; then
  echo "[ERROR] .env.commander not found: $ENV_CMD"
  exit 1
fi

# --- Launch ------------------------------------------------------------------

echo "========================================"
echo "USS TJR — Slack Bots"
echo "========================================"
echo "  [BOT] Main bot    → .env"
echo "  [CMD] Commander   → .env.commander"
echo "  Ctrl+C stops both"
echo "========================================"
echo ""

# Each subshell sources its own env file — no variable leakage between bots.
(
  source "$VENV"
  set -a; source "$ENV_BOT"; set +a
  export PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}"
  cd "$SCRIPT_DIR"
  python app.py 2>&1
) | sed -u 's/^/[BOT] /' &
PID_BOT=$!

(
  source "$VENV"
  set -a; source "$ENV_CMD"; set +a
  export PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}"
  cd "$SCRIPT_DIR"
  python app.py 2>&1
) | sed -u 's/^/[CMD] /' &
PID_CMD=$!

# Kill both on Ctrl+C or if either process exits
cleanup() {
  echo ""
  echo "Stopping bots..."
  kill "$PID_BOT" "$PID_CMD" 2>/dev/null
  wait "$PID_BOT" "$PID_CMD" 2>/dev/null
  echo "Stopped."
}
trap cleanup EXIT INT TERM

wait "$PID_BOT" "$PID_CMD"
