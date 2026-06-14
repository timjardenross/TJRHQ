"""
Narrative Intelligence — WP6 / Sprint C (G-014)

Extracts recurring themes, constraints, concerns, and positive improvements
from free-text fields in captains_log_entries:
  - overall_note
  - what_happened

Uses the HealthLLMProvider chain (Gemini → Mistral → Ollama).
Falls back to frequency-based keyword extraction when LLM is unavailable.

Usage:
    from core.health.narrative_intelligence import extract_narrative_intelligence
    result = extract_narrative_intelligence(entries)
"""

from __future__ import annotations

import json
import logging
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "core" / "health"))

from health_llm import HealthLLMProvider, parse_llm_narrative

log = logging.getLogger(__name__)

MIN_ENTRIES_FOR_NLP = 3

_CAPTAIN_PROFILE_PATH = _REPO_ROOT / "knowledge" / "memory" / "captain_profile.txt"


def _load_health_exec_excerpt() -> str:
    """Return HEALTH PROFILE + EXECUTIVE FUNCTION SUPPORT sections from the captain profile."""
    try:
        text = _CAPTAIN_PROFILE_PATH.read_text(encoding="utf-8", errors="replace")
        m = re.search(
            r"(={10,}\s*\nHEALTH PROFILE\s*\n={10,}.+?)(={10,}\s*\nPROFESSIONAL EXPERTISE)",
            text, re.DOTALL,
        )
        return m.group(1).strip() if m else ""
    except Exception:
        return ""


_CAPTAIN_PROFILE_EXCERPT = _load_health_exec_excerpt()

_PROFILE_CONTEXT = (
    f"\n\nCAPTAIN PROFILE CONTEXT (source: captain_profile_knowledge_base v1.0):\n{_CAPTAIN_PROFILE_EXCERPT}"
    if _CAPTAIN_PROFILE_EXCERPT else ""
)

_SYSTEM_PROMPT = (
    "You are the Medical Intelligence Officer for USS Starship Endeavour.\n"
    "You analyse the Captain's personal log entries to extract patterns and intelligence.\n"
    "You respond ONLY with valid JSON — no markdown fences, no preamble.\n"
    "You surface evidence-backed findings only. You do not speculate about health conditions.\n"
    "You do not include any clinical diagnoses, medication names, or medical advice."
    + _PROFILE_CONTEXT
)

_NLP_JSON_KEYS = {
    "recurring_themes", "constraints", "concerns", "positive_improvements", "summary",
    "pain_trigger_patterns", "pain_reliever_patterns", "effective_coping_strategies",
}

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "was", "is", "are", "were", "have", "has", "had", "be",
    "been", "being", "do", "did", "does", "will", "would", "could", "should",
    "may", "might", "that", "this", "it", "i", "my", "me", "we", "you",
    "he", "she", "they", "so", "from", "by", "as", "up", "out", "no",
    "not", "very", "some", "all", "also", "then", "than", "just", "good",
    "day", "today", "morning", "night", "week", "time", "home", "work",
    "worked", "working", "wfh", "got", "get", "went", "going",
}


def _build_nlp_prompt(entries: List[Dict[str, Any]]) -> str:
    notes = []
    for e in sorted(entries, key=lambda x: x.get("log_date", "")):
        dt = e.get("log_date", "unknown")
        note = (e.get("overall_note") or "").strip()
        happened = (e.get("what_happened") or "").strip()
        triggers = (e.get("pain_triggers") or "").strip()
        relievers = (e.get("pain_relievers") or "").strip()
        coping = (e.get("coping_strategies") or "").strip()
        activity = (e.get("activity_impact") or "").strip()
        if note or happened or triggers or relievers or coping or activity:
            parts = [f"[{dt}]"]
            if note:      parts.append(f"note: {note}")
            if happened:  parts.append(f"happened: {happened}")
            if triggers:  parts.append(f"pain_triggers: {triggers}")
            if relievers: parts.append(f"pain_relievers: {relievers}")
            if coping:    parts.append(f"coping: {coping}")
            if activity:  parts.append(f"activity_impact: {activity}")
            notes.append(" | ".join(parts))

    if not notes:
        return ""

    entries_text = "\n".join(notes)
    return f"""{_SYSTEM_PROMPT}

Analyse these Captain's log entries and extract intelligence:

{entries_text}

Return a JSON object with exactly these keys:
{{
  "recurring_themes": ["theme1", "theme2"],
  "constraints": ["constraint1", "constraint2"],
  "concerns": ["concern1", "concern2"],
  "positive_improvements": ["improvement1", "improvement2"],
  "pain_trigger_patterns": ["trigger1", "trigger2"],
  "pain_reliever_patterns": ["reliever1", "reliever2"],
  "effective_coping_strategies": ["strategy1", "strategy2"],
  "summary": "2-3 sentence intelligence summary"
}}

Rules:
- recurring_themes: topics or activities that appear across multiple entries
- constraints: things that limited the Captain (physical, logistical, situational)
- concerns: negative patterns worth monitoring
- positive_improvements: signs of improvement or positive momentum
- pain_trigger_patterns: activities, postures, or conditions that consistently worsened pain
- pain_reliever_patterns: actions or conditions that consistently helped manage pain
- effective_coping_strategies: coping methods that appear repeatedly or are noted as helpful
- Only include items with evidence from 2+ entries. Return empty arrays if nothing qualifies.
- If pain_triggers/relievers/coping fields are absent from all entries, return empty arrays for those keys.
- summary: factual, evidence-based, no speculation"""


def _parse_nlp_response(raw: str) -> Optional[Dict[str, Any]]:
    """Parse NLP response JSON; returns None on failure."""
    if not raw:
        return None
    # Strip markdown fences
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    try:
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            return None
        if not _NLP_JSON_KEYS.issubset(data.keys()):
            missing = _NLP_JSON_KEYS - data.keys()
            log.debug("NLP response missing keys: %s", missing)
            return None
        return data
    except json.JSONDecodeError:
        return None


def _keyword_fallback(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Deterministic fallback: extract top keywords from narrative fields.
    Returns a simplified structure matching the LLM schema.
    """
    _ALL_TEXT_FIELDS = (
        "overall_note", "what_happened",
        "pain_triggers", "pain_relievers", "coping_strategies", "activity_impact",
    )
    words: List[str] = []
    for e in entries:
        for field in _ALL_TEXT_FIELDS:
            text = (e.get(field) or "").lower()
            tokens = re.findall(r"\b[a-z]{4,}\b", text)
            words.extend(t for t in tokens if t not in _STOPWORDS)

    top_words = [w for w, _ in Counter(words).most_common(10)]

    return {
        "recurring_themes": top_words[:5] if top_words else [],
        "constraints": [],
        "concerns": [],
        "positive_improvements": [],
        "pain_trigger_patterns": [],
        "pain_reliever_patterns": [],
        "effective_coping_strategies": [],
        "summary": (
            f"Keyword analysis of {len(entries)} entries. "
            f"Most frequent terms: {', '.join(top_words[:5]) if top_words else 'none'}. "
            "LLM narrative unavailable — install Gemini, Mistral, or Ollama for full NLP intelligence."
        ),
        "source": "keyword_fallback",
    }


def extract_narrative_intelligence(
    entries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Extract intelligence from narrative fields in log entries.

    Args:
        entries: List of captains_log_entry dicts.

    Returns dict with:
        recurring_themes:      List[str]
        constraints:           List[str]
        concerns:              List[str]
        positive_improvements: List[str]
        summary:               str
        source:                'llm' | 'keyword_fallback'
        provider:              str or None (LLM provider name)
        entries_analysed:      int
        status:                'ok' | 'insufficient_data' | 'no_text'
    """
    _TEXT_FIELDS = (
        "overall_note", "what_happened",
        "pain_triggers", "pain_relievers", "coping_strategies", "activity_impact",
    )
    # Filter to entries with at least one narrative field
    text_entries = [
        e for e in entries
        if any((e.get(f) or "").strip() for f in _TEXT_FIELDS)
    ]

    _EMPTY_CBT: Dict[str, Any] = {
        "pain_trigger_patterns": [],
        "pain_reliever_patterns": [],
        "effective_coping_strategies": [],
    }

    if len(text_entries) < MIN_ENTRIES_FOR_NLP:
        return {
            "recurring_themes": [],
            "constraints": [],
            "concerns": [],
            "positive_improvements": [],
            **_EMPTY_CBT,
            "summary": (
                f"Insufficient narrative data: {len(text_entries)} entries with text "
                f"(minimum {MIN_ENTRIES_FOR_NLP} required)."
            ),
            "source": None,
            "provider": None,
            "entries_analysed": len(text_entries),
            "status": "insufficient_data" if text_entries else "no_text",
        }

    prompt = _build_nlp_prompt(text_entries)
    if not prompt:
        return {
            "recurring_themes": [], "constraints": [], "concerns": [],
            "positive_improvements": [], **_EMPTY_CBT,
            "summary": "No narrative text found.",
            "source": None, "provider": None, "entries_analysed": 0, "status": "no_text",
        }

    # Attempt LLM extraction
    provider_obj = HealthLLMProvider()
    raw, provider_name = provider_obj.generate(prompt)

    if raw:
        parsed = _parse_nlp_response(raw)
        if parsed:
            return {
                **parsed,
                "source": "llm",
                "provider": provider_name,
                "entries_analysed": len(text_entries),
                "status": "ok",
            }

    # Fall back to keyword extraction
    result = _keyword_fallback(text_entries)
    result.update({
        "provider": None,
        "entries_analysed": len(text_entries),
        "status": "ok",
    })
    return result
