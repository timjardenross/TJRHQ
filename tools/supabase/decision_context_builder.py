#!/usr/bin/env python3
"""Decision Context Builder for USS-TJR-MSN-0009A.

Converts unstructured specialist outputs and challenge review into a standard
decision context that Commander TJR can use to make a clear recommendation —
rather than producing summaries, architecture commentary, or meeting notes.

Works in both normal Commander mode and Dual Commander Evaluation mode
(MSN-0010A). Both Commander models receive the same decision context.

Usage:
    from decision_context_builder import build_decision_context
    context = build_decision_context(question, classification, outputs, challenge, mission_context)
"""

from __future__ import annotations

from typing import Any

from challenge_review import ChallengeReview
from decision_mode_classifier import DecisionClassification, DecisionMode
from specialist_executor import SpecialistOutput


def build_decision_context(
    question: str,
    classification: DecisionClassification,
    outputs: list[SpecialistOutput],
    challenge: ChallengeReview | None,
    mission_context: dict[str, Any],
) -> dict[str, Any]:
    """Build a structured decision context for Commander TJR.

    Prevents Commander from receiving an unstructured information dump.
    Provides a standard frame: situation → bottleneck → options → positions → decision required.
    """
    options = _extract_options(question, outputs, classification)
    bottleneck = _infer_bottleneck(question, outputs, classification, mission_context)
    opportunity_cost = _infer_opportunity_cost(question, options, classification)
    time_to_value = _infer_time_to_value(options, outputs)
    reversibility = _infer_reversibility(question, classification)
    specialist_positions = _extract_specialist_positions(outputs, options)
    reviewer_position = _extract_reviewer_position(challenge, options) if challenge else None
    sources = sorted({source for output in outputs for source in output.sources})

    return {
        # --- Core decision frame ---
        "question": question,
        "decision_mode": classification.mode.value,
        "decision_mode_confidence": classification.confidence,
        "decision_mode_rationale": classification.rationale,
        # --- Situation ---
        "current_situation": _current_situation(outputs, mission_context),
        "current_bottleneck": bottleneck,
        # --- Options ---
        "options": options,
        # --- Specialist and reviewer positions ---
        "specialist_positions": specialist_positions,
        "reviewer_position": reviewer_position,
        # --- Strategic evaluation dimensions (MSN-0009A framework) ---
        "strategic_alignment": _strategic_alignment(question, classification, mission_context),
        "opportunity_cost": opportunity_cost,
        "time_to_value": time_to_value,
        "reversibility": reversibility,
        # --- Required decision ---
        "required_decision": _required_decision(question, classification, options),
        # --- Sources (preserved from specialist retrieval) ---
        "sources": sources,
        # --- Pass-through from mission context ---
        "mission_id": mission_context.get("mission_id"),
        "intent": mission_context.get("intent"),
    }


# ---------------------------------------------------------------------------
# Options extraction
# ---------------------------------------------------------------------------

def _extract_options(
    question: str,
    outputs: list[SpecialistOutput],
    classification: DecisionClassification,
) -> list[dict[str, str]]:
    """Identify the decision options from the question and specialist outputs.

    For strategic/binary questions, tries to extract two named options.
    For operational/architectural, returns a single 'proceed' option.
    """
    lowered = question.lower()

    # Explicit "A or B" patterns in strategic questions
    if classification.mode == DecisionMode.STRATEGIC:
        # Detect "X over Y" / "X before Y" / "X or Y" patterns
        over_terms = ["over", "before", "instead of", " or ", " vs ", " versus "]
        for sep in over_terms:
            if sep.strip() in lowered:
                parts = _split_on_separator(question, sep)
                if parts and len(parts) == 2:
                    opt_a, opt_b = parts
                    return [
                        {"label": "Option A", "description": opt_a.strip().capitalize()},
                        {"label": "Option B", "description": opt_b.strip().capitalize()},
                    ]

        # Detect "should we build X" → A=build, B=defer
        build_terms = ["should we build", "should we implement", "should we invest", "should we deploy"]
        for term in build_terms:
            if term in lowered:
                subject = question[lowered.index(term) + len(term):].strip(" ?")
                return [
                    {"label": "Option A", "description": f"Build / proceed with {subject}"},
                    {"label": "Option B", "description": f"Defer or deprioritise {subject}"},
                ]

    if classification.mode == DecisionMode.GOVERNANCE:
        return [
            {"label": "Option A", "description": "Assign clear ownership now."},
            {"label": "Option B", "description": "Defer ownership assignment pending further context."},
        ]

    # Operational / architectural — single path
    return [
        {"label": "Proceed", "description": "Execute the recommended path as described by specialists."},
    ]


def _split_on_separator(question: str, sep: str) -> list[str] | None:
    """Split a question string on a separator, returning two parts if clean."""
    lowered = question.lower()
    idx = lowered.find(sep.strip())
    if idx == -1:
        return None
    before = question[:idx].strip()
    after = question[idx + len(sep.strip()):].strip(" ?")
    # Remove leading interrogatives from the before part
    for prefix in ["should we prioritise ", "should we prefer ", "should uss tjr prioritise "]:
        before_lower = before.lower()
        if before_lower.startswith(prefix):
            before = before[len(prefix):]
            break
    if before and after:
        return [before, after]
    return None


# ---------------------------------------------------------------------------
# Bottleneck inference
# ---------------------------------------------------------------------------

def _infer_bottleneck(
    question: str,
    outputs: list[SpecialistOutput],
    classification: DecisionClassification,
    mission_context: dict[str, Any],
) -> str:
    """Identify what is currently limiting progress."""
    lowered = question.lower()

    if "slack" in lowered and ("voice" in lowered or "voice core" in lowered):
        return "Daily usability and crew accessibility — USS TJR lacks a runtime the Captain can use conversationally today."

    if "bottleneck" in lowered:
        return "The question itself asks to identify the bottleneck — Commander must surface this from specialist inputs."

    if "notion" in lowered and ("source of truth" in lowered or "workspace" in lowered):
        return "Knowledge authority boundaries — unclear whether Notion is operational visibility or source of truth."

    if "msn-0008" in lowered or "0008d" in lowered or "0008e" in lowered:
        return "Commander Intelligence — current Commander synthesises but does not decide. Blocks downstream mission quality."

    intent = mission_context.get("intent", "")
    if intent == "technical_delivery":
        return "Implementation — no validated end-to-end path exists for the described capability."
    if intent == "mission_planning":
        return "Mission sequencing — current priorities and dependencies are not yet explicit."
    if intent == "knowledge_visibility":
        return "Knowledge authority — source-of-truth boundaries are not clear across GitHub, Supabase and Notion."

    if outputs:
        low = [o for o in outputs if o.confidence < 70]
        if low:
            return f"Evidence confidence — {', '.join(o.specialist for o in low)} returned low-confidence outputs."

    return "Not clearly identified from available specialist outputs. Commander should surface this from context."


# ---------------------------------------------------------------------------
# Opportunity cost
# ---------------------------------------------------------------------------

def _infer_opportunity_cost(
    question: str,
    options: list[dict[str, str]],
    classification: DecisionClassification,
) -> str:
    """What is not being done if Option A is chosen?"""
    if len(options) >= 2:
        opt_b = options[1]["description"]
        return f"Choosing Option A means {opt_b} is delayed or deprioritised."

    lowered = question.lower()
    if "slack" in lowered:
        return "Voice Core development is delayed — conversational runtime via voice remains unavailable."
    if "voice" in lowered:
        return "Slack Runtime is delayed — crew accessibility via existing channels is not improved."
    if "notion" in lowered:
        return "Engineering capacity is diverted from capability-building into visibility infrastructure."

    if classification.mode == DecisionMode.OPERATIONAL:
        return "Speed of delivery — a different sequence may reduce time to value but increase coordination cost."

    return "An alternative capability or mission is not progressed. Specific opportunity cost depends on current roadmap."


# ---------------------------------------------------------------------------
# Time to value
# ---------------------------------------------------------------------------

def _infer_time_to_value(
    options: list[dict[str, str]],
    outputs: list[SpecialistOutput],
) -> str:
    descriptions = " ".join(o["description"].lower() for o in options)
    if "slack" in descriptions:
        return "Short — Slack Runtime can deliver usable crew access within days of implementation."
    if "voice" in descriptions:
        return "Medium — Voice Core requires architecture, integration and testing before value is accessible."
    if "notion" in descriptions:
        return "Short — Notion visibility can be improved incrementally with immediate operational benefit."
    if any(o.confidence >= 80 for o in outputs):
        return "Short to medium — high-confidence specialist outputs suggest a clear path exists."
    return "Unknown — insufficient evidence to estimate time to value. Recommend defining acceptance criteria first."


# ---------------------------------------------------------------------------
# Reversibility
# ---------------------------------------------------------------------------

def _infer_reversibility(question: str, classification: DecisionClassification) -> str:
    lowered = question.lower()
    if any(t in lowered for t in ["source of truth", "architecture", "schema", "database", "infrastructure"]):
        return "Low — architectural and data decisions are expensive to reverse once in production."
    if any(t in lowered for t in ["slack", "notion", "visibility", "workspace"]):
        return "High — tooling and integration decisions can be changed without major structural cost."
    if any(t in lowered for t in ["voice core", "runtime", "core"]):
        return "Medium — runtime decisions can be reversed but involve re-sequencing mission work."
    if classification.mode == DecisionMode.GOVERNANCE:
        return "High — ownership assignments can be changed with Captain TJR authority."
    if classification.mode == DecisionMode.OPERATIONAL:
        return "Medium — execution sequences can be adjusted but may introduce rework."
    return "Medium — decision can likely be revisited but may consume resources to change."


# ---------------------------------------------------------------------------
# Specialist and reviewer positions
# ---------------------------------------------------------------------------

def _extract_specialist_positions(
    outputs: list[SpecialistOutput],
    options: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Map each specialist's recommendation to the closest option."""
    positions = []
    option_labels = [o["label"] for o in options]
    option_descs = [o["description"].lower() for o in options]

    for output in outputs:
        rec_lower = output.recommendation.lower()
        # Try to match the recommendation to an option
        stance = "Neutral"
        for label, desc in zip(option_labels, option_descs):
            key_words = [w for w in desc.split() if len(w) > 4]
            if any(kw in rec_lower for kw in key_words[:5]):
                stance = label
                break

        positions.append({
            "specialist": output.specialist,
            "confidence": str(output.confidence),
            "stance": stance,
            "recommendation": output.recommendation,
        })
    return positions


def _extract_reviewer_position(
    challenge: ChallengeReview,
    options: list[dict[str, str]],
) -> dict[str, str]:
    """Summarise the reviewer's challenge position."""
    return {
        "reviewer": challenge.reviewer,
        "challenge_position": challenge.challenge_position,
        "recommendation_adjustment": challenge.recommendation_adjustment,
        "escalation_required": str(challenge.escalation_required),
    }


# ---------------------------------------------------------------------------
# Situation summary
# ---------------------------------------------------------------------------

def _current_situation(
    outputs: list[SpecialistOutput],
    mission_context: dict[str, Any],
) -> str:
    specialists = [o.specialist for o in outputs]
    intent = mission_context.get("intent", "general_command")
    mission_id = mission_context.get("mission_id")

    situation_parts = []
    if mission_id:
        situation_parts.append(f"Active mission: {mission_id}.")
    situation_parts.append(f"Intent: {intent.replace('_', ' ')}.")
    if specialists:
        situation_parts.append(f"Specialists engaged: {', '.join(specialists)}.")
    if outputs:
        avg_conf = sum(o.confidence for o in outputs) // len(outputs)
        situation_parts.append(f"Average specialist confidence: {avg_conf}%.")
    return " ".join(situation_parts)


# ---------------------------------------------------------------------------
# Strategic alignment
# ---------------------------------------------------------------------------

def _strategic_alignment(
    question: str,
    classification: DecisionClassification,
    mission_context: dict[str, Any],
) -> str:
    intent = mission_context.get("intent", "general_command")
    lowered = question.lower()

    if "slack" in lowered:
        return "High — Slack Runtime directly supports daily Captain usability, a current USS TJR objective."
    if "voice core" in lowered:
        return "High — Voice Core is a long-term strategic capability but not the immediate bottleneck."
    if "notion" in lowered:
        return "Medium — Notion visibility supports operational clarity but is not a core technical capability."
    if "msn-0009" in lowered or "decision" in lowered and "intelligence" in lowered:
        return "High — Commander Decision Intelligence is a direct enabler of mission quality."
    if intent == "technical_delivery":
        return "Medium to high — technical delivery supports the USS TJR capability roadmap."
    if intent == "mission_planning":
        return "High — mission sequencing directly affects all active and future USS TJR objectives."
    return "Alignment unclear without current roadmap context. Commander should assess against active mission priorities."


# ---------------------------------------------------------------------------
# Required decision
# ---------------------------------------------------------------------------

def _required_decision(
    question: str,
    classification: DecisionClassification,
    options: list[dict[str, str]],
) -> str:
    if classification.mode == DecisionMode.STRATEGIC:
        if len(options) >= 2:
            labels = " or ".join(o["label"] for o in options)
            return f"Choose {labels} and state clearly why, including what is being sacrificed."
        return "Make a clear recommendation and explain the trade-off."

    if classification.mode == DecisionMode.OPERATIONAL:
        return "Define the execution sequence and identify the first concrete action."

    if classification.mode == DecisionMode.ARCHITECTURAL:
        return "Recommend where this component belongs and why. Include boundary and ownership implications."

    if classification.mode == DecisionMode.GOVERNANCE:
        return "Name the owner and the approval authority. State what changes if ownership is not clarified."

    return "Make a clear recommendation. Do not present all options as equally valid."
