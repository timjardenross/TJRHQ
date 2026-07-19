#!/bin/bash
# USS TJR Control Deck — Status Check
# MSN-0013: Enhanced with real process health and port-listening checks.
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/config/services.conf"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Print a status line: symbol, label, detail
_status() {
  local symbol="$1" label="$2" detail="$3"
  printf "  %s %s|%s\n" "$symbol" "$label" "$detail"
}

_ok()   { _status "✅" "$1" "$2"; }
_warn() { _status "⚠️ " "$1" "$2"; }
_fail() { _status "❌" "$1" "$2"; }
_info() { _status "ℹ️ " "$1" "$2"; }

# Check if a process matching a pattern is running
_proc_running() {
  pgrep -f "$1" >/dev/null 2>&1
}

# Check if a port is listening (lsof, fallback nc)
_port_listening() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -i ":${port}" -sTCP:LISTEN >/dev/null 2>&1
  else
    nc -z 127.0.0.1 "$port" >/dev/null 2>&1
  fi
}

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   USS TJR Control Deck — Status Report   ║"
printf "║   %-40s ║\n" "$(date '+%Y-%m-%d %H:%M:%S')"
echo "╚══════════════════════════════════════════╝"
echo ""

# ---------------------------------------------------------------------------
# Load config
# ---------------------------------------------------------------------------

if [ -f "$CONFIG_FILE" ]; then
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"
  CONFIG_OK=true
else
  echo "[ERROR] Missing config file: $CONFIG_FILE"
  CONFIG_OK=false
fi


# ---------------------------------------------------------------------------
# Service health (process + port)
# ---------------------------------------------------------------------------

echo "── SERVICE HEALTH ──────────────────────────"

# Slack Bot: process match on "app.py" (Python or python — macOS bundle uses capital P)
if _proc_running "[Pp]ython.*app\.py"; then
  _ok "Slack Bot" "process running"
else
  _fail "Slack Bot" "process not found"
fi

# Ngrok tunnel: Slack needs this to receive inbound events
if [ "${CONFIG_OK}" = true ] && _port_listening "${NGROK_PORT:-3100}"; then
  _ok "Ngrok Tunnel" "port ${NGROK_PORT:-3100} listening"
else
  _warn "Ngrok Tunnel" "port ${NGROK_PORT:-3100} not listening"
fi

# Commander bot: same app.py binary as all bots — check for 2+ instances (both profiles running)
_bot_count=$(pgrep -f "[Pp]ython.*app\.py" 2>/dev/null | wc -l | tr -d ' ')
if [ "${_bot_count}" -ge 2 ]; then
  _ok "Bot Instances" "${_bot_count} running (commander + engineering)"
elif [ "${_bot_count}" -eq 1 ]; then
  _warn "Bot Instances" "1 running — only one profile active"
else
  _warn "Bot Instances" "none running"
fi

# Ollama: local LLM inference
if _proc_running "ollama"; then
  _ok "Ollama LLM" "process running"
elif command -v ollama >/dev/null 2>&1; then
  _warn "Ollama LLM" "installed but not running — run: ollama serve"
else
  _warn "Ollama LLM" "not installed — LLM fallback active"
fi

# Paperclip: port 3100
if [ "${CONFIG_OK}" = true ] && _port_listening "${PAPERCLIP_PORT:-3100}"; then
  _ok "Paperclip" "port ${PAPERCLIP_PORT:-3100} listening"
else
  _info "Paperclip" "not running (optional)"
fi

# Health monitor: btop or htop process
if _proc_running "btop"; then
  _ok "Health Monitor" "btop running"
elif _proc_running "htop"; then
  _ok "Health Monitor" "htop running"
else
  _info "Health Monitor" "not running"
fi

echo ""

# ---------------------------------------------------------------------------
# Supabase connectivity
# ---------------------------------------------------------------------------

echo "── SUPABASE ────────────────────────────────"
SLACK_BOT_ENV="${SLACK_BOT_DIR:-.}/.env"
if [ -f "$SLACK_BOT_ENV" ]; then
  # Extract SUPABASE_URL without printing its value
  SUPA_URL=$(grep -m1 '^SUPABASE_URL=' "$SLACK_BOT_ENV" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'")
  if [ -n "$SUPA_URL" ]; then
    # Attempt a lightweight HTTP HEAD to check reachability (not authenticated)
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 4 "$SUPA_URL/rest/v1/" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "401" ] || [ "$HTTP_CODE" = "403" ]; then
      _ok "Supabase" "reachable (HTTP $HTTP_CODE)"
    elif [ "$HTTP_CODE" = "000" ]; then
      _fail "Supabase" "unreachable — check network"
    else
      _warn "Supabase" "HTTP $HTTP_CODE — check SUPABASE_URL in .env"
    fi
  else
    _warn "Supabase" "SUPABASE_URL not set in .env"
  fi
else
  _warn "Supabase" ".env not found"
fi
echo ""

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

echo "── TOOLS ───────────────────────────────────"
if command -v ngrok >/dev/null 2>&1; then
  _ok "ngrok" "installed"
else
  _fail "ngrok" "not installed"
fi
if command -v jq >/dev/null 2>&1; then
  _ok "jq" "installed"
else
  _fail "jq" "not installed"
fi
if command -v curl >/dev/null 2>&1; then
  _ok "curl" "installed"
else
  _fail "curl" "not installed"
fi
if command -v btop >/dev/null 2>&1; then
  _ok "System Monitor" "btop installed"
elif command -v htop >/dev/null 2>&1; then
  _ok "System Monitor" "htop installed"
else
  _warn "System Monitor" "btop/htop not installed"
fi
echo ""

# ---------------------------------------------------------------------------
# Configured paths
# ---------------------------------------------------------------------------

echo "── CONFIGURED PATHS ────────────────────────"
if [ "$CONFIG_OK" = true ]; then
  declare -A dir_labels=([SLACK_BOT_DIR]="Slack Bot Path" [COMMANDER_DIR]="Commander Path" [PAPERCLIP_DIR]="Paperclip Path")
  for dir_var in SLACK_BOT_DIR COMMANDER_DIR PAPERCLIP_DIR; do
    dir_val="${!dir_var:-not set}"
    label="${dir_labels[$dir_var]}"
    if [ "$dir_val" = "not set" ]; then
      _warn "$label" "not set in config"
    elif [ -d "$dir_val" ]; then
      _ok "$label" "found"
    else
      _fail "$label" "path not found"
    fi
  done
else
  echo "  (config file missing — paths unavailable)"
fi
echo ""

echo "────────────────────────────────────────────"
echo "  Run start.command to start the Control Deck."
echo "  Run restart.command to restart all services."
echo ""
