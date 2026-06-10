#!/bin/bash
# USS TJR Control Deck — Paperclip startup script.
# MSN-0013: Graceful startup with PAPERCLIP_ENABLED guard.
#
# Paperclip is a local project management server (port 3100).
# Status: OPTIONAL — system operates without Paperclip.
# To suppress this pane at startup, set PAPERCLIP_ENABLED=false in slack-bot/.env.
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTROL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$CONTROL_ROOT/.." && pwd)"
CONFIG_FILE="$CONTROL_ROOT/config/services.conf"
LOG_FILE="$CONTROL_ROOT/logs/paperclip.log"

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

# Load .env for PAPERCLIP_ENABLED flag (best-effort — don't fail if missing)
ENV_FILE="$PROJECT_ROOT/slack-bot/.env"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

echo "========================================"
echo "USS TJR Control Deck - Paperclip"
echo "========================================"
echo "Log: $LOG_FILE"
echo "Configured port: ${PAPERCLIP_PORT:-3100}"
echo ""

# --- PAPERCLIP_ENABLED guard -------------------------------------------------

PAPERCLIP_ENABLED="${PAPERCLIP_ENABLED:-true}"
if [ "$PAPERCLIP_ENABLED" = "false" ]; then
  echo "Paperclip is disabled (PAPERCLIP_ENABLED=false in .env)."
  echo "This pane will remain open but Paperclip will not start."
  echo "USS TJR systems that depend on Paperclip will operate in fallback mode."
  read -r -p "Press Enter to keep this pane open..."
  exit 0
fi

# --- Pre-flight checks -------------------------------------------------------

if [ ! -d "$PAPERCLIP_DIR" ]; then
  echo "[WARN] Paperclip directory not found: $PAPERCLIP_DIR"
  echo ""
  echo "Paperclip is an OPTIONAL service. The USS TJR system operates without it."
  echo "To suppress this message, set PAPERCLIP_ENABLED=false in slack-bot/.env."
  echo ""
  echo "To install and configure Paperclip:"
  echo "  1. Install the Paperclip server binary."
  echo "  2. Update PAPERCLIP_DIR and PAPERCLIP_COMMAND in config/services.conf."
  read -r -p "Press Enter to keep this pane open..."
  exit 1
fi

# --- Launch ------------------------------------------------------------------

cd "$PAPERCLIP_DIR" || exit 1

echo "Starting Paperclip: $PAPERCLIP_COMMAND"
echo "Working directory: $(pwd)"
echo ""

bash -lc "$PAPERCLIP_COMMAND" 2>&1 | tee -a "$LOG_FILE"

EXIT_CODE="${PIPESTATUS[0]}"
echo ""
if [ "$EXIT_CODE" -eq 0 ]; then
  echo "Paperclip exited normally (exit 0)."
else
  echo "[WARN] Paperclip exited with code $EXIT_CODE. Check log: $LOG_FILE"
  echo "       Paperclip is OPTIONAL. Other USS TJR services are unaffected."
fi
read -r -p "Press Enter to keep this pane open..."
