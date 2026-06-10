#!/usr/bin/env python3
"""Commander TJR synthesis for fan-out specialist perspectives."""

from __future__ import annotations

import json
import os
import re
from typing import Any
import urllib.error
import urllib.request

from challenge_review import ChallengeReview
from specialist_executor import SpecialistOutput


DEFAULT_SYNTHESIS_PROVIDER = "deterministic"
DEFAULT_SYNTHESIS_MODEL = "qwen3:8b"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"


def synthesize(question: str, context: dict[str, Any], outputs: list[SpecialistOutput]) -> str:
    response, _ = synthesize_commander(question, context, outputs, None, None)
    return response


def deterministic_synthesis(
    question: str,
    context: dict[str, Any],
    outputs: list[SpecialistOutput],
    decision_context: dict[str, Any] | None = None,
) -> str:
    strongest = max(outputs, key=lambda output: output.confidence) if outputs else None
    recommendation = commander_recommendation(question, context, outputs, strongest)
    sources = sorted({source for output in outputs for source in output.sources})

    # MSN-0009A: strategic mode uses the new mandatory format
    if decision_context and decision_context.get("decision_mode") == "strategic":
        return _deterministic_strategic(question, context, outputs, decision_context, recommendation, sources)

    lines = [
        "# Commander TJR Recommendation",
        "",
        "## Position / Recommendation",
        recommendation,
        "",
        "## Specialist Inputs",
    ]
    for output in outputs:
        lines.append(f"- {output.specialist} ({output.confidence}%): {output.recommendation}")
    lines.extend(["", "## Key Trade-offs"])
    lines.extend(tradeoffs(outputs))
    lines.extend(["", "## Risks"])
    lines.extend(risks(outputs))
    lines.extend(["", "## Next Actions"])
    lines.extend(next_actions(context, outputs))
    lines.extend(["", "## Sources"])
    if sources:
        lines.extend(f"- {source}" for source in sources)
    else:
        lines.append("- No live Supabase sources were available in this run.")
    return "\n".join(lines)


def _deterministic_strategic(
    question: str,
    context: dict[str, Any],
    outputs: list[SpecialistOutput],
    decision_context: dict[str, Any],
    recommendation: str,
    sources: list[str],
) -> str:
    """Deterministic output in the MSN-0009A strategic format."""
    bottleneck = decision_context.get("current_bottleneck", "Not identified.")
    opportunity_cost = decision_context.get("opportunity_cost", "Not identified.")
    reversibility = decision_context.get("reversibility", "Unknown.")
    options = decision_context.get("options", [])

    # Build recommended action line
    rec_action = f"Recommended Action: {recommendation}"

    # Trade-offs from options
    trade_gained = "Addresses the current bottleneck and progresses the primary mission objective."
    trade_sacrificed = opportunity_cost
    if len(options) >= 2:
        trade_gained = f"Choosing {options[0]['label']}: {options[0]['description']}"
        trade_sacrificed = f"Delaying {options[1]['label']}: {options[1]['description']}"

    # Next action
    mission_id = context.get("mission_id")
    next_action_line = (
        f"Raise a mission record for this decision"
        + (f" under {mission_id}" if mission_id else "")
        + " and assign a specialist owner before the next session."
    )

    lines = [
        "# Commander TJR Strategic Decision",
        "",
        "## Recommended Action",
        rec_action,
        "",
        f"Current bottleneck addressed: {bottleneck}",
        "",
        "## Why",
    ]
    # Rationale from specialist positions
    if outputs:
        lines.append(f"Specialist consensus supports this direction:")
        for o in outputs:
            lines.append(f"- {o.specialist} ({o.confidence}%): {o.recommendation}")
    lines.extend([
        "",
        f"Strategic alignment: {decision_context.get('strategic_alignment', 'Not assessed.')}",
        f"Time to value: {decision_context.get('time_to_value', 'Unknown.')}",
        "",
        "## Trade-Offs",
        f"Gained: {trade_gained}",
        f"Sacrificed: {trade_sacrificed}",
        "",
        "## Risks",
    ])
    lines.extend(risks(outputs))
    lines.append(f"- Reversibility: {reversibility}")
    lines.extend([
        "",
        "## Next Action",
        f"- {next_action_line}",
        "",
        "## Sources",
    ])
    if sources:
        lines.extend(f"- {source}" for source in sources)
    else:
        lines.append("- No live Supabase sources were available in this run.")
    return "\n".join(lines)


def synthesize_with_challenge(
    question: str,
    context: dict[str, Any],
    outputs: list[SpecialistOutput],
    challenge: ChallengeReview,
) -> str:
    response, _ = synthesize_commander(question, context, outputs, challenge, None)
    return response


def deterministic_synthesis_with_challenge(
    question: str,
    context: dict[str, Any],
    outputs: list[SpecialistOutput],
    challenge: ChallengeReview,
    decision_context: dict[str, Any] | None = None,
) -> str:
    # MSN-0009B: strategic mode uses the ## Recommended Action format with challenge integrated
    if decision_context and decision_context.get("decision_mode") == "strategic":
        return _deterministic_strategic_with_challenge(
            question, context, outputs, challenge, decision_context
        )

    initial = deterministic_synthesis(question, context, outputs, decision_context)
    initial_recommendation = commander_recommendation(
        question,
        context,
        outputs,
        max(outputs, key=lambda output: output.confidence) if outputs else None,
    )
    final = final_recommendation(context, challenge)
    sources = sorted({source for output in outputs for source in output.sources})
    lines = [
        "# Commander TJR Final Recommendation",
        "",
        "## Initial Recommendation",
        initial_recommendation,
        "",
        "## Expert Challenge",
        f"Reviewer: {challenge.reviewer}",
        f"Challenge Position: {challenge.challenge_position}",
        "Assumptions Challenged:",
        *[f"- {item}" for item in challenge.assumptions_challenged],
        "Risks Identified:",
        *[f"- {item}" for item in challenge.risks_identified],
        f"Alternative View: {challenge.alternative_view}",
        f"Recommendation Adjustment: {challenge.recommendation_adjustment}",
        f"Escalation Required? {'yes' if challenge.escalation_required else 'no'}",
        "",
        "## Final Recommendation",
        final,
        "",
        "## Why This Position Was Chosen",
        why_chosen(context, challenge),
        "",
        "## Risks Accepted",
        *[f"- {item}" for item in challenge.risks_identified],
        "",
        "## Next Actions",
        *next_actions(context, outputs),
        "",
        "## Sources",
    ]
    if sources:
        lines.extend(f"- {source}" for source in sources)
    else:
        lines.append("- No live Supabase sources were available in this run.")
    lines.extend(["", "<!-- Initial synthesis retained internally for traceability. -->"])
    lines.append(f"<!-- initial_length={len(initial)} -->")
    return "\n".join(lines)


def _deterministic_strategic_with_challenge(
    question: str,
    context: dict[str, Any],
    outputs: list[SpecialistOutput],
    challenge: ChallengeReview,
    decision_context: dict[str, Any],
) -> str:
    """MSN-0009B: strategic format applied to challenge mode output.

    Merges the reviewer adjustment directly into the ## Recommended Action,
    rather than appending it as a separate 'Final Recommendation' section.
    """
    bottleneck = decision_context.get("current_bottleneck", "Not identified.")
    opportunity_cost = decision_context.get("opportunity_cost", "Not identified.")
    reversibility = decision_context.get("reversibility", "Unknown.")
    options = decision_context.get("options", [])
    sources = sorted({source for output in outputs for source in output.sources})
    mission_id = context.get("mission_id")

    # Base recommendation — adjusted by the reviewer
    base_rec = commander_recommendation(
        question, context, outputs,
        max(outputs, key=lambda o: o.confidence) if outputs else None,
    )
    # Weave the reviewer adjustment into the recommendation
    rec_action = (
        f"Recommended Action: {base_rec} "
        f"— with reviewer adjustment: {challenge.recommendation_adjustment}"
    )

    # Trade-offs
    trade_gained = "Addresses the current bottleneck and progresses the primary mission objective."
    trade_sacrificed = opportunity_cost
    if len(options) >= 2:
        trade_gained = f"Choosing {options[0]['label']}: {options[0]['description']}"
        trade_sacrificed = f"Delaying {options[1]['label']}: {options[1]['description']}"

    # Next action
    next_action_line = (
        "Raise a mission record for this decision"
        + (f" under {mission_id}" if mission_id else "")
        + " and assign a specialist owner before the next session."
    )

    lines = [
        "# Commander TJR Strategic Decision",
        "",
        "## Recommended Action",
        rec_action,
        "",
        f"Current bottleneck addressed: {bottleneck}",
        "",
        "## Expert Challenge",
        f"Reviewer: {challenge.reviewer} — {challenge.reviewer_reason}",
        f"Challenge: {challenge.challenge_position}",
        "Assumptions challenged:",
        *[f"- {a}" for a in challenge.assumptions_challenged],
        f"Escalation required: {'yes' if challenge.escalation_required else 'no'}",
        "",
        "## Why",
    ]
    if outputs:
        lines.append("Specialist consensus with reviewer adjustment applied:")
        for o in outputs:
            lines.append(f"- {o.specialist} ({o.confidence}%): {o.recommendation}")
    lines.extend([
        "",
        f"Strategic alignment: {decision_context.get('strategic_alignment', 'Not assessed.')}",
        f"Time to value: {decision_context.get('time_to_value', 'Unknown.')}",
        f"Reviewer rationale: {why_chosen(context, challenge)}",
        "",
        "## Trade-Offs",
        f"Gained: {trade_gained}",
        f"Sacrificed: {trade_sacrificed}",
        "",
        "## Risks",
    ])
    lines.extend(risks(outputs))
    lines.extend(f"- {r}" for r in challenge.risks_identified)
    lines.append(f"- Reversibility: {reversibility}")
    lines.extend([
        "",
        "## Next Action",
        f"- {next_action_line}",
        "",
        "## Sources",
    ])
    if sources:
        lines.extend(f"- {source}" for source in sources)
    else:
        lines.append("- No live Supabase sources were available in this run.")
    return "\n".join(lines)


def synthesize_commander(
    question: str,
    context: dict[str, Any],
    outputs: list[SpecialistOutput],
    challenge: ChallengeReview | None,
    decision_context: dict[str, Any] | None = None,
) -> tuple[str, dict[str, str]]:
    deterministic = (
        deterministic_synthesis_with_challenge(question, context, outputs, challenge, decision_context)
        if challenge
        else deterministic_synthesis(question, context, outputs, decision_context)
    )
    provider = os.environ.get("COMMANDER_SYNTHESIS_PROVIDER", DEFAULT_SYNTHESIS_PROVIDER).lower()
    model = os.environ.get("COMMANDER_SYNTHESIS_MODEL", DEFAULT_SYNTHESIS_MODEL)
    if provider != "ollama":
        return deterministic, {"provider": "deterministic", "model": "template"}
    try:
        response = ollama_synthesis(question, context, outputs, challenge, model, decision_context)
        if not response.strip():
            return deterministic, {"provider": "deterministic", "model": "template"}
        return response, {"provider": "ollama", "model": model}
    except Exception:
        return deterministic, {"provider": "deterministic", "model": "template"}


def ollama_synthesis(
    question: str,
    context: dict[str, Any],
    outputs: list[SpecialistOutput],
    challenge: ChallengeReview | None,
    model: str,
    decision_context: dict[str, Any] | None = None,
) -> str:
    base_url = os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).rstrip("/")
    payload = json.dumps(
        {
            "model": model,
            "prompt": commander_prompt(question, context, outputs, challenge, decision_context),
            "stream": False,
            "think": False,
            "options": {"temperature": 0.2},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/api/generate",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    timeout = float(os.environ.get("COMMANDER_SYNTHESIS_TIMEOUT_SECONDS", "30"))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    return strip_thinking(body.get("response") or body.get("thinking") or "")


def commander_prompt(
    question: str,
    context: dict[str, Any],
    outputs: list[SpecialistOutput],
    challenge: ChallengeReview | None,
    decision_context: dict[str, Any] | None = None,
) -> str:
    sources = sorted({source for output in outputs for source in output.sources})
    challenge_text = "None"
    if challenge:
        challenge_text = json.dumps(challenge.as_dict(), indent=2)

    # MSN-0009A: use decision-mode-specific prompt when decision context is available
    if decision_context:
        return _decision_prompt(question, context, outputs, challenge_text, decision_context, sources)

    # Legacy prompt (retained for backwards compatibility)
    return f"""/no_think
You are Commander TJR. Produce one clear operational recommendation.

Rules:
- Make a recommendation.
- Surface disagreements or tension.
- Explain trade-offs.
- Reference only the provided sources.
- Do not invent evidence or sources.
- Do not say all options are equally valid unless Captain TJR must decide a strategic trade-off.

Required markdown sections:
## Position
## Rationale
## Specialist Inputs
## Key Trade-offs
## Risks
## Next Actions
## Sources

Question:
{question}

Mission context:
{json.dumps(context, indent=2)}

Specialist outputs:
{json.dumps([output.as_dict() for output in outputs], indent=2)}

Challenge review:
{challenge_text}

Allowed sources:
{json.dumps(sources, indent=2)}
"""


def _decision_prompt(
    question: str,
    context: dict[str, Any],
    outputs: list[SpecialistOutput],
    challenge_text: str,
    decision_context: dict[str, Any],
    sources: list[str],
) -> str:
    """MSN-0009A decision-mode-aware Commander prompt."""
    mode = decision_context.get("decision_mode", "operational")
    bottleneck = decision_context.get("current_bottleneck", "Not identified.")
    opportunity_cost = decision_context.get("opportunity_cost", "Not identified.")
    time_to_value = decision_context.get("time_to_value", "Unknown.")
    reversibility = decision_context.get("reversibility", "Unknown.")
    strategic_alignment = decision_context.get("strategic_alignment", "Unknown.")
    required_decision = decision_context.get("required_decision", "Make a clear recommendation.")
    options = decision_context.get("options", [])
    specialist_positions = decision_context.get("specialist_positions", [])
    reviewer_position = decision_context.get("reviewer_position")

    options_text = "\n".join(
        f"- {o['label']}: {o['description']}" for o in options
    ) or "- Proceed with the recommended path."

    positions_text = "\n".join(
        f"- {p['specialist']} ({p['confidence']}% confidence, stance: {p['stance']}): {p['recommendation']}"
        for p in specialist_positions
    ) or "- No specialist positions available."

    reviewer_text = "None"
    if reviewer_position:
        reviewer_text = (
            f"Reviewer: {reviewer_position['reviewer']}\n"
            f"Challenge: {reviewer_position['challenge_position']}\n"
            f"Adjustment: {reviewer_position['recommendation_adjustment']}\n"
            f"Escalation required: {reviewer_position['escalation_required']}"
        )

    if mode == "strategic":
        format_instruction = """Required output format (strategic mode):
## Recommended Action
Begin with exactly: "Recommended Action: [your recommendation in one sentence]"
Then expand in 2–3 sentences. Do NOT begin with "Here are some options" or present all choices as equal.

## Why
Explain the reasoning. Reference the bottleneck, strategic alignment and specialist positions.

## Trade-Offs
What is gained by this recommendation.
What is sacrificed or delayed.

## Risks
What risks are being accepted. Reference the opportunity cost and reversibility.

## Next Action
One concrete next step. Must be specific and actionable.

## Sources
List sources used."""

    elif mode == "governance":
        format_instruction = """Required output format (governance mode):
## Ownership Recommendation
Name the owner and approval authority clearly.

## Why
Explain why this ownership assignment is appropriate.

## Risks
What happens if ownership is not assigned.

## Next Action
One concrete next step.

## Sources
List sources used."""

    elif mode == "architectural":
        format_instruction = """Required output format (architectural mode):
## Architecture Recommendation
State clearly where this component belongs and why.

## Rationale
Technical and operational reasons for this placement.

## Trade-Offs
What this architecture gains and what it constrains.

## Risks
What could go wrong with this architectural decision.

## Next Action
One concrete next step.

## Sources
List sources used."""

    else:  # operational
        format_instruction = """Required output format (operational mode):
## Recommended Sequence
State the execution sequence clearly.

## Rationale
Why this sequence is correct given current constraints.

## Key Trade-offs
Speed vs quality, short-term vs long-term.

## Risks
What could block or delay execution.

## Next Action
First concrete step to begin.

## Sources
List sources used."""

    return f"""/no_think
You are Commander TJR. You are a Chief of Staff and Strategic Decision Officer, not a technical writer or architect.

Your job is to make a DECISION, not to summarise options.

Decision mode: {mode.upper()}

Forbidden behaviours:
- Do NOT begin with "Here are some options..."
- Do NOT produce architecture summaries unless mode is architectural.
- Do NOT produce meeting notes or implementation plans unless mode is operational.
- Do NOT say all options are equally valid.
- Do NOT invent evidence or sources.

Rules:
- Make one clear recommendation.
- State what is being sacrificed.
- Reference only the provided sources.
- Apply the Strategic Decision Framework below.

Strategic Decision Framework:
- Strategic Alignment: {strategic_alignment}
- Current Bottleneck: {bottleneck}
- Opportunity Cost: {opportunity_cost}
- Time to Value: {time_to_value}
- Reversibility: {reversibility}

Question:
{question}

Required Decision:
{required_decision}

Options:
{options_text}

Specialist Positions:
{positions_text}

Reviewer Position:
{reviewer_text}

Challenge review (full):
{challenge_text}

Mission context:
{json.dumps(context, indent=2)}

Allowed sources:
{json.dumps(sources, indent=2)}

{format_instruction}
"""


def strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def extract_section(response: str, section: str) -> str:
    pattern = rf"^##\s+{re.escape(section)}\s*$"
    lines = response.splitlines()
    start = None
    for index, line in enumerate(lines):
        if re.match(pattern, line.strip(), flags=re.IGNORECASE):
            start = index + 1
            break
    if start is None:
        return ""
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end]).strip()


def extract_bullets(response: str, section: str) -> list[str]:
    content = extract_section(response, section)
    bullets = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped[2:])
    if bullets:
        return bullets
    return [content] if content else []


def final_recommendation(context: dict[str, Any], challenge: ChallengeReview) -> str:
    if context.get("intent") == "technical_delivery":
        return f"Proceed with the smallest technical path, but apply the reviewer adjustment: {challenge.recommendation_adjustment}"
    if context.get("intent") == "mission_planning":
        return f"Proceed as a mission plan, with the reviewer adjustment: {challenge.recommendation_adjustment}"
    if context.get("intent") == "knowledge_visibility":
        return f"Proceed with source-of-truth boundaries first, with the reviewer adjustment: {challenge.recommendation_adjustment}"
    return f"Proceed with the primary recommendation after applying this adjustment: {challenge.recommendation_adjustment}"


def why_chosen(context: dict[str, Any], challenge: ChallengeReview) -> str:
    if challenge.escalation_required:
        return "The final position keeps momentum while explicitly accepting that Captain TJR may need to resolve priority or evidence gaps."
    return "The final position preserves the primary specialist direction while absorbing the single highest-value reviewer constraint."


def commander_recommendation(
    question: str,
    context: dict[str, Any],
    outputs: list[SpecialistOutput],
    strongest: SpecialistOutput | None,
) -> str:
    if not outputs:
        return "Do not proceed until at least one specialist can provide a perspective."
    if context.get("intent") == "technical_delivery":
        return "Build the smallest end-to-end path first: architecture, implementation, validation, then operational visibility."
    if context.get("intent") == "mission_planning":
        return "Treat this as a sequenced mission: clarify objective, assign owner, identify dependencies, and define acceptance criteria."
    if context.get("intent") == "knowledge_visibility":
        return "Keep GitHub authoritative, use Supabase for retrieval, and expose only operational visibility in Notion."
    if strongest:
        return f"Proceed with {strongest.specialist}'s recommendation as the lead path, with supporting specialist constraints applied."
    return f"Answer the Captain's question directly: {question}"


def tradeoffs(outputs: list[SpecialistOutput]) -> list[str]:
    specialists = {output.specialist for output in outputs}
    items = []
    if "Chief Engineer" in specialists and "UX Design Officer" in specialists:
        items.append("- Technical completeness must be balanced against workflow simplicity.")
    if "Chief of Staff" in specialists and "Chief Engineer" in specialists:
        items.append("- Mission sequencing may constrain the ideal engineering order.")
    if "Knowledge Manager" in specialists:
        items.append("- Visibility improves operations, but source-of-truth boundaries must remain clear.")
    if not items:
        items.append("- Main trade-off is confidence versus speed: use the current recommendation, but validate with sources.")
    return items


def risks(outputs: list[SpecialistOutput]) -> list[str]:
    items = [
        "- Low-confidence specialist outputs should be escalated before major decisions.",
        "- Stale embeddings or missing Supabase credentials can reduce retrieval quality.",
    ]
    if any(not output.sources for output in outputs):
        items.append("- One or more specialists produced a fallback perspective without live source citations.")
    return items


def next_actions(context: dict[str, Any], outputs: list[SpecialistOutput]) -> list[str]:
    actions = []
    mission_id = context.get("mission_id")
    if mission_id:
        actions.append(f"- Attach this recommendation to mission `{mission_id}`.")
    actions.append("- Review cited sources and confirm the recommendation matches current repository truth.")
    actions.append("- Convert the recommendation into implementation tasks with acceptance criteria.")
    if any(output.confidence < 70 for output in outputs):
        actions.append("- Escalate low-confidence areas to Captain TJR or the relevant lead specialist.")
    return actions
