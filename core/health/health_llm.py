"""
Health Intelligence LLM Provider — Sprint A

Single-call LLM provider for personal health synthesis narrative.
Uses the same provider-chain pattern as OR Intelligence (intelligence/brief/llm_provider.py)
but is a standalone module requiring no intelligence/ package imports.

Provider order:
  1. Gemini 2.5 Flash   (cloud — if GEMINI_API_KEY set)
  2. Mistral Small      (cloud — if MISTRAL_API_KEY set)
  3. Ollama local       (local — if Ollama is running)

If all providers fail:
  - Returns (None, None)
  - Weekly synthesis falls back to deterministic template narrative
  - No exception is raised; caller must check for None

The prompt must request JSON output with exactly these keys:
  situation, patterns_noticed, what_it_means, recommended_focus, watch_items
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

try:
    from dotenv import load_dotenv
    load_dotenv(_ENV_FILE)
except ImportError:
    pass

_GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
_MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_OLLAMA_MODEL    = os.getenv("OLLAMA_COMMANDER_MODEL") or os.getenv("OLLAMA_MODEL", "qwen3:8b")

_CAPTAIN_PROFILE_PATH = Path(__file__).resolve().parents[2] / "knowledge" / "memory" / "captain_profile.txt"


def _load_captain_profile_excerpt() -> str:
    """Return the HEALTH PROFILE and EXECUTIVE FUNCTION SUPPORT sections from the captain profile."""
    try:
        text = _CAPTAIN_PROFILE_PATH.read_text(encoding="utf-8", errors="replace")
        # Extract from HEALTH PROFILE through end of EXECUTIVE FUNCTION SUPPORT
        m = re.search(
            r"(={10,}\s*\nHEALTH PROFILE\s*\n={10,}.+?)(={10,}\s*\nPROFESSIONAL EXPERTISE)",
            text, re.DOTALL,
        )
        return m.group(1).strip() if m else ""
    except Exception:
        return ""


_CAPTAIN_PROFILE_EXCERPT = _load_captain_profile_excerpt()

_SYSTEM_PROMPT = (
    "You are the Medical Intelligence Officer for USS Starship Endeavour. "
    "You generate structured personal health intelligence briefs for Captain TJR. "
    "Rules: "
    "Only synthesise from the data provided — never invent patterns. "
    "Be direct and specific; cite the data behind each observation. "
    "If data is insufficient to identify a pattern, say so rather than speculate. "
    "Write in clear plain English. "
    "Focus on what is actionable for someone managing chronic pain and recovery."
    + (f"\n\nCAPTAIN PROFILE CONTEXT (source: captain_profile_knowledge_base v1.0):\n{_CAPTAIN_PROFILE_EXCERPT}" if _CAPTAIN_PROFILE_EXCERPT else "")
)

_EXPECTED_KEYS = {"situation", "patterns_noticed", "what_it_means",
                  "recommended_focus", "watch_items"}


class HealthLLMProvider:
    """
    Attempts each provider in preference order.
    Never raises — returns (None, None) on total failure.
    """

    def generate(self, prompt: str) -> tuple[Optional[str], Optional[str]]:
        """
        Returns (raw_text, provider_name) or (None, None) if all fail.
        raw_text is the model's full response string; parsing is the caller's job.
        """
        providers = [
            ("gemini-2.5-flash", self._gemini),
            ("mistral-small",    self._mistral),
            (_OLLAMA_MODEL,      self._ollama),
        ]
        for name, fn in providers:
            try:
                result = fn(prompt)
                if result:
                    log.info("Health LLM narrative generated via %s (%d chars)", name, len(result))
                    return result, name
            except Exception as exc:
                log.warning("Health LLM provider %s failed: %s", name, exc)

        log.warning("All health LLM providers failed — narrative will use deterministic fallback")
        return None, None

    def _gemini(self, prompt: str) -> Optional[str]:
        if not _GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY not set")
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.5-flash:generateContent?key={_GEMINI_API_KEY}"
        )
        body = json.dumps({
            "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 1024, "temperature": 0.3},
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

    def _mistral(self, prompt: str) -> Optional[str]:
        if not _MISTRAL_API_KEY:
            raise RuntimeError("MISTRAL_API_KEY not set")
        body = json.dumps({
            "model": "mistral-small-latest",
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            "max_tokens": 1024,
            "temperature": 0.3,
        }).encode()
        req = urllib.request.Request(
            "https://api.mistral.ai/v1/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {_MISTRAL_API_KEY}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"].strip()

    def _ollama(self, prompt: str) -> Optional[str]:
        body = json.dumps({
            "model": _OLLAMA_MODEL,
            "prompt": f"{_SYSTEM_PROMPT}\n\n{prompt}",
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 800},
        }).encode()
        req = urllib.request.Request(
            f"{_OLLAMA_BASE_URL}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        return data.get("response", "").strip()


def parse_llm_narrative(raw: str) -> Optional[dict]:
    """
    Extract and validate the JSON narrative object from a raw LLM response.

    Returns a dict with keys: situation, patterns_noticed, what_it_means,
    recommended_focus, watch_items — or None if parsing fails or keys are missing.
    """
    if not raw:
        return None
    try:
        clean = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        clean = re.sub(r"\s*```\s*$", "", clean)
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            data = json.loads(clean)
        if not isinstance(data, dict):
            return None
        if not _EXPECTED_KEYS.issubset(data.keys()):
            missing = _EXPECTED_KEYS - data.keys()
            log.warning("LLM narrative missing keys: %s", missing)
            return None
        return {k: data[k] for k in _EXPECTED_KEYS}
    except Exception as exc:
        log.warning("Failed to parse LLM health narrative JSON: %s", exc)
        return None
