#!/usr/bin/env bash
# REVS Bot — startup script (local/manual run, not the systemd path).
# Run from repo root: bash telegram-bots/revs/start.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BOT_DIR="$SCRIPT_DIR"

echo "[revs-bot] Starting from $BOT_DIR"

VENV="$BOT_DIR/.venv"
if [ ! -d "$VENV" ]; then
    echo "[revs-bot] Creating virtualenv…"
    python3 -m venv "$VENV"
fi

source "$VENV/bin/activate"

echo "[revs-bot] Installing requirements…"
pip install -q -r "$BOT_DIR/requirements.txt"

if [ ! -f "$BOT_DIR/.env" ]; then
    echo "[revs-bot] ERROR: $BOT_DIR/.env not found"
    echo "Copy .env.example and fill in TELEGRAM_BOT_TOKEN"
    exit 1
fi

if [ ! -f "$REPO_ROOT/platform-runtime/.env" ]; then
    echo "[revs-bot] WARNING: $REPO_ROOT/platform-runtime/.env not found — SUPABASE_URL/ANON_KEY/JWT_SECRET must come from somewhere."
fi

echo "[revs-bot] Bot online."
cd "$REPO_ROOT"
python -m telegram_bots.revs.app
