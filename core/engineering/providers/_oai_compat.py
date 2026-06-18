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


def _request_once(url: str, api_key: str, payload: dict, *, label: str, timeout: int) -> dict:
    """One POST to the endpoint; returns parsed JSON. Key never logged."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
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
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"[{label}] returned non-JSON: {raw[:200]}") from exc


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
    max_continuations: int = 3,
) -> tuple[str, str]:
    """POST a chat completion to an OpenAI-compatible endpoint. Key never logged.

    Handles TRUNCATION automatically: if the model stops because it hit the token
    limit (`finish_reason == "length"`), the partial answer is fed back and the
    model is asked to continue, up to `max_continuations` times, and the pieces
    are concatenated. This keeps long engineering plans / patches from being cut
    off mid-output. If it is still truncated after the cap, a clear marker is
    appended (rather than silently returning a partial) and a warning is logged.
    """
    if not api_key:
        raise RuntimeError(f"[{label}] API key is not set. Add it to .env and restart.")

    url = f"{base_url.rstrip('/')}/chat/completions"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    log.info("[%s] url=%s model=%s prompt_len=%d", label, url, model, len(prompt))

    parts: list[str] = []
    used = model
    truncated = False
    for attempt in range(max_continuations + 1):
        data = _request_once(url, api_key, {
            "model": model, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens, "stream": False,
        }, label=label, timeout=timeout)
        try:
            choice = data["choices"][0]
            piece = (choice["message"]["content"] or "")
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"[{label}] response missing choices/message: {str(data)[:300]}") from exc
        used = data.get("model", model)
        if piece:
            parts.append(piece)
        if choice.get("finish_reason") != "length":
            truncated = False
            break
        truncated = True
        if attempt < max_continuations:
            # Feed the partial back and ask for a seamless continuation.
            messages.append({"role": "assistant", "content": piece})
            messages.append({"role": "user", "content":
                             "Continue exactly where you left off. Do not repeat any "
                             "previous content; resume mid-token if necessary."})
            log.info("[%s] response truncated (finish_reason=length) — continuing (%d/%d)",
                     label, attempt + 1, max_continuations)

    text = "".join(parts).strip()
    if not text:
        raise RuntimeError(f"[{label}] returned an empty response.")
    if truncated:
        log.warning("[%s] response still truncated after %d continuations (len=%d)",
                    label, max_continuations, len(text))
        text += (f"\n\n[…response truncated after {max_continuations} continuations — "
                 "ask me to continue for the rest.]")

    log.info("[%s] response_len=%d model=%s parts=%d", label, len(text), used, len(parts))
    return text, used


def mask(key: str) -> str:
    """Masked key fingerprint for connectivity messages (never the full key)."""
    return f"{key[:8]}…" if len(key) > 8 else "set"
