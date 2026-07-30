"""Kimi K2 (Code) backend for the Engineering Workflow Router.

Served via Ollama Cloud's OpenAI-compatible Chat Completions API — the SAME
gateway and key as the GLM backend (https://ollama.com/v1, Bearer auth). Kimi is
therefore just a different model id on the shared endpoint; no separate Moonshot
integration or new secret is required.

Intended role (MSN-0066 Chief Engineer bot): engineering PLANNING.

Key resolution (first set wins): KIMI_API_KEY → OLLAMA_API_KEY → GLM_API_KEY
(so it works out of the box with the existing Ollama Cloud key).

Optional env:
    KIMI_BASE_URL  (default: https://ollama.com/v1)
    KIMI_MODEL     (default: kimi-k2:1t-cloud) — set to the exact served tag
"""

from __future__ import annotations

import os
from typing import Optional

from core.engineering.providers import _oai_compat

DEFAULT_MODEL = "kimi-k2.7-code"   # current Ollama Cloud tag (verified 2026-06-18)
DEFAULT_BASE_URL = "https://ollama.com/v1"


def _base_url() -> str:
    return os.getenv("KIMI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _api_key() -> str:
    # Reuse the shared Ollama Cloud key unless a dedicated Kimi key is set.
    for env in ("KIMI_API_KEY", "OLLAMA_API_KEY", "GLM_API_KEY"):
        v = os.getenv(env, "").strip()
        if v:
            return v
    return ""


def _resolved_model(model: Optional[str]) -> str:
    return model or os.getenv("KIMI_MODEL", DEFAULT_MODEL)


def check_connectivity() -> tuple[bool, str]:
    """Key-only pre-flight gate (no network call). Never raises; key masked."""
    key = _api_key()
    if not key:
        return False, ("No Kimi key. Set KIMI_API_KEY (or reuse OLLAMA_API_KEY / "
                       "GLM_API_KEY, the Ollama Cloud key) in .env.")
    return True, (f"Kimi key configured ({_oai_compat.mask(key)}). "
                  f"Endpoint: {_base_url()}. Model: {_resolved_model(None)}.")


def call(prompt: str, model: Optional[str] = None, system: Optional[str] = None) -> tuple[str, str]:
    """Send prompt to Kimi via Ollama Cloud. Returns (text, model_used)."""
    return _oai_compat.chat(_base_url(), _api_key(), _resolved_model(model),
                            prompt, system=system, label="kimi")
