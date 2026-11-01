#!/usr/bin/env bash
# Resilience Crosswalk Bot — local startup script (production uses
# deploy/tg-resiliencebot.service). Run from repo root:
#   bash telegram-bots/resiliencebot/start.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BOT_DIR="$SCRIPT_DIR"

VENV="$BOT_DIR/.venv"
if [ ! -d "$VENV" ]; then
    echo "[resiliencebot] Creating virtualenv…"
    python3 -m venv "$VENV"
fi

source "$VENV/bin/activate"
pip install -q -r "$BOT_DIR/requirements.txt"

if [ ! -f "$BOT_DIR/.env" ]; then
    echo "[resiliencebot] ERROR: $BOT_DIR/.env not found"
    echo "Copy .env.example and fill in TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"
    exit 1
fi

echo "[resiliencebot] Bot online."
cd "$REPO_ROOT"
python -m telegram_bots.resiliencebot.app
