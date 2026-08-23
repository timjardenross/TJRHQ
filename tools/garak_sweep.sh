#!/usr/bin/env bash
# garak_sweep.sh — LLM safety sweep against the local model router
#
# Runs garak probes (hallucination, promptinject) against the model router
# at http://localhost:8891 and saves a timestamped report under reports/garak/.
#
# Exit codes:
#   0  — sweep completed with no failures detected
#   1  — one or more probe failures detected
#   2  — garak could not run (missing venv, router unreachable, etc.)
#
# Usage:
#   bash tools/garak_sweep.sh
#
# The ROUTER_URL environment variable overrides the default endpoint.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON="${REPO_ROOT}/platform-runtime/.venv/bin/python3"
VENV_GARAK="${REPO_ROOT}/platform-runtime/.venv/bin/garak"
REPORT_DIR="${REPO_ROOT}/reports/garak"
ROUTER_URL="${ROUTER_URL:-http://localhost:8891}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_PATH="${REPORT_DIR}/sweep-${TIMESTAMP}.json"

# ── Preflight checks ────────────────────────────────────────────────────────

if [[ ! -x "${VENV_PYTHON}" ]]; then
    echo "[garak-sweep] ERROR: platform-runtime venv not found at ${VENV_PYTHON}" >&2
    exit 2
fi

if [[ ! -x "${VENV_GARAK}" ]]; then
    echo "[garak-sweep] ERROR: garak not installed in venv. Run:" >&2
    echo "  ${REPO_ROOT}/platform-runtime/.venv/bin/pip install garak" >&2
    exit 2
fi

mkdir -p "${REPORT_DIR}"

# Check router reachability before starting a potentially long sweep.
if ! curl --silent --fail --max-time 5 "${ROUTER_URL}/health" > /dev/null 2>&1 \
   && ! curl --silent --fail --max-time 5 "${ROUTER_URL}/" > /dev/null 2>&1; then
    echo "[garak-sweep] WARNING: model router at ${ROUTER_URL} did not respond to preflight." >&2
    echo "[garak-sweep] Proceeding anyway — garak may report connection errors." >&2
fi

# ── Run sweep ───────────────────────────────────────────────────────────────

echo "[garak-sweep] Starting sweep at $(date -u)"
echo "[garak-sweep] Target:  ${ROUTER_URL}"
echo "[garak-sweep] Report:  ${REPORT_PATH}"
echo "[garak-sweep] Probes:  hallucination, promptinject"

"${VENV_GARAK}" \
    --model_type rest \
    --model_name "local-router" \
    --rest.uri "${ROUTER_URL}/v1/chat/completions" \
    --probes hallucination,promptinject \
    --report_prefix "${REPORT_PATH}" \
    --extended_detectors \
    2>&1 | tee "${REPORT_PATH}.log"

GARAK_EXIT="${PIPESTATUS[0]}"

echo "[garak-sweep] garak exited with code ${GARAK_EXIT}"
echo "[garak-sweep] Report saved to: ${REPORT_PATH}"

# ── Interpret result ────────────────────────────────────────────────────────
# garak exits 0 even when probes fire; inspect the log for failure markers.

if [[ "${GARAK_EXIT}" -ne 0 ]]; then
    echo "[garak-sweep] FAIL — garak exited non-zero (${GARAK_EXIT}). See log for details." >&2
    exit 1
fi

if grep -qiE "(FAIL|vulnerability|probe triggered)" "${REPORT_PATH}.log" 2>/dev/null; then
    echo "[garak-sweep] FAIL — probes detected potential vulnerabilities. Review: ${REPORT_PATH}.log" >&2
    exit 1
fi

echo "[garak-sweep] PASS — no failures detected."
exit 0
