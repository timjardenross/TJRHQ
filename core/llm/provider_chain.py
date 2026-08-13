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

import json
import urllib.request
from typing import Optional


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
        # thinkingBudget=0 disables Gemini 2.5's internal reasoning tokens —
        # without this, maxOutputTokens is consumed by hidden thought tokens
        # before any visible text, silently truncating short responses.
        "generationConfig": {
            "maxOutputTokens": max_output_tokens, "temperature": temperature,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
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
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())

    text = (data.get("response") or "").strip()
    if not text:
        raise RuntimeError("Ollama returned an empty response")
    return text
