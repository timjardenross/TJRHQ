"""
Shared cloud/local LLM call primitives — ADR-024 (Resilience Intelligence
Convergence), consolidating the Gemini/Mistral/Ollama request mechanics that
were previously implemented twice: intelligence/brief/llm_provider.py
(RESIL-EXT) and core/health/health_llm.py (RESIL-HUMAN).

Each function performs exactly one provider call and raises RuntimeError on
any failure (missing key, empty response, transport error) — callers are
responsible for the try/except-and-fall-through provider chain, retry
policy, and domain-specific system prompt / token-budget choices. This
module owns none of that; it only owns "how do you actually talk to Gemini /
Mistral / Ollama."
"""

from __future__ import annotations

import contextlib
import json
import urllib.request
from typing import Optional

try:
    import sys as _sys
    _sys.path.insert(0, '/opt/starship-endeavour/platform-runtime/.venv/lib/python3.12/site-packages')
    from platform_runtime.lib.telemetry import configure_tracing as _configure_tracing
    from opentelemetry import trace as _trace
    _configure_tracing("provider-chain")
    _TRACING_AVAILABLE = True
except Exception:
    _TRACING_AVAILABLE = False


def _llm_span(provider: str, model: str, task_type: str = ""):
    """
    Return an OTel span context manager for a provider LLM call, or a
    no-op context manager when tracing is not available.

    Args:
        provider:  LLM provider name (e.g. "gemini", "mistral", "ollama")
        model:     Model identifier being called
        task_type: Optional task label for additional span attribute richness
    """
    if not _TRACING_AVAILABLE:
        return contextlib.nullcontext()
    tracer = _trace.get_tracer("provider_chain")
    return tracer.start_as_current_span(
        f"llm.{provider}",
        attributes={"llm.provider": provider, "llm.model": model, "llm.task_type": task_type}
    )


def call_gemini(
    system_prompt: str,
    prompt: str,
    *,
    api_key: str,
    max_output_tokens: int = 2048,
    temperature: float = 0.3,
    timeout: int = 30,
) -> str:
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-3.5-flash-lite:generateContent?key={api_key}"
    )
    body = json.dumps({
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": prompt}]}],
        # 2026-08-22: thinkingConfig.thinkingBudget=0 (added for Gemini 2.5's
        # hidden-reasoning-token truncation behavior) is REJECTED outright by
        # gemini-3.5-flash-lite with HTTP 400 INVALID_ARGUMENT — confirmed
        # live, this was silently failing every call in every pipeline using
        # this module (100% Mistral-fallback rate, never actually reaching
        # Gemini). Removed rather than reworked: live-verified this model
        # doesn't need it — finishReason=STOP, full untruncated text, well
        # under maxOutputTokens, with no thinkingConfig at all.
        "generationConfig": {
            "maxOutputTokens": max_output_tokens, "temperature": temperature,
        },
    }).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with _llm_span("gemini", "gemini-3.5-flash-lite"):
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())

    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")
    return candidates[0]["content"]["parts"][0]["text"].strip()


def call_mistral(
    system_prompt: str,
    prompt: str,
    *,
    api_key: str,
    model: str = "mistral-small-latest",
    max_tokens: int = 2048,
    temperature: float = 0.3,
    timeout: int = 30,
) -> str:
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY not set")

    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode()
    req = urllib.request.Request(
        "https://api.mistral.ai/v1/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with _llm_span("mistral", model):
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())

    return data["choices"][0]["message"]["content"].strip()


def call_ollama(
    system_prompt: str,
    prompt: str,
    *,
    base_url: str,
    model: str,
    temperature: float = 0.3,
    num_predict: int = 1200,
    timeout: int = 60,
) -> str:
    body = json.dumps({
        "model": model,
        "prompt": f"{system_prompt}\n\n{prompt}",
        "stream": False,
        "options": {"temperature": temperature, "num_predict": num_predict},
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with _llm_span("ollama", model):
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())

    text = (data.get("response") or "").strip()
    if not text:
        raise RuntimeError("Ollama returned an empty response")
    return text
