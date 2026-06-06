#!/bin/bash
# USS TJR Control Deck — Restart
# Kills the existing tmux session (if any) then delegates to start.command.
# MSN-0013: Inherits pre-flight validation from start.command.
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SESSION_NAME="usstjr"

echo "========================================"
echo "USS TJR Control Deck — Restarting"
echo "========================================"
echo ""

if command -v tmux >/dev/null 2>&1; then
  if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    tmux kill-session -t "$SESSION_NAME"
    echo "Stopped existing tmux session '$SESSION_NAME'."
  else
    echo "No existing tmux session '$SESSION_NAME' found — starting fresh."
  fi
else
  echo "[WARN] tmux not installed. Install with: brew install tmux"
fi

echo ""
sleep 1
echo "Starting new session..."
echo ""
exec "$SCRIPT_DIR/start.command"
