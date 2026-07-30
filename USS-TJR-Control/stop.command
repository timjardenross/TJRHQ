#!/bin/bash
set -u

SESSION_NAME="usstjr"

echo "Stopping USS TJR Control Deck..."

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is not installed. No session can be running."
  exit 0
fi

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  tmux kill-session -t "$SESSION_NAME"
  echo "Stopped tmux session '$SESSION_NAME'."
else
  echo "No tmux session named '$SESSION_NAME' is running."
fi
