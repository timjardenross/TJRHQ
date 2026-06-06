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
    response, _ = synthesize_commander(question, context, outputs, None)
    return response


def deterministic_synthesis(question: str, context: dict[str, Any], outputs: list[SpecialistOutput]) -> str:
    strongest = max(outputs, key=lambda output: output.confidence) if outputs else None
    recommendation = commander_recommendation(question, context, outputs, strongest)
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
    sources = sorted({source for output in outputs for source in output.sources})
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
    response, _ = synthesize_commander(question, context, outputs, challenge)
    return response


def deterministic_synthesis_with_challenge(
    question: str,
    context: dict[str, Any],
    outputs: list[SpecialistOutput],
    challenge: ChallengeReview,
) -> str:
    initial = deterministic_synthesis(question, context, outputs)
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


def synthesize_commander(
    question: str,
    context: dict[str, Any],
    outputs: list[SpecialistOutput],
    challenge: ChallengeReview | None,
) -> tuple[str, dict[str, str]]:
    deterministic = (
        deterministic_synthesis_with_challenge(question, context, outputs, challenge)
        if challenge
        else deterministic_synthesis(question, context, outputs)
    )
    provider = os.environ.get("COMMANDER_SYNTHESIS_PROVIDER", DEFAULT_SYNTHESIS_PROVIDER).lower()
    model = os.environ.get("COMMANDER_SYNTHESIS_MODEL", DEFAULT_SYNTHESIS_MODEL)
    if provider != "ollama":
        return deterministic, {"provider": "deterministic", "model": "template"}
    try:
        response = ollama_synthesis(question, context, outputs, challenge, model)
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
) -> str:
    base_url = os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).rstrip("/")
    payload = json.dumps(
        {
            "model": model,
            "prompt": commander_prompt(question, context, outputs, challenge),
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
) -> str:
    sources = sorted({source for output in outputs for source in output.sources})
    challenge_text = "None"
    if challenge:
        challenge_text = json.dumps(challenge.as_dict(), indent=2)
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
