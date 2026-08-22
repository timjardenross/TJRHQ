#!/usr/bin/env bash
# Capacity Bot — startup script
# Run from repo root: bash telegram-bots/capacitybot/start.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BOT_DIR="$SCRIPT_DIR"

echo "[capacitybot] Starting from $BOT_DIR"

VENV="$BOT_DIR/.venv"
if [ ! -d "$VENV" ]; then
    echo "[capacitybot] Creating virtualenv…"
    python3 -m venv "$VENV"
fi

source "$VENV/bin/activate"

echo "[capacitybot] Installing requirements…"
pip install -q -r "$BOT_DIR/requirements.txt"

if [ ! -f "$BOT_DIR/.env" ]; then
    echo "[capacitybot] ERROR: $BOT_DIR/.env not found"
    echo "Copy .env.example and fill in TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"
    exit 1
fi

echo "[capacitybot] Bot online."
cd "$REPO_ROOT"
python -m telegram_bots.capacitybot.app
