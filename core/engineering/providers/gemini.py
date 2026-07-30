"""
Gemini backend for the Engineering Workflow Router.

Suitable for: plan, review, architecture assessment, mission decomposition.
NOT for: auto-apply or direct file modification (ADR-030 governs this).

Required env var:
    GEMINI_API_KEY

Optional env vars:
    GEMINI_ENGINEERING_MODEL   (default: gemini-2.5-flash)
"""

from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"


def check_connectivity() -> tuple[bool, str]:
    """
    Validate that the Gemini API key is present and the SDK is importable.
    Does NOT make a live network call — key presence is the gate.
    Returns (ok, message).
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return False, "GEMINI_API_KEY is not set. Add it to .env before using the Gemini backend."
    try:
        import google.generativeai  # noqa: F401
        return True, f"Gemini SDK available. Key configured ({api_key[:8]}…). Default model: {DEFAULT_MODEL}."
    except ImportError:
        return False, "google-generativeai SDK not installed. Run: pip install google-generativeai"


def call(prompt: str, model: Optional[str] = None) -> tuple[str, str]:
    """
    Send prompt to Gemini generate_content.

    Returns (response_text, model_used).
    Raises RuntimeError with a descriptive message on failure.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. "
            "Add it to your .env file and restart the router."
        )

    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise RuntimeError(
            "google-generativeai SDK not installed. Run: pip install google-generativeai"
        ) from exc

    resolved_model = model or os.getenv("GEMINI_ENGINEERING_MODEL", DEFAULT_MODEL)

    log.info("[gemini] model=%s prompt_len=%d", resolved_model, len(prompt))

    try:
        genai.configure(api_key=api_key)
        client = genai.GenerativeModel(resolved_model)
        response = client.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=2048,
            ),
        )
    except Exception as exc:
        raise RuntimeError(f"Gemini API call failed: {exc}") from exc

    text = ""
    try:
        text = response.text
    except Exception:
        # Fallback: try parts
        try:
            text = "".join(part.text for part in response.parts)
        except Exception:
            pass

    if not text or not text.strip():
        raise RuntimeError(
            "Gemini returned an empty response. "
            "Check GEMINI_API_KEY validity and model availability."
        )

    log.info("[gemini] response_len=%d model=%s", len(text), resolved_model)
    return text.strip(), resolved_model
