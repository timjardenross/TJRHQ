#!/usr/bin/env bash
# Engineering Dept Bot — startup script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

VENV="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV" ]; then python3 -m venv "$VENV"; fi
source "$VENV/bin/activate"
pip install -q -r "$SCRIPT_DIR/requirements.txt"

if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "[engineering-dept-bot] ERROR: .env not found"; exit 1
fi

source "$SCRIPT_DIR/.env"
if [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "[engineering-dept-bot] WARNING: TELEGRAM_CHAT_ID not set — send /start to discover it"
fi

echo "[engineering-dept-bot] Online."
cd "$REPO_ROOT"
python -m telegram_bots.engineering-dept.app
