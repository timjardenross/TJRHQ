#!/usr/bin/env bash
# XO Bot — startup script
# Run from repo root: bash telegram-bots/xo/start.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BOT_DIR="$SCRIPT_DIR"

echo "[xo-bot] Starting from $BOT_DIR"

# Virtualenv
VENV="$BOT_DIR/.venv"
if [ ! -d "$VENV" ]; then
    echo "[xo-bot] Creating virtualenv…"
    python3 -m venv "$VENV"
fi

source "$VENV/bin/activate"

echo "[xo-bot] Installing requirements…"
pip install -q -r "$BOT_DIR/requirements.txt"

# Confirm .env exists
if [ ! -f "$BOT_DIR/.env" ]; then
    echo "[xo-bot] ERROR: $BOT_DIR/.env not found"
    echo "Copy .env.example and fill in TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"
    exit 1
fi

# Confirm TELEGRAM_CHAT_ID is set
source "$BOT_DIR/.env"
if [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "[xo-bot] WARNING: TELEGRAM_CHAT_ID not set in .env"
    echo "Send /start to @Starship_endeavour_xO_bot to get your chat ID, then update .env"
    echo ""
    echo "Starting bot anyway — use /start to discover chat ID…"
fi

echo "[xo-bot] Bot online."
cd "$REPO_ROOT"
python -m telegram_bots.xo.app
