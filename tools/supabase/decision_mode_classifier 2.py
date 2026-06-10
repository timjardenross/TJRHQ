#!/usr/bin/env python3
"""Decision Mode Classifier for USS-TJR-MSN-0009A/B.

Determines the dominant decision type for a question so Commander TJR can
apply the appropriate response framework.

Supported modes:
    strategic     — prioritisation, investment, build vs defer choices
    operational   — implementation, sequencing, execution guidance
    architectural — component placement, service interaction, system design
    governance    — ownership, approval, accountability

Classification strategy (MSN-0009B):
    1. If COMMANDER_SYNTHESIS_PROVIDER=ollama, try a lightweight LLM call.
       Falls back silently to rules-based if Ollama is unavailable or returns
       an unrecognised mode.
    2. Rules-based signal matching is always the fallback and works without
       any external dependency.

Usage:
    from decision_mode_classifier import classify_decision_mode, DecisionMode
    mode = classify_decision_mode("Should we prioritise Slack over Voice Core?")
    print(mode.value)  # "strategic"
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum


class DecisionMode(str, Enum):
    STRATEGIC = "strategic"
    OPERATIONAL = "operational"
    ARCHITECTURAL = "architectural"
    GOVERNANCE = "governance"


@dataclass(frozen=True)
class DecisionClassification:
    mode: DecisionMode
    confidence: int          # 0–100
    matched_signals: list[str]
    rationale: str


# ---------------------------------------------------------------------------
# Signal tables — order within each group matters (specificity first)
# ---------------------------------------------------------------------------

_STRATEGIC_SIGNALS = [
    # Priority / investment choices
    "should we prioritise",
    "should we invest",
    "should we build",
    "should we deploy",
    "should we proceed",
    "should we delay",
    "should we defer",
    "should we adopt",
    "should we move",
    # Comparative / trade-off frames
    "over voice core",
    "before slack",
    "before voice",
    "vs ",
    "versus",
    "or ",          # "slack or voice"
    # Strategic intent markers
    "what is the current bottleneck",
    "bottleneck",
    "current priority",
    "current focus",
    "strategic",
    "now or later",
    "right time",
    "is it worth",
    "what should uss tjr",
    "should uss tjr",
    # Mission-level framing
    "mission priority",
    "mission focus",
    "roadmap priority",
    "next mission",
]

_OPERATIONAL_SIGNALS = [
    "how should this be implemented",
    "how should we implement",
    "what sequence",
    "what order",
    "step by step",
    "how do we",
    "how should we build",
    "how to build",
    "how to implement",
    "how to deploy",
    "implementation plan",
    "execution plan",
    "migration plan",
    "migration path",
    "how should we run",
    "what steps",
    "what is the process",
    "what process",
    "rollout",
    "release plan",
    "sprint plan",
]

_ARCHITECTURAL_SIGNALS = [
    "where should this",
    "where should the",
    "where does this",
    "where should it",
    "how should this service",
    "how should this component",
    "how should the service",
    "how should the component",
    "service boundary",
    "component boundary",
    "should sit in",
    "should live in",
    "should live under",
    "data model",
    "schema design",
    "api design",
    "database design",
    "system design",
    "module boundary",
    "interface between",
    "coupling",
    "dependency between",
    "architecture",
    "infrastructure",
]

_GOVERNANCE_SIGNALS = [
    "who owns",
    "who approves",
    "who is responsible",
    "who decides",
    "who should own",
    "who should approve",
    "who should decide",
    "accountability",
    "ownership",
    "decision rights",
    "raci",
    "approval process",
    "who reviews",
    "governance",
    "authority",
    "escalation path",
    "who signs off",
]

# Weighted groups: (signals, mode, base_score_per_match)
_SIGNAL_GROUPS = [
    (_STRATEGIC_SIGNALS,     DecisionMode.STRATEGIC,     15),
    (_OPERATIONAL_SIGNALS,   DecisionMode.OPERATIONAL,   15),
    (_ARCHITECTURAL_SIGNALS, DecisionMode.ARCHITECTURAL, 15),
    (_GOVERNANCE_SIGNALS,    DecisionMode.GOVERNANCE,    20),
]


def classify_decision_mode(question: str) -> DecisionClassification:
    """Classify the dominant decision mode of a question.

    MSN-0009B: When COMMANDER_SYNTHESIS_PROVIDER=ollama, tries a lightweight
    LLM call first for novel phrasings. Falls back to rules-based on any
    failure — including network error, timeout, or unrecognised LLM output.
    """
    provider = os.environ.get("COMMANDER_SYNTHESIS_PROVIDER", "deterministic").lower()
    if provider == "ollama":
        try:
            return _llm_classify(question)
        except Exception:  # noqa: BLE001
            pass  # silent fallback — rules-based is always available

    return _rules_classify(question)


def _rules_classify(question: str) -> DecisionClassification:
    """Rules-based signal matching — fast, dependency-free."""
    lowered = question.lower().strip()
    scores: dict[DecisionMode, int] = {mode: 0 for mode in DecisionMode}
    matched: dict[DecisionMode, list[str]] = {mode: [] for mode in DecisionMode}

    for signals, mode, weight in _SIGNAL_GROUPS:
        for signal in signals:
            if signal in lowered:
                scores[mode] += weight
                matched[mode].append(signal.strip())

    best_mode = max(scores, key=lambda m: scores[m])
    best_score = scores[best_mode]

    if best_score == 0:
        return DecisionClassification(
            mode=DecisionMode.OPERATIONAL,
            confidence=40,
            matched_signals=[],
            rationale="No strong decision signals detected. Defaulting to operational guidance.",
        )

    confidence = min(95, 50 + best_score)
    rationale = _rationale_for(best_mode, matched[best_mode])
    return DecisionClassification(
        mode=best_mode,
        confidence=confidence,
        matched_signals=matched[best_mode][:5],
        rationale=rationale,
    )


def _llm_classify(question: str) -> DecisionClassification:
    """Lightweight LLM classification via Ollama (MSN-0009B).

    Uses a tiny, structured prompt and parses the JSON response.
    Raises on any network or parsing error so the caller can fall back.
    """
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = os.environ.get("COMMANDER_SYNTHESIS_MODEL", "qwen3:8b")
    timeout = float(os.environ.get("COMMANDER_SYNTHESIS_TIMEOUT_SECONDS", "30"))

    prompt = (
        "/no_think\n"
        "Classify this question into exactly one decision mode.\n"
        "Modes: strategic, operational, architectural, governance\n\n"
        "strategic: prioritisation, investment, build-vs-defer choices\n"
        "operational: implementation, sequencing, execution guidance\n"
        "architectural: component placement, service design, system boundaries\n"
        "governance: ownership, approval, accountability\n\n"
        f"Question: {question}\n\n"
        'Respond with ONLY valid JSON: {"mode": "<mode>", "confidence": <0-100>, "rationale": "<one sentence>"}\n'
        "Do not include any other text."
    )

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {"temperature": 0.0},
    }).encode("utf-8")

    request = urllib.request.Request(
        f"{base_url}/api/generate",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    raw = (body.get("response") or "").strip()
    # Strip <think>...</think> blocks in case the model leaks them
    import re
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    # Extract first JSON object
    match = re.search(r"\{.*?\}", raw, flags=re.DOTALL)
    if not match:
        raise ValueError(f"LLM returned no JSON: {raw!r}")
    parsed = json.loads(match.group())

    mode_str = parsed.get("mode", "").lower().strip()
    try:
        mode = DecisionMode(mode_str)
    except ValueError:
        raise ValueError(f"LLM returned unrecognised mode: {mode_str!r}")

    confidence = int(parsed.get("confidence", 70))
    rationale = str(parsed.get("rationale", "LLM classification."))

    return DecisionClassification(
        mode=mode,
        confidence=confidence,
        matched_signals=["llm_classification"],
        rationale=f"[LLM] {rationale}",
    )


def _rationale_for(mode: DecisionMode, signals: list[str]) -> str:
    top = signals[0] if signals else "general framing"
    if mode == DecisionMode.STRATEGIC:
        return (
            f"Question involves a prioritisation or investment choice "
            f"(detected: {top!r}). Commander should produce a recommendation, not a summary."
        )
    if mode == DecisionMode.OPERATIONAL:
        return (
            f"Question asks for implementation or sequencing guidance "
            f"(detected: {top!r}). Commander should produce execution steps."
        )
    if mode == DecisionMode.ARCHITECTURAL:
        return (
            f"Question involves component placement or system design "
            f"(detected: {top!r}). Commander should produce an architecture recommendation."
        )
    if mode == DecisionMode.GOVERNANCE:
        return (
            f"Question involves ownership or approval authority "
            f"(detected: {top!r}). Commander should produce an ownership recommendation."
        )
    return "No rationale available."
