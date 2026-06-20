"""
VM Ollama backend for the Engineering Workflow Router.

Calls the Ollama HTTP API on a configurable host. Works for both:
- Local Ollama (localhost:11434) — the default
- VM-hosted Ollama (set OLLAMA_VM_URL=http://<vm-ip>:11434)

Optional env vars:
    OLLAMA_VM_URL              (default: http://localhost:11434)
    OLLAMA_ENGINEERING_MODEL   (default: qwen2.5-coder:7b)
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Optional

log = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen2.5-coder:7b"
_CONNECT_TIMEOUT = 5   # seconds for connectivity check
_REQUEST_TIMEOUT = 120  # seconds for generation


def _base_url() -> str:
    return os.getenv("OLLAMA_VM_URL", "http://localhost:11434").rstrip("/")


def check_connectivity() -> tuple[bool, str]:
    """
    Return (reachable, message).
    Does not raise — safe to call as a pre-flight check.
    """
    url = f"{_base_url()}/api/tags"
    try:
        req = urllib.request.urlopen(url, timeout=_CONNECT_TIMEOUT)
        data = json.loads(req.read().decode())
        models = [m["name"] for m in data.get("models", [])]
        return True, f"Ollama reachable at {_base_url()}. Models: {models}"
    except Exception as exc:
        return False, f"Ollama not reachable at {_base_url()}: {exc}"


def call(prompt: str, model: Optional[str] = None) -> tuple[str, str]:
    """
    Send prompt to Ollama generate endpoint.

    Returns (response_text, model_used).
    Raises RuntimeError with a descriptive message on failure.
    """
    resolved_model = model or os.getenv("OLLAMA_ENGINEERING_MODEL", DEFAULT_MODEL)
    base = _base_url()
    url = f"{base}/api/generate"

    payload = json.dumps({
        "model": resolved_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 2048,
        },
    }).encode("utf-8")

    log.info("[vm-ollama] url=%s model=%s prompt_len=%d", url, resolved_model, len(prompt))

    reachable, msg = check_connectivity()
    if not reachable:
        raise RuntimeError(
            f"VM Ollama connectivity check failed — cannot run request.\n{msg}"
        )

    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama request failed: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Ollama unexpected error: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ollama returned non-JSON: {raw[:200]}") from exc

    text = data.get("response", "").strip()
    if not text:
        raise RuntimeError(f"Ollama returned an empty response. Raw: {raw[:300]}")

    log.info("[vm-ollama] response_len=%d model=%s", len(text), resolved_model)
    return text, resolved_model
