#!/usr/bin/env bash
# Wraps a command's startup with a fresh Infisical machine-identity login,
# then runs it with all project secrets injected as env vars.
#
# Why a wrapper and not `infisical run --client-id=... --client-secret=...`
# directly: this CLI version's `run` subcommand only accepts --token (a
# pre-minted access token), not raw Universal Auth credentials — so this
# script mints one via `infisical login` first. The bootstrap credential
# (.infisical-auth.env, chmod 600, root-only) is the one secret that still
# has to live on disk; everything else (Supabase keys, BOT_API_SECRET,
# Google Calendar creds, etc.) now comes from Infisical instead of being
# duplicated across every service's own .env file.
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

TOKEN="$(infisical login --method=universal-auth \
  --client-id="$INFISICAL_UA_CLIENT_ID" \
  --client-secret="$INFISICAL_UA_CLIENT_SECRET" \
  --domain="$DOMAIN" --plain --silent)"

exec infisical run \
  --domain="$DOMAIN" \
  --projectId="$PROJECT_ID" \
  --env="$ENVIRONMENT" \
  --token="$TOKEN" \
  -- "$@"
