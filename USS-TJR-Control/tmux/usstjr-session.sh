#!/bin/bash
set -u

SESSION_NAME="usstjr"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTROL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is not installed."
  echo "Install tmux first, for example: brew install tmux"
  read -r -p "Press Enter to exit..."
  exit 1
fi

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  echo "tmux session '$SESSION_NAME' already exists. Attaching..."
  exec tmux attach-session -t "$SESSION_NAME"
fi

SLACK_PANE="$(tmux new-session -d -s "$SESSION_NAME" -n "Control Deck" -P -F "#{pane_id}" "$CONTROL_ROOT/scripts/start-slack-bot.sh")"
tmux rename-window -t "$SESSION_NAME:0" "USS TJR"
tmux select-pane -t "$SLACK_PANE" -T "Slack Bot"

COMMANDER_PANE="$(tmux split-window -h -t "$SLACK_PANE" -P -F "#{pane_id}" "$CONTROL_ROOT/scripts/start-commander.sh")"
tmux select-pane -t "$COMMANDER_PANE" -T "Commander"

PAPERCLIP_PANE="$(tmux split-window -v -t "$SLACK_PANE" -P -F "#{pane_id}" "$CONTROL_ROOT/scripts/start-paperclip.sh")"
tmux select-pane -t "$PAPERCLIP_PANE" -T "Paperclip"

HEALTH_PANE="$(tmux split-window -v -t "$COMMANDER_PANE" -P -F "#{pane_id}" "$CONTROL_ROOT/scripts/start-health-monitor.sh")"
tmux select-pane -t "$HEALTH_PANE" -T "Health Monitor"

NGROK_PANE="$(tmux split-window -v -t "$COMMANDER_PANE" -P -F "#{pane_id}" "$CONTROL_ROOT/scripts/start-ngrok.sh")"
tmux select-pane -t "$NGROK_PANE" -T "NGROK Tunnel"

tmux select-layout -t "$SESSION_NAME:0" tiled >/dev/null
tmux setw -t "$SESSION_NAME:0" pane-border-status top >/dev/null
tmux select-pane -t "$SLACK_PANE"

echo "Created tmux session '$SESSION_NAME'. Attaching..."
exec tmux attach-session -t "$SESSION_NAME"
