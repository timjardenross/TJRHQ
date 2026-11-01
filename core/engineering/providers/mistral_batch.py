"""
Mistral backend for the Engineering Workflow Router.

Uses the Mistral chat completions API (not Batch API — the Batch API is for
async bulk requests; for mission planning the synchronous completions endpoint
is the correct tool).

Required env var:
    MISTRAL_API_KEY

Optional env vars:
    MISTRAL_ENGINEERING_MODEL   (default: mistral-small-2503)
"""

from __future__ import annotations

import logging
import os

# LLM application security baseline (USS-TJR-MSN-0366 Stream 5): this is a
# real external-cloud-API dispatch point (api.mistral.ai, not Ollama-local),
# found via `grep -rn "from mistralai import"` per that mission's scope.
# Same gate as core/model-router/app.py's Gemini branch — see
# docs/decisions/ADR-llm-application-security-baseline.md.
from core.security.llm_guardrails import check_output_rail, secure_outbound_prompt

log = logging.getLogger(__name__)

DEFAULT_MODEL = "mistral-small-2503"

try:
    from mistralai import Mistral
except ImportError:
    Mistral = None  # type: ignore[assignment,misc]


def call(prompt: str, model: str | None = None) -> tuple[str, str]:
    """
    Send prompt to Mistral chat completions.

    Returns (response_text, model_used).
    Raises RuntimeError with a descriptive message on failure.
    """
    if Mistral is None:
        raise RuntimeError("mistralai SDK not installed. Run: pip install mistralai")

    api_key = os.getenv("MISTRAL_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "MISTRAL_API_KEY is not set. "
            "Add it to your .env file and restart the router."
        )

    resolved_model = model or os.getenv("MISTRAL_ENGINEERING_MODEL", DEFAULT_MODEL)

    # Guardrails gate: raises RuntimeError (BlockedByGuardrailsError /
    # GuardrailsUnavailableError, both subclasses) on a blocked prompt or an
    # unreachable guardrails venv — propagates to this function's own
    # caller exactly like the "Mistral API call failed" RuntimeError below.
    safe_prompt, _redaction = secure_outbound_prompt(prompt)

    client = Mistral(api_key=api_key)

    log.info("[mistral] model=%s prompt_len=%d", resolved_model, len(safe_prompt))

    try:
        response = client.chat.complete(
            model=resolved_model,
            messages=[{"role": "user", "content": safe_prompt}],
            max_tokens=2048,
            temperature=0.2,
        )
    except Exception as exc:
        raise RuntimeError(f"Mistral API call failed: {exc}") from exc

    text = response.choices[0].message.content if response.choices else ""
    if not text:
        raise RuntimeError("Mistral returned an empty response.")

    check_output_rail(text)

    log.info("[mistral] response_len=%d", len(text))
    return text.strip(), resolved_model
