#!/usr/bin/env bash
# Start the Arize Phoenix LLM observability server on port 6006.
#
# Phoenix collects OTel spans from all instrumented Starship Endeavour
# services and renders them as trace trees in its web UI.
#
# Usage:
#   ./tools/start-phoenix.sh
#   # Then open http://localhost:6006 in a browser.
#
# Log file: /var/log/starship/phoenix.log
#
# Port 6006 is Phoenix's default. Nothing else in this platform uses
# that port (confirmed by grep for 6006 in the codebase — no conflicts).
#
# Requires: platform-runtime/.venv with arize-phoenix installed.
#   Install: platform-runtime/.venv/bin/pip install arize-phoenix

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PYTHON="${REPO_ROOT}/platform-runtime/.venv/bin/python"
LOG_FILE="/var/log/starship/phoenix.log"

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "ERROR: venv Python not found at ${VENV_PYTHON}" >&2
  echo "Run: python3 -m venv platform-runtime/.venv && platform-runtime/.venv/bin/pip install arize-phoenix" >&2
  exit 1
fi

if ! "${VENV_PYTHON}" -c "import phoenix" 2>/dev/null; then
  echo "ERROR: arize-phoenix not installed in the venv." >&2
  echo "Run: ${REPO_ROOT}/platform-runtime/.venv/bin/pip install arize-phoenix" >&2
  exit 1
fi

# All 7 instrumented call sites import "platform_runtime.lib.telemetry"
# (underscore) — but the directory on disk is "platform-runtime" (hyphen),
# so that import has never actually resolved (silently swallowed by each
# call site's own try/except ImportError, matching GAP 2's "silently
# dropped" symptom). Two symlinks close that gap: one at the repo root
# for the sys.path.insert(_REPO_ROOT) pattern (intelligence/scheduler.py,
# telegram-bots/xo/app.py, platform-runtime/lib/officers/daily_operations_cycle.py),
# one inside this venv's site-packages for the pattern that inserts that
# path directly (core/model-router/app.py, core/llm/provider_chain.py,
# platform-runtime/lib/mistral_agent_client.py — these run under system
# Python, not this venv, so they reach platform_runtime only via that
# site-packages symlink). The repo-root symlink is tracked in git; the
# venv-internal one is not (.venv/ is gitignored) and must be recreated
# after any fresh venv build — this check makes that self-healing rather
# than a second silent gap.
REPO_ROOT_LINK="${REPO_ROOT}/platform_runtime"
if [[ ! -e "${REPO_ROOT_LINK}" ]]; then
  ln -s platform-runtime "${REPO_ROOT_LINK}"
  echo "Created ${REPO_ROOT_LINK} -> platform-runtime (repo-root import shim)"
fi

VENV_SITE_PACKAGES="$("${VENV_PYTHON}" -c 'import site; print(site.getsitepackages()[0])')"
VENV_LINK="${VENV_SITE_PACKAGES}/platform_runtime"
if [[ ! -e "${VENV_LINK}" ]]; then
  ln -s "${REPO_ROOT}/platform-runtime" "${VENV_LINK}"
  echo "Created ${VENV_LINK} -> ${REPO_ROOT}/platform-runtime (venv import shim)"
fi

mkdir -p "$(dirname "${LOG_FILE}")"

echo "Starting Phoenix on port 6006 — UI at http://localhost:6006"
echo "Logging to ${LOG_FILE}"

exec "${VENV_PYTHON}" -m phoenix.server.main serve \
  --host 0.0.0.0 \
  --port 6006 \
  >> "${LOG_FILE}" 2>&1
