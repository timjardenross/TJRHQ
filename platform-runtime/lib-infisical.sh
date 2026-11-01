#!/usr/bin/env bash
# Shared helpers for run-with-infisical.sh and run-with-infisical-bot.sh.
# Sourced, not executed. Callers set DOMAIN (e.g. http://127.0.0.1:8446/api).
#
# Why this exists (2026-10-06): after a reboot the Infisical container on :8446
# comes up *after* the units that need it. The old bot wrapper then ran its
# command with NO secrets and no error: `export X="$(infisical login ...)"`
# returns export's status (0), not the login's, and `source <(infisical export
# ...)` ignores the exporter's exit status. intelligence-scheduler therefore ran
# for 11 hours without TELEGRAM_BOT_TOKEN and silently failed to deliver its EOD
# brief. A wrapper must either hand its command real secrets or fail loudly so
# systemd (Restart=) retries; it must never start the command half-configured.

# Block until the Infisical API answers, or fail. Timeout and poll interval are
# overridable (INFISICAL_READY_TIMEOUT / INFISICAL_READY_INTERVAL, seconds).
infisical_wait_ready() {
  local timeout="${INFISICAL_READY_TIMEOUT:-120}" interval="${INFISICAL_READY_INTERVAL:-2}" waited=0
  _INFISICAL_WAIT_STARTED="$SECONDS"   # one time budget for this and infisical_wait_secrets_ready
  until curl -fsS -m 3 -o /dev/null "${DOMAIN}/status" 2>/dev/null; do
    if [ "$waited" -ge "$timeout" ]; then
      echo "infisical: API at ${DOMAIN} not ready after ${timeout}s - refusing to start without secrets" >&2
      return 1
    fi
    sleep "$interval"
    waited=$((waited + interval))
  done
}

# Block until a real secrets export works, or fail. Needs INFISICAL_TOKEN (call after
# infisical_login). Added 2026-10-09 (USS-TJR-MSN-0412 Stream 6): after that day's reboot
# the API answered /status within seconds but returned 404 for the secrets route for
# ~12 minutes, so every unit passed infisical_wait_ready and then died in `infisical
# run`/`export` ("failed to fetch secrets", 530 journal lines in one boot). Probing the
# real operation closes that gap. Backoff: INFISICAL_READY_INTERVAL doubling up to
# INFISICAL_READY_MAX_INTERVAL (default 15 s); shares the INFISICAL_READY_TIMEOUT budget
# with infisical_wait_ready, but always makes at least one attempt.
# usage: infisical_wait_secrets_ready <project-id> <env>
infisical_wait_secrets_ready() {
  local project="$1" env="$2"
  local timeout="${INFISICAL_READY_TIMEOUT:-120}" interval="${INFISICAL_READY_INTERVAL:-2}"
  local max_interval="${INFISICAL_READY_MAX_INTERVAL:-15}"
  local started="${_INFISICAL_WAIT_STARTED:-$SECONDS}"
  until infisical export --domain="$DOMAIN" --projectId="$project" --env="$env" \
          --path=/ --format=dotenv >/dev/null 2>&1; do
    if [ $((SECONDS - started)) -ge "$timeout" ]; then
      echo "infisical: secrets not readable at ${DOMAIN} after ${timeout}s - refusing to start without secrets" >&2
      return 1
    fi
    sleep "$interval"
    interval=$((interval * 2))
    if [ "$interval" -gt "$max_interval" ]; then interval="$max_interval"; fi
  done
  return 0
}

# Mint a machine-identity token and export it as INFISICAL_TOKEN. Fails (non-zero)
# on a failed or empty login instead of exporting an empty token.
infisical_login() {
  local token
  token="$(infisical login --method=universal-auth \
    --client-id="$INFISICAL_UA_CLIENT_ID" \
    --client-secret="$INFISICAL_UA_CLIENT_SECRET" \
    --domain="$DOMAIN" --plain --silent)" || {
      echo "infisical: login failed - refusing to start without secrets" >&2
      return 1
    }
  if [ -z "$token" ]; then
    echo "infisical: login returned an empty token - refusing to start without secrets" >&2
    return 1
  fi
  export INFISICAL_TOKEN="$token"
}

# Export one folder as dotenv and source it into the current shell (caller wraps
# in set -a). Fails if the export fails, or if it is empty and $3 is "required".
# usage: infisical_source_path <path> <project-id> <env> [required]
infisical_source_path() {
  local path="$1" project="$2" env="$3" required="${4:-}" out
  out="$(infisical export --domain="$DOMAIN" --projectId="$project" --env="$env" \
    --path="$path" --format=dotenv)" || {
      echo "infisical: export of ${path} failed - refusing to start without secrets" >&2
      return 1
    }
  if [ "$required" = "required" ] && [ -z "$out" ]; then
    echo "infisical: export of ${path} was empty - refusing to start without secrets" >&2
    return 1
  fi
  # shellcheck disable=SC1090
  source <(printf '%s\n' "$out")
}
