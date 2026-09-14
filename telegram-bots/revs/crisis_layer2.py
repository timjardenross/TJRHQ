"""Layer-2 crisis confirmation — README.md's "Known gaps" / blocker #2,
safety.py's own docstring: a recommended-but-unbuilt LLM disambiguation
pass for bare method/acquisition nouns ("pills", "rope", "bought") that
Layer 1's regex (safety.py's classify_free_text) deliberately excludes as
too generic to match without context — a major false-positive source on
their own.

This is net-new work, not a retrofit — no Layer 2 code existed before
this module. It runs strictly AFTER Layer 1 in app.py's _crisis_gate:
Layer 1 already catches direct/indirect ideation language with its
deliberately high-recall regex, so this module's whole job is the narrow
gap Layer 1 was built to leave open — an ambiguous method/acquisition word
that's only a crisis signal in context ("I've been saving up my pills" vs.
"took a pill for my headache").

Two-stage design, cheapest gate first:
  1. should_run_layer2() — a deterministic regex pre-filter over the
     ambiguous words themselves. This is purely a cost/latency gate (skip
     the LLM call on the overwhelming majority of ordinary messages) — it
     is deliberately broad, same recall-over-precision bias as Layer 1,
     since a false positive here only costs one LLM call, not a
     user-facing action.
  2. confirm_crisis_context() — the actual LLM disambiguation, gated
     behind stage 1. Its verdict is what decides whether the user sees the
     crisis-response message and the Captain gets escalated.

Same failure principle as safety.py's own docstring: being wrong toward
"flagged, but wasn't a crisis" costs one extra gentle message; being wrong
the other way costs everything. Applied here as: ANY failure in the LLM
stage (every provider down, an unparseable response, a response missing
the expected shape) resolves to "uncertain" — treated identically to a
"crisis" verdict by the caller, never silently downgraded to "not_crisis".
A Layer 2 outage never makes the bot LESS safe than not having Layer 2 at
all; it only means the narrow gap goes uncovered for that message, same as
before this module existed — it must never actively suppress a Layer-1
result or invent a false "all clear."

Still needs the same adversarial review (§8.3) safety.py's pattern list
does — a disambiguation pass is not the same thing as a reviewed one.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys

# core.llm.provider_chain needs the repo root on sys.path. app.py's own
# sys.path insertion only adds this bot's own directory (for its sibling
# flat-import style), and this module is imported before app.py imports
# config.py (which is the sibling that normally does this) — so don't
# depend on import order, mirror config.py's own repo-root insertion here.
_BOT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_BOT_DIR))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core.llm.provider_chain import (
    call_gemini,
    call_mistral,
    call_ollama,
)

log = logging.getLogger("revs-bot.crisis_layer2")

# Read lazily (inside _call_provider_chain), not as module-level constants
# — app.py imports this module before it imports config.py (see app.py's
# own comment on sibling-import ordering), so the shared-config dotenv
# load (platform-runtime/.env) hasn't necessarily run yet at this module's
# import time. Reading os.getenv() at call time instead means it always
# sees whatever config.py has already loaded into os.environ by the time
# the crisis gate actually fires.

# Stage 1 pre-filter — bare method/acquisition nouns from the research
# summary's taxonomy (README.md blocker #2), the exact category safety.py
# names as deliberately excluded from Layer 1. Kept broad on purpose: this
# only gates an LLM call, not an escalation.
_AMBIGUOUS_PATTERNS = [
    r"\bpills?\b", r"\btablets?\b", r"\bmedication(s)?\b.{0,20}\bsaved\b",
    r"\boverdose\b", r"\bod'?d\b",
    r"\brope\b", r"\bnoose\b", r"\bhang(ing)?\b",
    r"\bbridge\b", r"\boff (the|a) (roof|building|balcony|ledge)\b",
    r"\bgun\b", r"\bfirearm\b", r"\bbullets?\b",
    r"\brazor blades?\b",
    r"\bexhaust\b", r"\bcarbon monoxide\b",
    r"\bstockpil\w*\b", r"\bsaved up\b", r"\bsaving up\b",
    r"\bhow many\b.{0,20}\b(pills|tablets|would it take)\b",
]
_AMBIGUOUS_RE = re.compile("|".join(_AMBIGUOUS_PATTERNS), re.IGNORECASE)

_VALID_VERDICTS = {"crisis", "not_crisis", "uncertain"}

_SYSTEM_PROMPT = """You are a safety-triage classifier for a peer-support app used by people managing chronic illness. A message has matched a keyword list of words that CAN relate to self-harm or suicide methods (e.g. "pills", "rope", "bridge") but are also extremely common in entirely ordinary contexts (medication logs, cooking, travel, hardware).

Your only job: decide whether THIS message, in context, shows a genuine risk indicator of suicidal ideation or self-harm intent — not whether the word itself is risky.

Respond with ONLY a JSON object, no other text, no markdown fence:
{"verdict": "crisis" | "not_crisis" | "uncertain", "reasoning": "<one short sentence>"}

- "crisis": the message shows real risk indicators in context (e.g. acquiring/counting a method, combined with despair, finality, or intent language).
- "not_crisis": the ambiguous word is clearly in an unrelated, ordinary context.
- "uncertain": you cannot confidently tell either way from this message alone.

When in doubt between "not_crisis" and "uncertain", always choose "uncertain" — a missed crisis is far worse than one extra flagged message."""


def should_run_layer2(text: str) -> bool:
    """Stage 1 — cheap, deterministic pre-filter. Callers should only reach
    this after Layer 1 (safety.py.classify_free_text) has already returned
    False for the same text; Layer 1's result already covers escalation
    for anything it catches."""
    if not text:
        return False
    return bool(_AMBIGUOUS_RE.search(text))


def _call_provider_chain(prompt: str) -> str | None:
    """One attempt per provider, first non-empty text wins. Never raises —
    a provider outage must degrade to the caller's fail-open handling, not
    crash the crisis gate."""
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    mistral_key = os.getenv("MISTRAL_API_KEY", "")
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_CRISIS_MODEL") or os.getenv("OLLAMA_MODEL", "qwen3:8b")
    providers = [
        ("gemini", lambda: call_gemini(_SYSTEM_PROMPT, prompt, api_key=gemini_key, max_output_tokens=150).text),
        ("mistral", lambda: call_mistral(_SYSTEM_PROMPT, prompt, api_key=mistral_key, max_tokens=150).text),
        ("ollama", lambda: call_ollama(_SYSTEM_PROMPT, prompt, base_url=ollama_base_url, model=ollama_model, num_predict=150).text),
    ]
    for name, fn in providers:
        try:
            result = fn()
            if result:
                return result
        except Exception as exc:  # noqa: BLE001 - per-provider attempt inside a fallback chain — one provider failing must not abort the chain
            log.warning("[crisis_layer2] %s provider failed: %s", name, exc)
    return None


def _parse_verdict(raw: str) -> str | None:
    """Strips a markdown code fence if present, then json.loads — same
    fence-stripping convention as scripts/self_improvement/router_client.py.
    Returns None (never a guessed default) unless the parsed object has a
    "verdict" field that is exactly one of the three known enum values —
    router_client.py's own docstring documents a real 5-day production
    incident caused by exactly this kind of unchecked LLM-JSON assumption,
    and this is a much higher-stakes surface than that one."""
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        if stripped.endswith("```"):
            stripped = stripped.rsplit("```", 1)[0]
        stripped = stripped.strip()
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    verdict = parsed.get("verdict")
    if verdict not in _VALID_VERDICTS:
        return None
    return verdict


async def confirm_crisis_context(text: str) -> str:
    """Stage 2 — the actual disambiguation. Always returns one of
    "crisis"/"not_crisis"/"uncertain"; never raises. Only "not_crisis" is
    ever safe for a caller to treat as "do nothing" — "crisis" and
    "uncertain" both mean the caller should run the same crisis-response
    path Layer 1 uses."""
    raw = await asyncio.to_thread(_call_provider_chain, text)
    if raw is None:
        log.warning("[crisis_layer2] all providers failed — defaulting to 'uncertain' (fail open)")
        return "uncertain"
    verdict = _parse_verdict(raw)
    if verdict is None:
        log.warning("[crisis_layer2] unparseable/invalid verdict shape from LLM — defaulting to 'uncertain' (fail open): %r", raw[:200])
        return "uncertain"
    return verdict
