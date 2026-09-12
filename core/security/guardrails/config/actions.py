"""Custom Colang actions for the TJR Model Router's input/output rails
(USS-TJR-MSN-0366 Stream 5). Auto-discovered by NeMo Guardrails from this
config directory (any @action-decorated function here is registered without
extra wiring).

Deterministic pre-filters, deliberately NOT model-based: both run before
(and independently of) the LLM-backed self_check_input/self_check_output
actions in nemoguardrails.library.self_check, so a well-known attack shape
is blocked even when the local checking model (Ollama gemma3:4b) is slow,
unreachable, or simply answers the semantic check wrong. See rails.co for
how the two layers compose.
"""
from __future__ import annotations

import re

from nemoguardrails.actions import action

# Matches the common "make the model ignore/override its own instructions"
# family of prompt-injection phrasing, plus the classic "DAN"/"developer
# mode" persona-override jailbreak and direct system-prompt-exfiltration
# asks. Deliberately narrow (real phrases from real jailbreak writeups, not
# single common words) to keep false positives on ordinary operational
# prompts low — this is a pre-filter sitting in front of the semantic
# self-check, not the only line of defense.
_JAILBREAK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+|any\s+)?(previous|prior|above|earlier)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+|any\s+)?(previous|prior|above|earlier)\s+instructions", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+|any\s+)?(previous|prior|above|earlier)\s+(instructions|rules)", re.IGNORECASE),
    re.compile(r"reveal\s+(your|the)\s+system\s+prompt", re.IGNORECASE),
    re.compile(r"(print|show|output)\s+(your|the)\s+(system\s+prompt|instructions)\s+verbatim", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(DAN|in\s+developer\s+mode|an?\s+unrestricted)", re.IGNORECASE),
    re.compile(r"act\s+as\s+an?\s+unfiltered", re.IGNORECASE),
    re.compile(r"pretend\s+(you\s+have|to\s+have)\s+no\s+(restrictions|rules|guidelines|filters)", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
]

# Matches obviously credential-shaped strings a cloud model's response
# should never legitimately contain (OWASP LLM02/LLM06-adjacent output
# check — the platform's own secrets, not the caller's business data).
_CREDENTIAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),           # OpenAI/Anthropic-style API keys
    re.compile(r"AKIA[0-9A-Z]{16}"),              # AWS access key id
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),        # Google API key
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),    # GitHub tokens
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]


@action(name="tjr_keyword_jailbreak_check")
async def tjr_keyword_jailbreak_check(user_message: str = "") -> bool:
    """Return True if `user_message` matches a known prompt-injection /
    jailbreak phrasing. Fully deterministic — no model call."""
    text = user_message or ""
    return any(p.search(text) for p in _JAILBREAK_PATTERNS)


@action(name="tjr_credential_leak_check")
async def tjr_credential_leak_check(bot_message: str = "") -> bool:
    """Return True if `bot_message` contains a credential-shaped string.
    Fully deterministic — no model call."""
    text = bot_message or ""
    return any(p.search(text) for p in _CREDENTIAL_PATTERNS)
