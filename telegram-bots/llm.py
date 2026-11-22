"""Shared LLM module for Telegram bots.

Routing (MSN-0206):
    Tier 1 — Model Router  :8891/api/model/xo-response  (gemma4:12b local)
    Tier 2 — Ollama Cloud  glm-5.2 (controlled overflow, logged)

    Callers can pass cloud_first=True to swap the order (cloud, then the
    router as fallback). XO's chat reply does this: the local router's
    xo-response averaged ~80 s on this CPU-only host against a 20 s client
    timeout, so trying it first just added a 20 s wait to every reply.

Configure via env vars:
    MODEL_ROUTER_URL        — default http://127.0.0.1:8891
    OLLAMA_CLOUD_BASE_URL   — default https://ollama.com (the cloud tier only)
    OLLAMA_CLOUD_MODEL      — default glm-5.2
    OLLAMA_API_KEY          — Ollama cloud API key (required for cloud tier)
    OLLAMA_CLOUD_DISABLED   — set to 1/true/yes/on to turn the cloud tier off
                              entirely (local router only). Unset = unchanged.
OLLAMA_BASE_URL / OLLAMA_MODEL are deliberately NOT read here: they are the
platform-wide LOCAL Ollama settings (http://localhost:11434, a local model),
and reading them made this "cloud" tier silently call the local CPU model.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request
from functools import partial

from core.security import personal_data_policy

log = logging.getLogger(__name__)

_DEFAULT_ROUTER_URL = "http://127.0.0.1:8891"
_DEFAULT_CLOUD_URL  = "https://ollama.com"
_DEFAULT_MODEL      = "glm-5.2"
_ROUTER_TIMEOUT     = 20
_CLOUD_TIMEOUT      = 30


def _router_url() -> str:
    return os.getenv("MODEL_ROUTER_URL", _DEFAULT_ROUTER_URL).rstrip("/")


def _cloud_base_url() -> str:
    return os.getenv("OLLAMA_CLOUD_BASE_URL", _DEFAULT_CLOUD_URL).rstrip("/")


def _cloud_model() -> str:
    return os.getenv("OLLAMA_CLOUD_MODEL", _DEFAULT_MODEL)


def _cloud_api_key() -> str:
    return os.getenv("OLLAMA_API_KEY", "")


def _cloud_disabled() -> bool:
    """True when the operator has switched the cloud tier off (default: off-switch unset)."""
    return os.getenv("OLLAMA_CLOUD_DISABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _personal_router_timeout() -> float:
    """Personal-data routes may not fall through to the cloud, so give the local router longer."""
    try:
        return float(os.getenv("LLM_PERSONAL_ROUTER_TIMEOUT", "60"))
    except ValueError:
        return 60.0


def _router_is_local() -> bool:
    """Fail-closed check that MODEL_ROUTER_URL points at this machine or a private network address.
    A personal-data route must not be sent to a router that has been (mis)configured to a public host."""
    import ipaddress
    from urllib.parse import urlparse
    host = (urlparse(_router_url()).hostname or "").lower()
    if host == "localhost" or host.endswith((".local", ".internal")):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


def _call_router(prompt: str, system_prompt: str | None = None, *, timeout: float | None = None) -> str | None:
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
        with urllib.request.urlopen(req, timeout=timeout or _ROUTER_TIMEOUT) as resp:  # nosec B310 - url built from MODEL_ROUTER_URL env var with fixed local default, not user input - reviewed 2026-09-12
            body = json.loads(resp.read())
        content = (body.get("response") or body.get("content") or "").strip()
        if content:
            log.debug("[llm] router tier-1 ok")
            return content
        return None
    except Exception as exc:  # noqa: BLE001 - network/timeout/JSON-decode surface from external router call is unpredictable, already logged
        log.warning("[llm] router unavailable: %s", exc)
        return None


def _call_cloud(prompt: str, system_prompt: str | None = None, *, degraded: bool = True) -> str | None:
    """Call Ollama Cloud (glm-5.2) as controlled overflow. Returns text or None.

    Default-deny (R1): personal health content is never sent here unless the Captain has opted in
    (HEALTH_LLM_EXTERNAL_ALLOWED=1); the content check below is a backstop for callers that forgot
    to mark the route as personal."""
    try:
        personal_data_policy.assert_may_leave_host(prompt, system_prompt or "", route="Ollama Cloud")
    except personal_data_policy.PersonalDataBlockedError as exc:
        log.warning("[llm] %s", exc)
        return None
    if _cloud_disabled():
        log.info("[llm] cloud tier disabled (OLLAMA_CLOUD_DISABLED) - not sent")
        return None
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
        with urllib.request.urlopen(req, timeout=_CLOUD_TIMEOUT) as resp:  # nosec B310 - url built from OLLAMA_BASE_URL env var with fixed default, not user input - reviewed 2026-09-12
            body = json.loads(resp.read())
        content = (body.get("message") or {}).get("content", "").strip()
        if content:
            if degraded:
                log.warning("[llm] degraded to cloud tier-2 (router unavailable)")
            else:
                log.info("[llm] cloud tier answered (cloud-first)")
            return content
        return None
    except Exception as exc:  # noqa: BLE001 - network/timeout/JSON-decode surface from external API call is unpredictable, already logged
        log.warning("[llm] cloud fallback failed: %s", exc)
        return None


def generate(prompt: str, system_prompt: str | None = None, *, cloud_first: bool = False,
             personal: bool = False) -> str | None:
    """Return text from the Model Router and Ollama Cloud, tried in that order
    (or cloud first when cloud_first=True). None if both fail. With
    OLLAMA_CLOUD_DISABLED set, only the local router is used.

    personal=True marks a route that carries the Captain's personal health data. Such a route uses
    the LOCAL router only and returns None (callers show a deterministic fallback) rather than
    reaching the cloud, unless HEALTH_LLM_EXTERNAL_ALLOWED=1. Content that looks personal is
    treated the same way even when the caller did not mark it."""
    if not personal_data_policy.external_ai_allowed() and (
            personal or personal_data_policy.contains_personal_health(f"{system_prompt or ''}\n{prompt}")):
        if not _router_is_local():
            log.warning("[llm] personal route refused: MODEL_ROUTER_URL is not a local/private address")
            return None
        return _call_router(prompt, system_prompt, timeout=_personal_router_timeout())
    if _cloud_disabled():
        return _call_router(prompt, system_prompt)
    if cloud_first:
        result = _call_cloud(prompt, system_prompt, degraded=False)
        if result:
            return result
        log.warning("[llm] cloud tier failed - falling back to the local router")
        return _call_router(prompt, system_prompt)
    result = _call_router(prompt, system_prompt)
    if result:
        return result
    return _call_cloud(prompt, system_prompt)


async def generate_async(
    prompt: str, system_prompt: str | None = None, *, cloud_first: bool = False, personal: bool = False
) -> str | None:
    """Non-blocking wrapper for use in async Telegram handlers."""
    return await asyncio.to_thread(
        partial(generate, prompt, system_prompt, cloud_first=cloud_first, personal=personal))
