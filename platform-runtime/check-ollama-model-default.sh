#!/usr/bin/env bash
# Preflight: fail loudly if OLLAMA_MODEL_DEFAULT is missing or names a model
# Ollama doesn't actually have pulled.
#
# Root cause this guards against (2026-09-21, see memory
# ollama-model-default-misconfig-recurring-2026-09-21): a misspelled
# Infisical key (OLLAMA_MODEL_DEFAUL, missing the T) meant every consumer
# of OLLAMA_MODEL_DEFAULT silently fell through to the code default
# 'glm-5.2', a model name Ollama doesn't have — every LLM call 404'd into
# the honest scaffold/manual-mode fallback, so nothing crashed and nothing
# alerted; Content Workbench AI Review/Polish/Generate, /api/xo, and
# /api/ai/chat all quietly stopped producing real AI output. This is the
# 3rd time this exact class of bug (model name doesn't match what's
# actually pulled) has hit this VM (see EVO-0009/PR#108, PR#114's
# deepeval judge routing).
#
# Run this inside run-with-infisical.sh so OLLAMA_MODEL_DEFAULT/
# OLLAMA_BASE_URL/OLLAMA_API_KEY are populated the same way the app sees
# them. Never echoes secret values — only model names, which aren't
# secrets.
#
# Usage: run-with-infisical.sh check-ollama-model-default.sh

set -euo pipefail

OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"
MODEL="${OLLAMA_MODEL_DEFAULT:-}"

if [ -z "$MODEL" ]; then
  echo "[check-ollama-model-default] FAIL: OLLAMA_MODEL_DEFAULT is not set." >&2
  exit 1
fi

HEADERS=(-H "Content-Type: application/json")
if [ -n "${OLLAMA_API_KEY:-}" ]; then
  HEADERS+=(-H "Authorization: Bearer ${OLLAMA_API_KEY}")
fi

TAGS_JSON="$(curl -fsS -m 10 "${HEADERS[@]}" "${OLLAMA_BASE_URL}/api/tags" 2>&1)" || {
  echo "[check-ollama-model-default] FAIL: could not reach ${OLLAMA_BASE_URL}/api/tags (Ollama down or unreachable)." >&2
  exit 1
}

AVAILABLE="$(printf '%s' "$TAGS_JSON" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception as exc:
    print(f"__PARSE_ERROR__:{exc}", file=sys.stderr)
    sys.exit(1)
for m in data.get("models", []):
    print(m.get("name") or m.get("model") or "")
')" || {
  echo "[check-ollama-model-default] FAIL: could not parse /api/tags response." >&2
  exit 1
}

if ! printf '%s\n' "$AVAILABLE" | grep -qxF "$MODEL"; then
  echo "[check-ollama-model-default] FAIL: OLLAMA_MODEL_DEFAULT='${MODEL}' is not in Ollama's pulled models." >&2
  echo "[check-ollama-model-default] Available models:" >&2
  printf '%s\n' "$AVAILABLE" | sed 's/^/  - /' >&2
  exit 1
fi

echo "[check-ollama-model-default] OK: '${MODEL}' is reachable and pulled."
