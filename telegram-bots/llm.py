"""Shared LLM module for Telegram bots.

Routing (MSN-0206):
    Tier 1 — Model Router  :8891/api/model/xo-response  (gemma4:12b local)
    Tier 2 — Ollama Cloud  glm-5.2 (controlled overflow, logged)

Configure via env vars in each bot's .env:
    MODEL_ROUTER_URL  — default http://127.0.0.1:8891
    OLLAMA_BASE_URL   — default https://ollama.com (cloud fallback only)
    OLLAMA_MODEL      — default glm-5.2
    OLLAMA_API_KEY    — Ollama cloud API key (required for cloud tier)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

_DEFAULT_ROUTER_URL = "http://127.0.0.1:8891"
_DEFAULT_CLOUD_URL  = "https://ollama.com"
_DEFAULT_MODEL      = "glm-5.2"
_ROUTER_TIMEOUT     = 20
_CLOUD_TIMEOUT      = 30


def _router_url() -> str:
    return os.getenv("MODEL_ROUTER_URL", _DEFAULT_ROUTER_URL).rstrip("/")


def _cloud_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", _DEFAULT_CLOUD_URL).rstrip("/")


def _cloud_model() -> str:
    return os.getenv("OLLAMA_MODEL", _DEFAULT_MODEL)


def _cloud_api_key() -> str:
    return os.getenv("OLLAMA_API_KEY", "")


def _call_router(prompt: str, system_prompt: str | None = None) -> str | None:
    """Call Model Router /api/model/xo-response. Returns text or None."""
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
        if content:
            log.debug("[llm] router tier-1 ok")
            return content
        return None
    except Exception as exc:
        log.warning("[llm] router unavailable: %s", exc)
        return None


def _call_cloud(prompt: str, system_prompt: str | None = None) -> str | None:
    """Call Ollama Cloud (glm-5.2) as controlled overflow. Returns text or None."""
    key = _cloud_api_key()
    if not key:
        log.warning("[llm] cloud fallback skipped — OLLAMA_API_KEY not set")
        return None

    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {"model": _cloud_model(), "messages": messages, "stream": False}
    req = urllib.request.Request(
        f"{_cloud_base_url()}/api/chat",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_CLOUD_TIMEOUT) as resp:
            body = json.loads(resp.read())
        content = (body.get("message") or {}).get("content", "").strip()
        if content:
            log.warning("[llm] degraded to cloud tier-2 (router unavailable)")
            return content
        return None
    except Exception as exc:
        log.warning("[llm] cloud fallback failed: %s", exc)
        return None


def generate(prompt: str, system_prompt: str | None = None) -> str | None:
    """Return text from Model Router (tier-1) or Ollama Cloud (tier-2). None if both fail."""
    result = _call_router(prompt, system_prompt)
    if result:
        return result
    return _call_cloud(prompt, system_prompt)


async def generate_async(prompt: str, system_prompt: str | None = None) -> str | None:
    """Non-blocking wrapper for use in async Telegram handlers."""
    return await asyncio.to_thread(generate, prompt, system_prompt)
