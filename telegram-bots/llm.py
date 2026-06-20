"""Shared LLM module for Telegram bots — Ollama Cloud.

Configure via env vars in each bot's .env:
    OLLAMA_BASE_URL  — default https://ollama.com
    OLLAMA_MODEL     — default glm-5.2
    OLLAMA_API_KEY   — Ollama cloud API key (required for cloud; never commit)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://ollama.com"
_DEFAULT_MODEL    = "glm-5.2"
_TIMEOUT          = 30


def _base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")


def _model() -> str:
    return os.getenv("OLLAMA_MODEL", _DEFAULT_MODEL)


def _api_key() -> str:
    return os.getenv("OLLAMA_API_KEY", "")


def generate(prompt: str, system_prompt: str | None = None) -> str | None:
    """Blocking Ollama call. Returns None on failure (caller decides fallback)."""
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {"model": _model(), "messages": messages, "stream": False}
    headers = {"Content-Type": "application/json"}
    key = _api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"

    req = urllib.request.Request(
        f"{_base_url()}/api/chat",
        data=json.dumps(payload).encode(),
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body = json.loads(resp.read())
        content = (body.get("message") or {}).get("content", "").strip()
        return content or None
    except Exception as exc:
        log.warning("[llm] Ollama call failed: %s", exc)
        return None


async def generate_async(prompt: str, system_prompt: str | None = None) -> str | None:
    """Non-blocking wrapper for use in async Telegram handlers."""
    return await asyncio.to_thread(generate, prompt, system_prompt)
