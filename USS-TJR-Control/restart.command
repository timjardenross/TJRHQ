#!/bin/bash
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SESSION_NAME="usstjr"

echo "Restarting USS TJR Control Deck..."

if command -v tmux >/dev/null 2>&1 && tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  tmux kill-session -t "$SESSION_NAME"
  echo "Stopped existing tmux session '$SESSION_NAME'."
else
  echo "No existing tmux session '$SESSION_NAME' found."
fi

sleep 1
echo "Starting new tmux session '$SESSION_NAME'..."
exec "$SCRIPT_DIR/start.command"
