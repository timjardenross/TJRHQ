"""Qwen3-Coder backend for the Engineering Workflow Router.

Served via Ollama Cloud's OpenAI-compatible Chat Completions API — the SAME
gateway and key as the GLM backend (https://ollama.com/v1, Bearer auth). Qwen is
therefore just a different model id on the shared endpoint; no separate DashScope
integration or new secret is required.

Intended role (MSN-0066 Chief Engineer bot): PATCH / code-proposal generation.

Key resolution (first set wins): QWEN_API_KEY → OLLAMA_API_KEY → GLM_API_KEY
(so it works out of the box with the existing Ollama Cloud key).

Optional env:
    QWEN_BASE_URL  (default: https://ollama.com/v1)
    QWEN_MODEL     (default: qwen3-coder:480b-cloud) — set to the exact served tag
"""

from __future__ import annotations

import os
from typing import Optional

from core.engineering.providers import _oai_compat

DEFAULT_MODEL = "qwen3-coder:480b"   # current Ollama Cloud tag (verified 2026-06-18)
DEFAULT_BASE_URL = "https://ollama.com/v1"


def _base_url() -> str:
    return os.getenv("QWEN_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _api_key() -> str:
    for env in ("QWEN_API_KEY", "OLLAMA_API_KEY", "GLM_API_KEY"):
        v = os.getenv(env, "").strip()
        if v:
            return v
    return ""


def _resolved_model(model: Optional[str]) -> str:
    return model or os.getenv("QWEN_MODEL", DEFAULT_MODEL)


def check_connectivity() -> tuple[bool, str]:
    """Key-only pre-flight gate (no network call). Never raises; key masked."""
    key = _api_key()
    if not key:
        return False, ("No Qwen key. Set QWEN_API_KEY (or reuse OLLAMA_API_KEY / "
                       "GLM_API_KEY, the Ollama Cloud key) in .env.")
    return True, (f"Qwen key configured ({_oai_compat.mask(key)}). "
                  f"Endpoint: {_base_url()}. Model: {_resolved_model(None)}.")


def call(prompt: str, model: Optional[str] = None, system: Optional[str] = None) -> tuple[str, str]:
    """Send prompt to Qwen3-Coder via Ollama Cloud. Returns (text, model_used)."""
    return _oai_compat.chat(_base_url(), _api_key(), _resolved_model(model),
                            prompt, system=system, label="qwen")
