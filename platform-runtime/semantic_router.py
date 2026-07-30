"""
P5 — Semantic Specialist Routing

Upgrades specialist routing from keyword-based to semantic intent-based routing.
- Classifies user intent into semantic categories
- Scores specialists based on intent and context
- Assigns confidence levels (high/medium/low)
- Recommends secondary specialists
- Escalates ambiguous requests to Executive Officer (XO)
- Operates locally without paid API dependency
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import re


# ============================================================================
# Intent Categories
# ============================================================================

class Intent(Enum):
    """Semantic intent classification for routing decisions."""

    ARCHITECTURE_REVIEW = "architecture_review"
    IMPLEMENTATION_PLANNING = "implementation_planning"
    CODE_REVIEW = "code_review"
    MISSION_CREATION = "mission_creation"
    MISSION_GOVERNANCE = "mission_governance"
    DECISION_LOGGING = "decision_logging"
    KNOWLEDGE_MANAGEMENT = "knowledge_management"
    PRODUCT_SCOPE = "product_scope"
    RISK_ASSESSMENT = "risk_assessment"
    OPERATIONAL_RESILIENCE = "operational_resilience"
    WELLNESS_SUPPORT = "wellness_support"
    DOCUMENTATION = "documentation"
    DEBUGGING = "debugging"
    INFRASTRUCTURE = "infrastructure"
    SECURITY_REVIEW = "security_review"
    UNKNOWN = "unknown"


class ConfidenceBand(Enum):
    """Confidence level bands for routing decisions."""

    HIGH = "high"  # 0.80–1.00
    MEDIUM = "medium"  # 0.55–0.79
    LOW = "low"  # 0.00–0.54


# ============================================================================
# Specialist Definitions
# ============================================================================

SPECIALIST_DEFINITIONS = {
    "Executive Officer (XO)": {
        "role": "Chief command authority",
        "domains": ["command", "governance", "escalation"],
        "intents": [Intent.MISSION_GOVERNANCE],
        "description": "Strategic oversight, triage, escalation authority"
    },
    "Chief Engineer": {
        "role": "Technical architecture authority",
        "domains": ["engineering", "architecture", "infrastructure"],
        "intents": [Intent.ARCHITECTURE_REVIEW, Intent.INFRASTRUCTURE, Intent.SECURITY_REVIEW],
        "description": "System design, technical decisions, infrastructure"
    },
    "Product Owner": {
        "role": "Product strategy and scope authority",
        "domains": ["product", "strategy", "prioritization"],
        "intents": [Intent.PRODUCT_SCOPE, Intent.IMPLEMENTATION_PLANNING],
        "description": "Feature scope, product fit, prioritization"
    },
    "Coder Agent": {
        "role": "Implementation and coding authority",
        "domains": ["development", "coding", "implementation"],
        "intents": [Intent.CODE_REVIEW, Intent.IMPLEMENTATION_PLANNING, Intent.DEBUGGING],
        "description": "Code implementation, debugging, feature development"
    },
    "Knowledge Officer": {
        "role": "Knowledge management and documentation authority",
        "domains": ["knowledge", "documentation", "governance"],
        "intents": [Intent.KNOWLEDGE_MANAGEMENT, Intent.DOCUMENTATION],
        "description": "Documentation, knowledge base, information architecture"
    },
    "Mission Scribe": {
        "role": "Mission tracking and recording authority",
        "domains": ["missions", "governance", "logging"],
        "intents": [Intent.MISSION_CREATION, Intent.DECISION_LOGGING],
        "description": "Mission creation, decision logging, governance records"
    },
    "Risk Officer": {
        "role": "Risk assessment and resilience authority",
        "domains": ["risk", "security", "resilience"],
        "intents": [Intent.RISK_ASSESSMENT, Intent.OPERATIONAL_RESILIENCE, Intent.SECURITY_REVIEW],
        "description": "Risk assessment, operational resilience, security"
    },
    "Wellness Specialist": {
        "role": "Health and wellness authority",
        "domains": ["wellness", "health", "support"],
        "intents": [Intent.WELLNESS_SUPPORT],
        "description": "Health, wellness, personal support"
    },
    "Number One": {
        "role": "Mission coordination and support",
        "domains": ["coordination", "missions", "operations"],
        "intents": [Intent.MISSION_CREATION],
        "description": "Mission coordination, operational support, escalation handling"
    }
}


# ============================================================================
# Intent Signals
# ============================================================================

INTENT_SIGNALS = {
    Intent.ARCHITECTURE_REVIEW: {
        "keywords": [
            "architecture", "system design", "design decision", "technical design",
            "scalability", "could break", "failure points", "risk assessment",
            "system resilience", "design pattern", "module structure", "service design",
            "how should we design", "architectural", "design this system"
        ],
        "weight": 100
    },
    Intent.IMPLEMENTATION_PLANNING: {
        "keywords": [
            "implement", "implementation plan", "how should we build", "build approach",
            "development plan", "feature implementation", "technical approach",
            "build strategy", "development strategy", "phased approach"
        ],
        "weight": 90
    },
    Intent.CODE_REVIEW: {
        "keywords": [
            "code review", "review this code", "review the code", "code quality",
            "coding standards", "code smell", "refactor", "code improvement",
            "review for bugs", "check for issues", "draft a github issue"
        ],
        "weight": 85
    },
    Intent.MISSION_CREATION: {
        "keywords": [
            "create a mission", "create mission", "new mission", "mission to",
            "task to", "work on", "build this", "implement this as a mission"
        ],
        "weight": 95
    },
    Intent.MISSION_GOVERNANCE: {
        "keywords": [
            "mission status", "mission governance", "mission priorities", "prioritize missions",
            "mission ownership", "who owns this mission", "mission assignment",
            "mission decisions", "mission authority"
        ],
        "weight": 100
    },
    Intent.DECISION_LOGGING: {
        "keywords": [
            "capture this decision", "log decision", "record decision", "decision log",
            "document this choice", "why did we decide", "decision rationale",
            "decision record", "architectural decision", "capture the decision"
        ],
        "weight": 90
    },
    Intent.KNOWLEDGE_MANAGEMENT: {
        "keywords": [
            "knowledge base", "knowledge management", "document this", "documentation",
            "information architecture", "how do we know", "source of truth",
            "knowledge system", "store knowledge"
        ],
        "weight": 85
    },
    Intent.PRODUCT_SCOPE: {
        "keywords": [
            "is this feature worth building", "product fit", "product scope",
            "feature worth", "build or not", "should we build", "feature priority",
            "product decision", "scope creep", "out of scope", "worth building"
        ],
        "weight": 95
    },
    Intent.RISK_ASSESSMENT: {
        "keywords": [
            "risk", "risks", "risk assessment", "risk analysis", "what could break",
            "failure points", "breaking points", "risk mitigation", "failure scenarios",
            "resilience", "operational risk", "resilience risk"
        ],
        "weight": 100
    },
    Intent.OPERATIONAL_RESILIENCE: {
        "keywords": [
            "operational resilience", "resilience", "fail over", "failure recovery",
            "system resilience", "disaster recovery", "business continuity",
            "uptime", "availability", "reliability"
        ],
        "weight": 90
    },
    Intent.WELLNESS_SUPPORT: {
        "keywords": [
            "health", "wellness", "wellbeing", "medical", "pain", "chronic pain",
            "health routine", "wellness routine", "recovery", "support"
        ],
        "weight": 90
    },
    Intent.DOCUMENTATION: {
        "keywords": [
            "document", "documentation", "write docs", "readme", "guide",
            "howto", "document this", "explain this", "draft documentation",
            "document the decision"
        ],
        "weight": 80
    },
    Intent.DEBUGGING: {
        "keywords": [
            "debug", "debugging", "bug", "fix bug", "error", "exception",
            "crash", "broken", "not working", "failure scenario"
        ],
        "weight": 85
    },
    Intent.INFRASTRUCTURE: {
        "keywords": [
            "infrastructure", "deployment", "infrastructure design", "infrastructure as code",
            "devops", "container", "kubernetes", "deployment strategy",
            "infrastructure architecture"
        ],
        "weight": 85
    },
    Intent.SECURITY_REVIEW: {
        "keywords": [
            "security", "security review", "security assessment", "security risk",
            "vulnerability", "threat", "attack surface", "security audit"
        ],
        "weight": 100
    }
}


# ============================================================================
# Routing Result Data Class
# ============================================================================

@dataclass
class RoutingDecision:
    """Complete routing decision with full context."""

    primary_specialist: str
    secondary_specialists: list[str] = field(default_factory=list)
    division: str = "Command"
    intent: Intent = Intent.UNKNOWN
    confidence: float = 0.5
    confidence_band: ConfidenceBand = ConfidenceBand.LOW
    rationale: str = ""
    escalate_to_xo: bool = False
    intent_signals_matched: list[str] = field(default_factory=list)
    specialist_scores: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "primary_specialist": self.primary_specialist,
            "secondary_specialists": self.secondary_specialists,
            "division": self.division,
            "intent": self.intent.value,
            "confidence": self.confidence,
            "confidence_band": self.confidence_band.value,
            "rationale": self.rationale,
            "escalate_to_xo": self.escalate_to_xo,
            "intent_signals_matched": self.intent_signals_matched,
            "specialist_scores": self.specialist_scores
        }


# ============================================================================
# Intent Classification
# ============================================================================

def classify_intent(text: str) -> tuple[Intent, list[str], float]:
    """
    Classify user intent from request text.

    Returns: (intent, matched_signals, confidence)
    """
    text_lower = text.lower()
    intent_scores: dict[Intent, tuple[float, list[str]]] = {}

    for intent, signal_data in INTENT_SIGNALS.items():
        matched = []
        score = 0.0

        for keyword in signal_data["keywords"]:
            if keyword in text_lower:
                matched.append(keyword)
                score += signal_data["weight"]

        if matched:
            # Normalize by number of keywords to get 0-1 confidence
            max_possible = len(signal_data["keywords"]) * signal_data["weight"]
            normalized_confidence = min(1.0, score / max_possible)
            intent_scores[intent] = (normalized_confidence, matched)

    if not intent_scores:
        return Intent.UNKNOWN, [], 0.0

    # Get intent with highest confidence
    best_intent = max(intent_scores, key=lambda i: intent_scores[i][0])
    confidence, signals = intent_scores[best_intent]

    return best_intent, signals, confidence


# ============================================================================
# Specialist Scoring & Selection
# ============================================================================

def score_specialists_for_intent(intent: Intent) -> dict[str, float]:
    """Score all specialists based on intent match."""
    scores: dict[str, float] = {}

    for specialist, spec_def in SPECIALIST_DEFINITIONS.items():
        # Base score: is this intent in the specialist's domain?
        if intent in spec_def["intents"]:
            scores[specialist] = 1.0
        else:
            scores[specialist] = 0.3  # Low base score for other specialists

    return scores


def select_primary_specialist(
    intent: Intent,
    specialist_scores: dict[str, float],
    text: str
) -> str:
    """Select best-fit primary specialist."""
    # Sort by score
    ranked = sorted(specialist_scores.items(), key=lambda x: x[1], reverse=True)

    if not ranked:
        return "Executive Officer (XO)"

    best_specialist, best_score = ranked[0]

    # If score is too low, escalate to XO
    if best_score < 0.4:
        return "Executive Officer (XO)"

    return best_specialist


def select_secondary_specialists(
    primary: str,
    specialist_scores: dict[str, float],
    max_secondary: int = 2
) -> list[str]:
    """Select secondary specialist recommendations."""
    # Filter out primary and sort remaining
    candidates = [
        (name, score) for name, score in specialist_scores.items()
        if name != primary and score >= 0.4
    ]

    ranked = sorted(candidates, key=lambda x: x[1], reverse=True)
    return [name for name, _ in ranked[:max_secondary]]


# ============================================================================
# Confidence Calculation
# ============================================================================

def calculate_confidence(
    intent: Intent,
    specialist_scores: dict[str, float],
    intent_signals: list[str],
    text: str
) -> tuple[float, ConfidenceBand]:
    """Calculate overall confidence score 0-1 and band."""

    # Intent signal match contributes 0.5 to confidence
    intent_confidence = len(intent_signals) / 5.0 if intent_signals else 0.0
    intent_confidence = min(0.5, intent_confidence)

    # Specialist match contributes 0.5 to confidence
    if specialist_scores:
        best_score = max(specialist_scores.values())
        specialist_confidence = best_score * 0.5
    else:
        specialist_confidence = 0.0

    overall = intent_confidence + specialist_confidence

    if overall >= 0.80:
        band = ConfidenceBand.HIGH
    elif overall >= 0.55:
        band = ConfidenceBand.MEDIUM
    else:
        band = ConfidenceBand.LOW

    return overall, band


# ============================================================================
# Routing Engine
# ============================================================================

def route_request_semantic(text: str) -> RoutingDecision:
    """
    Route request using semantic intent analysis.

    Core algorithm:
    1. Classify intent from text
    2. Score specialists for that intent
    3. Select primary and secondary specialists
    4. Calculate confidence
    5. Escalate to XO if confidence is low
    6. Generate rationale
    """

    # Step 1: Classify intent
    intent, intent_signals, _ = classify_intent(text)

    # Step 2: Score specialists for this intent
    specialist_scores = score_specialists_for_intent(intent)

    # Step 3: Select specialists
    primary = select_primary_specialist(intent, specialist_scores, text)
    secondary = select_secondary_specialists(primary, specialist_scores)

    # Step 4: Calculate confidence
    confidence, confidence_band = calculate_confidence(
        intent, specialist_scores, intent_signals, text
    )

    # Step 5: Decide on escalation
    escalate_to_xo = confidence < 0.55 and intent == Intent.UNKNOWN

    if escalate_to_xo:
        primary = "Executive Officer (XO)"
        secondary = []

    # Step 6: Determine division
    division = SPECIALIST_DEFINITIONS[primary].get("role", "Command")

    # Step 7: Build rationale
    rationale = _build_rationale(
        intent, intent_signals, primary, confidence_band, escalate_to_xo
    )

    return RoutingDecision(
        primary_specialist=primary,
        secondary_specialists=secondary,
        division=division,
        intent=intent,
        confidence=confidence,
        confidence_band=confidence_band,
        rationale=rationale,
        escalate_to_xo=escalate_to_xo,
        intent_signals_matched=intent_signals,
        specialist_scores=specialist_scores
    )


def _build_rationale(
    intent: Intent,
    signals: list[str],
    specialist: str,
    confidence_band: ConfidenceBand,
    escalate: bool
) -> str:
    """Build human-readable routing rationale."""

    if escalate:
        return (
            f"Request lacks sufficient context to identify specialist domain. "
            f"Escalating to Executive Officer for clarification or triage."
        )

    signal_str = ", ".join(f"'{s}'" for s in signals[:3])
    if len(signals) > 3:
        signal_str += f", and {len(signals) - 3} more"

    return (
        f"Request intent is {intent.value.replace('_', ' ')}. "
        f"Detected signals: {signal_str}. "
        f"{specialist} is primary authority for {intent.value.replace('_', ' ')}. "
        f"Confidence: {confidence_band.value}."
    )


# ============================================================================
# Legacy Compatibility Layer
# ============================================================================

def enhance_router_with_semantic(legacy_routing: dict[str, Any]) -> dict[str, Any]:
    """
    Enhance existing routing result with semantic analysis.

    This preserves backward compatibility with existing router.py
    while adding semantic confidence scoring.
    """
    # Make a copy to avoid mutations
    enhanced = dict(legacy_routing)

    # Add semantic analysis
    primary = enhanced.get("assigned_specialists", ["Executive Officer (XO)"])[0]
    text = enhanced.get("_original_text", "")

    if text:
        semantic = route_request_semantic(text)
        enhanced["semantic_intent"] = semantic.intent.value
        enhanced["semantic_confidence"] = semantic.confidence
        enhanced["semantic_confidence_band"] = semantic.confidence_band.value
        enhanced["semantic_rationale"] = semantic.rationale

    return enhanced
