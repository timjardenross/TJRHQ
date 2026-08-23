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

mkdir -p "$(dirname "${LOG_FILE}")"

echo "Starting Phoenix on port 6006 — UI at http://localhost:6006"
echo "Logging to ${LOG_FILE}"

exec "${VENV_PYTHON}" -m phoenix.server.main serve \
  --host 0.0.0.0 \
  --port 6006 \
  >> "${LOG_FILE}" 2>&1
