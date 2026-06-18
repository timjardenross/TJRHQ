"""
GLM (Zhipu / Z.ai) backend for the Engineering Workflow Router.

Talks to a GLM model over the OpenAI-compatible Chat Completions API. The
default target is Ollama Cloud (https://ollama.com/v1), which serves the GLM-5
family (glm-5, glm-5.1, glm-5.2, glm-4.7). The same request shape also works for
any OpenAI-compatible GLM gateway (e.g. a local Ollama at http://localhost:11434/v1,
or Zhipu/Z.ai's /api/paas/v4), so the endpoint is fully env-driven.

Auth is a simple `Authorization: Bearer <GLM_API_KEY>` (Ollama Cloud style). Uses
only the standard library (urllib) — no extra SDK dependency, matching the
vm_ollama backend's style.

Suitable for: plan, review, patch proposal (review-only). NOT for auto-apply.

Required env var:
    GLM_API_KEY

Optional env vars:
    GLM_BASE_URL   (default: https://ollama.com/v1)
    GLM_MODEL      (default: glm-5.2)   — set to the exact served model id
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Optional

log = logging.getLogger(__name__)

DEFAULT_MODEL = "glm-5.2"
DEFAULT_BASE_URL = "https://ollama.com/v1"
_REQUEST_TIMEOUT = 120  # seconds for generation


def _base_url() -> str:
    return os.getenv("GLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _api_key() -> str:
    return os.getenv("GLM_API_KEY", "").strip()


def _resolved_model(model: Optional[str]) -> str:
    return model or os.getenv("GLM_MODEL", DEFAULT_MODEL)


def check_connectivity() -> tuple[bool, str]:
    """
    Validate that the GLM API key is present. Key-only gate (no network call),
    so it is always safe to call as a pre-flight check. Never raises; the key is
    masked in the message (never logged in full).
    """
    key = _api_key()
    if not key:
        return False, "GLM_API_KEY is not set. Add it to .env before using the GLM backend."
    masked = f"{key[:8]}…" if len(key) > 8 else "set"
    return True, f"GLM key configured ({masked}). Endpoint: {_base_url()}. Model: {_resolved_model(None)}."


def call(prompt: str, model: Optional[str] = None, system: Optional[str] = None) -> tuple[str, str]:
    """
    Send prompt to GLM via the OpenAI-compatible Chat Completions endpoint.

    `system`, when provided, is sent as a leading system-role message — used by
    callers to attach a persona/role description that contains the model's
    responses on every call.

    Returns (response_text, model_used).
    Raises RuntimeError with a descriptive message on failure.
    """
    key = _api_key()
    if not key:
        raise RuntimeError(
            "GLM_API_KEY is not set. Add it to your .env file and restart."
        )

    resolved_model = _resolved_model(model)
    url = f"{_base_url()}/chat/completions"

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = json.dumps({
        "model": resolved_model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 4096,
        "stream": False,
    }).encode("utf-8")

    log.info("[glm] url=%s model=%s prompt_len=%d", url, resolved_model, len(prompt))

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",  # key never logged
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        # Surface the API's error body (it does NOT contain the key) to diagnose
        # bad model id / wrong endpoint, without leaking the Authorization header.
        body = ""
        try:
            body = exc.read().decode("utf-8")[:400]
        except Exception:
            pass
        raise RuntimeError(f"GLM request failed: HTTP {exc.code} {exc.reason}. {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GLM request failed (endpoint unreachable): {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"GLM unexpected error: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"GLM returned non-JSON: {raw[:200]}") from exc

    try:
        text = (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"GLM response missing choices/message: {raw[:300]}") from exc

    if not text:
        raise RuntimeError(f"GLM returned an empty response. Raw: {raw[:300]}")

    used = data.get("model", resolved_model)
    log.info("[glm] response_len=%d model=%s", len(text), used)
    return text, used
