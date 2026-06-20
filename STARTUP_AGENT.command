#!/bin/bash
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTROL_ROOT="$SCRIPT_DIR/USS-TJR-Control"
COMMAND_CENTER="$SCRIPT_DIR/core/command-centre"
LOG_DIR="$CONTROL_ROOT/logs/startup"
MASTER_LOG="$LOG_DIR/startup-agent.log"
TIMESTAMP="$(date +"%Y-%m-%d_%H-%M-%S")"
STARTUP_MODE="${STARTUP_AGENT_MODE:-auto}"

mkdir -p "$LOG_DIR"
touch "$MASTER_LOG"

log() {
  printf '%s %s\n' "[$(date +"%Y-%m-%d %H:%M:%S")]" "$*" | tee -a "$MASTER_LOG"
}

run_in_terminal() {
  local title="$1"
  local command="$2"

  if command -v osascript >/dev/null 2>&1; then
    osascript <<APPLESCRIPT >/dev/null 2>&1
tell application "Terminal"
  activate
  do script "$command"
  set custom title of selected tab of front window to "$title"
end tell
APPLESCRIPT
    return 0
  fi

  return 1
}

run_in_tmux() {
  local session_name="usstjr-startup"
  local commander_cmd="cd '$SCRIPT_DIR' && ./START_COMMANDER_BOT.sh"
  local engineering_cmd="cd '$SCRIPT_DIR' && ./START_ENGINEERING_BOT.sh"
  local command_center_cmd="cd '$COMMAND_CENTER' && docker compose up -d"

  if ! command -v tmux >/dev/null 2>&1; then
    return 1
  fi

  if tmux has-session -t "$session_name" 2>/dev/null; then
    log "tmux session '$session_name' already exists; attaching."
    exec tmux attach-session -t "$session_name"
  fi

  tmux new-session -d -s "$session_name" -n "Startup" "$commander_cmd >> '$LOG_DIR/commander-$TIMESTAMP.log' 2>&1"
  tmux rename-window -t "$session_name:0" "Commander"
  tmux split-window -h -t "$session_name:0" "$engineering_cmd >> '$LOG_DIR/engineering-$TIMESTAMP.log' 2>&1"
  tmux select-pane -t "$session_name:0.0" -T "Commander"
  tmux select-pane -t "$session_name:0.1" -T "Engineering"
  tmux split-window -v -t "$session_name:0.0" "$command_center_cmd >> '$LOG_DIR/command-centre-$TIMESTAMP.log' 2>&1"
  tmux select-pane -t "$session_name:0.2" -T "Command Centre"
  tmux select-layout -t "$session_name:0" tiled >/dev/null
  tmux setw -t "$session_name:0" pane-border-status top >/dev/null
  log "Created tmux session '$session_name'."
  exec tmux attach-session -t "$session_name"
}

start_background() {
  local title="$1"
  local command="$2"
  local log_file="$3"

  (
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] Starting $title"
    bash -lc "$command"
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] $title exited with $?"
  ) >> "$log_file" 2>&1 &
}

command_one="cd '$SCRIPT_DIR' && ./START_COMMANDER_BOT.sh | tee -a '$LOG_DIR/commander-$TIMESTAMP.log'"
command_two="cd '$SCRIPT_DIR' && ./START_ENGINEERING_BOT.sh | tee -a '$LOG_DIR/engineering-$TIMESTAMP.log'"
command_three="cd '$COMMAND_CENTER' && docker compose up -d | tee -a '$LOG_DIR/command-centre-$TIMESTAMP.log'"

log "Startup agent beginning."
log "Repository root: $SCRIPT_DIR"
log "Master log: $MASTER_LOG"
log "Command centre: $COMMAND_CENTER"
log "Requested mode: $STARTUP_MODE"

if [ "$STARTUP_MODE" = "tmux" ]; then
  log "Using tmux mode."
  if run_in_tmux; then
    exit 0
  fi
  log "tmux mode failed; falling back."
elif [ "$STARTUP_MODE" = "terminals" ] || [ "$STARTUP_MODE" = "auto" ]; then
  if run_in_terminal "Commander Bot" "$command_one" && \
     run_in_terminal "Engineering Bot" "$command_two" && \
     run_in_terminal "Command Centre" "$command_three"; then
    log "Opened Terminal tabs for Commander Bot, Engineering Bot, and Command Centre."
    log "Per-service logs are in $LOG_DIR."
    exit 0
  fi
  log "Terminal automation unavailable; trying tmux."
  if run_in_tmux; then
    exit 0
  fi
fi

log "Terminal automation unavailable; falling back to background execution."
start_background "Commander Bot" "cd '$SCRIPT_DIR' && ./START_COMMANDER_BOT.sh" "$LOG_DIR/commander-$TIMESTAMP.log"
start_background "Engineering Bot" "cd '$SCRIPT_DIR' && ./START_ENGINEERING_BOT.sh" "$LOG_DIR/engineering-$TIMESTAMP.log"
start_background "Command Centre" "cd '$COMMAND_CENTER' && docker compose up -d" "$LOG_DIR/command-centre-$TIMESTAMP.log"

log "Background startup launched."
log "Per-service logs are in $LOG_DIR."
