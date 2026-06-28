"""Shared LLM module for Telegram bots.

Tier 1: Model Router :8891/api/model/xo-response (local, preferred)
Tier 2: Ollama Cloud glm-5.2 (cloud overflow — explicit fallback, never silent)

Configure via env vars in each bot's .env:
    MODEL_ROUTER_URL — default http://127.0.0.1:8891
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

_DEFAULT_ROUTER_URL  = "http://127.0.0.1:8891"
_DEFAULT_CLOUD_URL   = "https://ollama.com"
_DEFAULT_CLOUD_MODEL = "glm-5.2"
_ROUTER_TIMEOUT      = 20
_CLOUD_TIMEOUT       = 30


def _router_url() -> str:
    return os.getenv("MODEL_ROUTER_URL", _DEFAULT_ROUTER_URL).rstrip("/")


def _cloud_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", _DEFAULT_CLOUD_URL).rstrip("/")


def _cloud_model() -> str:
    return os.getenv("OLLAMA_MODEL", _DEFAULT_CLOUD_MODEL)


def _cloud_api_key() -> str:
    return os.getenv("OLLAMA_API_KEY", "")


def _call_router(prompt: str, system_prompt: str | None = None) -> str | None:
    """Call Model Router tier-1. Returns None on any failure."""
    payload: dict = {"prompt": prompt}
    if system_prompt:
        payload["system_prompt"] = system_prompt
    req = urllib.request.Request(
        f"{_router_url()}/api/model/xo-response",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_ROUTER_TIMEOUT) as resp:
            body = json.loads(resp.read())
        content = (body.get("response") or body.get("content") or "").strip()
        return content or None
    except Exception as exc:
        log.warning("[llm] Model Router unavailable: %s", exc)
        return None


def _call_cloud(prompt: str, system_prompt: str | None = None) -> str | None:
    """Call Ollama Cloud glm-5.2 as explicit overflow. Logs WARNING on every use."""
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {"model": _cloud_model(), "messages": messages, "stream": False}
    headers = {"Content-Type": "application/json"}
    key = _cloud_api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"

    req = urllib.request.Request(
        f"{_cloud_base_url()}/api/chat",
        data=json.dumps(payload).encode(),
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=_CLOUD_TIMEOUT) as resp:
            body = json.loads(resp.read())
        content = (body.get("message") or {}).get("content", "").strip()
        if content:
            log.warning("[llm] Serving via Ollama Cloud overflow (router unavailable)")
        return content or None
    except Exception as exc:
        log.warning("[llm] Ollama Cloud call failed: %s", exc)
        return None


def generate(prompt: str, system_prompt: str | None = None) -> str | None:
    """Blocking generation. Tries router first, then cloud overflow. Returns None if both fail."""
    result = _call_router(prompt, system_prompt)
    if result:
        return result
    return _call_cloud(prompt, system_prompt)


async def generate_async(prompt: str, system_prompt: str | None = None) -> str | None:
    """Non-blocking wrapper for use in async Telegram handlers."""
    return await asyncio.to_thread(generate, prompt, system_prompt)
