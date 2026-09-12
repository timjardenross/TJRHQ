#!/usr/bin/env bash
# Wraps a command's startup with a fresh Infisical machine-identity login,
# then runs it with all project secrets injected as env vars.
#
# STATUS as of USS-TJR-MSN-0371 (2026-09-12): this is now the real, live
# secret source for every deploy/*.service unit that has one plain shared
# set of secrets (repo-wide check: no unit has an active EnvironmentFile=
# pointing at a hand-maintained .env anymore — see the mission's Stream 6
# knowledge record). A handful of services genuinely need nothing here
# (no EnvironmentFile= ever existed for them) and were left alone.
#
# Bots with their OWN distinct secret values under the same key name
# (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID differ per bot) do NOT use this
# script — Infisical's "prod" environment is one flat namespace, one
# value per key, so a single wrapper can't serve three different bots'
# tokens. Those use run-with-infisical-bot.sh instead (root secrets +
# a per-bot Infisical folder override — see that script's own header).
#
# Why a wrapper and not `infisical run --client-id=... --client-secret=...`
# directly: this CLI version's `run` subcommand only accepts --token (a
# pre-minted access token), not raw Universal Auth credentials — so this
# script mints one via `infisical login` first. The bootstrap credential
# (.infisical-auth.env) is the one secret that still has to live on disk —
# root:infisical-readers, chmod 640 (widened from root-only chmod 600 to
# let vm-processing*.service's User=claude read it; see that unit's own
# comment).
#
# Usage: run-with-infisical.sh <command> [args...]

set -euo pipefail

AUTH_FILE="$(dirname "$0")/.infisical-auth.env"
DOMAIN="http://127.0.0.1:8446/api"
PROJECT_ID="53c88035-a1eb-44b3-ab03-3d3a8899748c"
ENVIRONMENT="prod"

if [ ! -f "$AUTH_FILE" ]; then
  echo "run-with-infisical.sh: missing $AUTH_FILE" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$AUTH_FILE"

# Minted token is passed via the INFISICAL_TOKEN env var, not --token=,
# so it never appears in argv (visible to any local user via plain
# `ps aux` / `/proc/<pid>/cmdline`, no root needed). This CLI binds
# --token to that env var name internally; env is still readable via
# /proc/<pid>/environ, but that requires root/same-UID, matching every
# other secret already exposed that way on this host.
export INFISICAL_TOKEN="$(infisical login --method=universal-auth \
  --client-id="$INFISICAL_UA_CLIENT_ID" \
  --client-secret="$INFISICAL_UA_CLIENT_SECRET" \
  --domain="$DOMAIN" --plain --silent)"

exec infisical run \
  --domain="$DOMAIN" \
  --projectId="$PROJECT_ID" \
  --env="$ENVIRONMENT" \
  -- "$@"
