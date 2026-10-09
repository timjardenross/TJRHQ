#!/usr/bin/env bash
# Per-bot variant of run-with-infisical.sh.
#
# Why this exists: Infisical's "prod" environment is one flat namespace —
# one value per key name. Several Telegram bots each need their own
# distinct TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (confirmed different real
# values per bot, not just different var names), which a flat namespace
# can't hold. Each bot's divergent keys live in their own Infisical folder
# (/bots/xo, /bots/revs, /bots/capacitybot) instead; this script fetches
# root (shared: SUPABASE_*, OLLAMA_*, EMBEDDING_PROVIDER, etc.) first, then
# the bot's own folder second so its keys win on any name collision — same
# override semantics the old two-file EnvironmentFile= layering had
# (platform-runtime/.env first, bot's own .env second).
#
# This CLI's `run` subcommand only fetches one --path, no merge across
# paths — so this script does two `infisical export` calls and sources
# them in order, rather than one `infisical run`.
#
# Usage: run-with-infisical-bot.sh <bot-name> -- <command> [args...]

set -euo pipefail

BOT="$1"
shift
if [ "${1:-}" = "--" ]; then
  shift
fi

AUTH_FILE="$(dirname "$0")/.infisical-auth.env"
DOMAIN="http://127.0.0.1:8446/api"
PROJECT_ID="53c88035-a1eb-44b3-ab03-3d3a8899748c"
ENVIRONMENT="prod"

if [ ! -f "$AUTH_FILE" ]; then
  echo "run-with-infisical-bot.sh: missing $AUTH_FILE" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$AUTH_FILE"

# shellcheck disable=SC1091
source "$(dirname "$0")/lib-infisical.sh"
# Fail loudly instead of running the bot with no secrets (see lib-infisical.sh):
# the old `export X="$(...)"` and `source <(...)` forms swallowed every failure.
infisical_wait_ready
infisical_login
set -a
infisical_source_path "/" "$PROJECT_ID" "$ENVIRONMENT"
# The bot's own folder is what carries its TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID,
# so an empty folder means a misconfigured bot, not "nothing to override".
infisical_source_path "/bots/$BOT" "$PROJECT_ID" "$ENVIRONMENT" required
set +a
exec "$@"
