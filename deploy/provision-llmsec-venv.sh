#!/bin/bash
# provision-llmsec-venv.sh - build (or verify) platform-runtime/.venv-llmsec.
#
# Why this exists: the LLM-security pipeline (Presidio PII redaction + NeMo
# Guardrails, ADR-032) runs in a dedicated, gitignored venv that nothing
# rebuilt. When it was removed in the 2026-11-03 disk clean-up, model-router
# returned HTTP 500 and self-improving-system failed until it was rebuilt by hand.
# This script is the one provisioning step. Same commands as the CI job
# (.github/workflows/python-ci.yml, "Provision llmsec venv").
#
# Usage (from anywhere):
#   deploy/provision-llmsec-venv.sh          build if missing/broken, else no-op
#   deploy/provision-llmsec-venv.sh --check  health check only; exit 1 if unhealthy
#
# Needs about 1-2 GB of pip downloads on first build.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/platform-runtime/.venv-llmsec"
REQ="$ROOT/core/security/requirements-llmsec.txt"
SPACY_MODEL="https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"

healthy() {
  "$VENV/bin/python3" -c "import presidio_analyzer, spacy; spacy.load('en_core_web_sm')" >/dev/null 2>&1
}

if [ "${1:-}" = "--check" ]; then
  if healthy; then echo "llmsec venv OK: $VENV"; exit 0; fi
  echo "llmsec venv MISSING or BROKEN: $VENV (run deploy/provision-llmsec-venv.sh)" >&2
  exit 1
fi

if healthy; then
  echo "llmsec venv already healthy, nothing to do."
  exit 0
fi

echo "Building $VENV ..."
rm -rf "$VENV"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r "$REQ"
# Install the small spaCy model explicitly; otherwise Presidio downloads the
# 400 MB en_core_web_lg on first use.
"$VENV/bin/pip" install "$SPACY_MODEL"
healthy && echo "llmsec venv built and healthy." || { echo "build finished but health check failed" >&2; exit 1; }
