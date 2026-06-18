"""Shared OpenAI-compatible Chat Completions client.

Extracted from the proven glm.py request/auth/error handling so Ollama-Cloud-
served backends (Kimi, Qwen) don't each re-implement it. Stdlib-only (urllib),
no SDK dependency. The Authorization header (Bearer key) is never logged; API
error bodies (which do not contain the key) are surfaced for diagnosis.

Returns (response_text, model_used). Raises RuntimeError with a descriptive,
key-safe message on any failure.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Optional

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 120  # seconds for generation


def chat(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    system: Optional[str] = None,
    *,
    label: str = "oai",
    timeout: int = DEFAULT_TIMEOUT,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> tuple[str, str]:
    """POST a chat completion to an OpenAI-compatible endpoint. Key never logged."""
    if not api_key:
        raise RuntimeError(f"[{label}] API key is not set. Add it to .env and restart.")

    url = f"{base_url.rstrip('/')}/chat/completions"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }).encode("utf-8")

    log.info("[%s] url=%s model=%s prompt_len=%d", label, url, model, len(prompt))

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",  # never logged
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8")[:400]
        except Exception:
            pass
        raise RuntimeError(f"[{label}] request failed: HTTP {exc.code} {exc.reason}. {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"[{label}] request failed (endpoint unreachable): {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"[{label}] unexpected error: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"[{label}] returned non-JSON: {raw[:200]}") from exc

    try:
        text = (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"[{label}] response missing choices/message: {raw[:300]}") from exc

    if not text:
        raise RuntimeError(f"[{label}] returned an empty response. Raw: {raw[:300]}")

    used = data.get("model", model)
    log.info("[%s] response_len=%d model=%s", label, len(text), used)
    return text, used


def mask(key: str) -> str:
    """Masked key fingerprint for connectivity messages (never the full key)."""
    return f"{key[:8]}…" if len(key) > 8 else "set"
