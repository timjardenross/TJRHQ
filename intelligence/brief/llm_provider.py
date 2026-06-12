"""
LLM provider chain for OR Intelligence brief narrative generation.
Used ONLY for executive narrative sections (not classification/ranking).

Provider order (per Captain's decision):
  1. Gemini 2.5 Flash
  2. Mistral Small
  3. Ollama qwen3:8b
  4. Rule-based fallback (always available)

If all LLM providers fail:
  - Events are still collected, classified, ranked, and persisted
  - Brief is generated with narrative_available=False
  - Narrative sections are explicitly marked [UNAVAILABLE]
"""

import json
import logging
import urllib.request
import urllib.error
from typing import Optional

from intelligence.config import (
    GEMINI_API_KEY, MISTRAL_API_KEY,
    OLLAMA_BASE_URL, OLLAMA_MODEL,
)

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are the Operational Resilience Intelligence Officer for USS Starship Endeavour.
You are generating sections of an executive intelligence brief for Captain TJR.

Rules:
- Only synthesise from the event data provided. Do not invent incidents.
- Be concise, factual, and use plain English.
- Prioritise Australian banking and CPS 230 implications.
- Use present tense for ongoing events, past tense for resolved events.
- Do not include caveats about your own uncertainty — that is handled by the confidence score.
"""


class LLMProvider:
    """Attempts each provider in preference order. Never raises — returns None on total failure."""

    def generate(self, prompt: str) -> tuple[Optional[str], Optional[str]]:
        """
        Returns (text, provider_name) or (None, None) if all fail.
        """
        providers = [
            ("gemini-2.5-flash",  self._gemini),
            ("mistral-small",     self._mistral),
            (OLLAMA_MODEL,        self._ollama),
        ]
        for name, fn in providers:
            try:
                result = fn(prompt)
                if result:
                    log.info("LLM narrative generated via %s", name)
                    return result, name
            except Exception as exc:
                log.warning("LLM provider %s failed: %s", name, exc)

        log.warning("All LLM providers failed — narrative will be unavailable")
        return None, None

    # ─── Gemini 2.5 Flash ─────────────────────────────────────────────────────

    def _gemini(self, prompt: str) -> Optional[str]:
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY not set")

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
        )
        body = json.dumps({
            "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 1200, "temperature": 0.3},
        }).encode()

        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())

        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")
        return candidates[0]["content"]["parts"][0]["text"].strip()

    # ─── Mistral Small ────────────────────────────────────────────────────────

    def _mistral(self, prompt: str) -> Optional[str]:
        if not MISTRAL_API_KEY:
            raise RuntimeError("MISTRAL_API_KEY not set")

        body = json.dumps({
            "model": "mistral-small-latest",
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            "max_tokens": 1200,
            "temperature": 0.3,
        }).encode()

        req = urllib.request.Request(
            "https://api.mistral.ai/v1/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {MISTRAL_API_KEY}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())

        return data["choices"][0]["message"]["content"].strip()

    # ─── Ollama ───────────────────────────────────────────────────────────────

    def _ollama(self, prompt: str) -> Optional[str]:
        body = json.dumps({
            "model": OLLAMA_MODEL,
            "prompt": f"{_SYSTEM_PROMPT}\n\n{prompt}",
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 1200},
        }).encode()

        req = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())

        return data.get("response", "").strip()
