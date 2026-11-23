"""Read-only check that the LOCAL model used for personal health narrative is available.

Run on the VM (it only reads the local Ollama model list; it sends no prompt and no personal
data, and changes nothing):

    python3 scripts/check_health_llm_local.py

Exit codes: 0 ready; 2 model not pulled; 3 Ollama unreachable; 4 model tag would leave the host.
When this does not return 0, personal health narrative falls back to the deterministic text.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

READY, MODEL_MISSING, UNREACHABLE, LEAVES_HOST = 0, 2, 3, 4


def evaluate_tags(tags: dict, model: str) -> tuple[int, str]:
    """Pure: decide the status from an /api/tags payload."""
    m = (model or "").strip()
    if m.lower().endswith((":cloud", "-cloud")):
        return LEAVES_HOST, f"model '{m}' is a cloud-hosted tag: it would leave this machine"
    names = {t.get("name", "") for t in (tags or {}).get("models", [])}
    if m in names or any(n.split(":")[0] == m.split(":")[0] and ":" not in m for n in names):
        return READY, f"model '{m}' is pulled and available locally"
    return MODEL_MISSING, f"model '{m}' is not pulled (available: {', '.join(sorted(names)) or 'none'})"


def check(base_url: str, model: str, *, opener=None) -> tuple[int, str]:
    try:
        req = urllib.request.Request(base_url.rstrip("/") + "/api/tags")
        with (opener or urllib.request.urlopen)(req, timeout=5) as resp:  # nosec B310 - local Ollama URL from env
            return evaluate_tags(json.loads(resp.read().decode()), model)
    except Exception as exc:  # noqa: BLE001 - any failure means "not available"
        return UNREACHABLE, f"Ollama unreachable at {base_url}: {type(exc).__name__}"


if __name__ == "__main__":
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("OLLAMA_COMMANDER_MODEL") or os.getenv("OLLAMA_MODEL", "qwen3:8b")
    code, msg = check(base, model)
    print(f"[health-llm-local] {msg}")
    sys.exit(code)
