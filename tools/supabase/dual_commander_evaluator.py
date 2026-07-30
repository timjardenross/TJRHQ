#!/usr/bin/env python3
"""Dual Commander Evaluation for USS-TJR-MSN-0010A.

Runs two Commander models (primary and candidate) independently over the same
specialist context and produces a side-by-side comparison. Does not let either
model see the other's response before generating its own.

Usage:
    from dual_commander_evaluator import run_dual_commander
    evaluation = run_dual_commander(question, context, outputs, challenge)
    print(evaluation.formatted_output())
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from challenge_review import ChallengeReview
from commander_synthesis import (
    commander_prompt,
    deterministic_synthesis,
    deterministic_synthesis_with_challenge,
    extract_section,
    strip_thinking,
)
from specialist_executor import SpecialistOutput

# decision_context is optional — imported lazily to avoid circular imports


# ---------------------------------------------------------------------------
# Environment configuration
# ---------------------------------------------------------------------------

DEFAULT_PRIMARY_MODEL = "qwen3:8b"
DEFAULT_CANDIDATE_MODEL = "deepseek-r1:14b"
DEFAULT_PROVIDER = "ollama"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class DualCommanderEvaluation:
    """Holds both Commander responses and a template-based comparison."""

    primary_model: str
    candidate_model: str
    primary_response: str
    candidate_response: str
    comparison_summary: str
    areas_of_agreement: list[str]
    areas_of_difference: list[str]
    decision_style_observations: list[str]
    practical_usefulness_notes: list[str]
    captain_preferred_model: str | None = None
    captain_decision_status: str = "Pending"
    captain_notes: str | None = None

    def formatted_output(self) -> str:
        """Render the dual evaluation in the required output format."""
        lines = [
            "# Dual Commander Evaluation",
            "",
            "## Qwen Commander Recommendation",
            "",
            self.primary_response,
            "",
            "## DeepSeek Commander Recommendation",
            "",
            self.candidate_response,
            "",
            "## Commander Comparison",
            "",
            "### Areas of Agreement",
        ]
        lines.extend(f"- {item}" for item in self.areas_of_agreement)
        lines.extend([
            "",
            "### Areas of Difference",
        ])
        lines.extend(f"- {item}" for item in self.areas_of_difference)
        lines.extend([
            "",
            "### Decision Style Observations",
        ])
        lines.extend(f"- {item}" for item in self.decision_style_observations)
        lines.extend([
            "",
            "### Practical Usefulness Notes",
        ])
        lines.extend(f"- {item}" for item in self.practical_usefulness_notes)
        lines.extend([
            "",
            "### Captain Decision",
            "Pending",
        ])
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a dict suitable for collaboration log JSON."""
        return {
            "dual_commander_enabled": True,
            "primary_model": self.primary_model,
            "candidate_model": self.candidate_model,
            "primary_response": self.primary_response,
            "candidate_response": self.candidate_response,
            "comparison_summary": self.comparison_summary,
            "areas_of_agreement": self.areas_of_agreement,
            "areas_of_difference": self.areas_of_difference,
            "decision_style_observations": self.decision_style_observations,
            "practical_usefulness_notes": self.practical_usefulness_notes,
            "captain_preferred_model": self.captain_preferred_model,
            "captain_decision_status": self.captain_decision_status,
            "captain_notes": self.captain_notes,
        }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_dual_commander(
    question: str,
    context: dict[str, Any],
    outputs: list[SpecialistOutput],
    challenge: ChallengeReview | None,
    decision_context: dict[str, Any] | None = None,
) -> DualCommanderEvaluation:
    """Run primary and candidate Commander models independently and compare.

    Both models receive exactly the same context (including decision_context from
    MSN-0009A when provided). Neither sees the other's output before generating
    its own response.
    """
    primary_model = os.environ.get("COMMANDER_PRIMARY_MODEL", DEFAULT_PRIMARY_MODEL)
    candidate_model = os.environ.get("COMMANDER_CANDIDATE_MODEL", DEFAULT_CANDIDATE_MODEL)
    provider = os.environ.get("COMMANDER_SYNTHESIS_PROVIDER", DEFAULT_PROVIDER).lower()

    fallback = (
        deterministic_synthesis_with_challenge(question, context, outputs, challenge, decision_context)
        if challenge
        else deterministic_synthesis(question, context, outputs, decision_context)
    )

    print(f"  [Dual Commander] Calling primary model: {primary_model}")
    primary_response = _call_model(
        question, context, outputs, challenge,
        model=primary_model, provider=provider, fallback=fallback,
        decision_context=decision_context,
    )

    print(f"  [Dual Commander] Calling candidate model: {candidate_model}")
    candidate_response = _call_model(
        question, context, outputs, challenge,
        model=candidate_model, provider=provider, fallback=fallback,
        decision_context=decision_context,
    )

    comparison = _compare(primary_model, primary_response, candidate_model, candidate_response)

    return DualCommanderEvaluation(
        primary_model=primary_model,
        candidate_model=candidate_model,
        primary_response=primary_response,
        candidate_response=candidate_response,
        comparison_summary=comparison["summary"],
        areas_of_agreement=comparison["areas_of_agreement"],
        areas_of_difference=comparison["areas_of_difference"],
        decision_style_observations=comparison["decision_style_observations"],
        practical_usefulness_notes=comparison["practical_usefulness_notes"],
    )


# ---------------------------------------------------------------------------
# Model call helpers
# ---------------------------------------------------------------------------

def _call_model(
    question: str,
    context: dict[str, Any],
    outputs: list[SpecialistOutput],
    challenge: ChallengeReview | None,
    model: str,
    provider: str,
    fallback: str,
    decision_context: dict[str, Any] | None = None,
) -> str:
    """Call a single Ollama model and return its response.

    Falls back to deterministic synthesis on any failure so the whole
    runtime does not crash if one model is unavailable.

    decision_context (MSN-0009A) is passed to the model when available,
    ensuring both Commander models receive the same structured decision frame.
    """
    if provider != "ollama":
        print(
            f"  Warning: Dual Commander requires COMMANDER_SYNTHESIS_PROVIDER=ollama. "
            f"Using deterministic fallback for {model}."
        )
        return fallback

    try:
        # Import here so the module is usable without ollama being present
        # (deterministic tests never reach this path).
        from commander_synthesis import ollama_synthesis  # noqa: PLC0415

        response = ollama_synthesis(question, context, outputs, challenge, model, decision_context)
        if not response.strip():
            print(f"  Warning: {model} returned an empty response. Using deterministic fallback.")
            return fallback
        return response
    except Exception as error:  # noqa: BLE001
        print(f"  Warning: {model} unavailable ({error}). Using deterministic fallback.")
        return fallback


# ---------------------------------------------------------------------------
# Comparison logic (deterministic / template-based — no third model)
# ---------------------------------------------------------------------------

def _compare(
    primary_model: str,
    primary_response: str,
    candidate_model: str,
    candidate_response: str,
) -> dict[str, Any]:
    """Produce a template-based comparison of two Commander responses.

    Does not call any model. Uses structural and keyword analysis only.
    """
    primary_sections = _extract_section_names(primary_response)
    candidate_sections = _extract_section_names(candidate_response)
    shared_sections = primary_sections & candidate_sections

    primary_position = (
        extract_section(primary_response, "Position")
        or extract_section(primary_response, "Final Recommendation")
        or extract_section(primary_response, "Position / Recommendation")
        or extract_section(primary_response, "Initial Recommendation")
    )
    candidate_position = (
        extract_section(candidate_response, "Position")
        or extract_section(candidate_response, "Final Recommendation")
        or extract_section(candidate_response, "Position / Recommendation")
        or extract_section(candidate_response, "Initial Recommendation")
    )

    primary_len = len(primary_response)
    candidate_len = len(candidate_response)

    # --- Areas of agreement ---
    agreements: list[str] = []
    if shared_sections:
        agreements.append(
            f"Both models produced common sections: {', '.join(sorted(shared_sections))}."
        )
    if primary_position and candidate_position:
        shared_kw = _shared_keywords(primary_position, candidate_position)
        if shared_kw:
            top = sorted(shared_kw)[:6]
            agreements.append(
                f"Both position sections share key themes: {', '.join(top)}."
            )
    if not agreements:
        agreements.append(
            "Both models produced a Commander-format recommendation for the same question."
        )

    # --- Areas of difference ---
    differences: list[str] = []
    only_primary = primary_sections - candidate_sections
    only_candidate = candidate_sections - primary_sections
    if only_primary:
        differences.append(
            f"{primary_model} included sections not in candidate: {', '.join(sorted(only_primary))}."
        )
    if only_candidate:
        differences.append(
            f"{candidate_model} included sections not in primary: {', '.join(sorted(only_candidate))}."
        )
    len_diff = abs(primary_len - candidate_len)
    if len_diff > 200:
        longer = primary_model if primary_len > candidate_len else candidate_model
        differences.append(
            f"{longer} produced a notably longer response ({len_diff} additional chars)."
        )
    if not differences:
        differences.append("No significant structural differences detected in this run.")

    # --- Decision style observations ---
    style_obs: list[str] = [
        f"{primary_model} response: {primary_len} chars, {len(primary_sections)} sections.",
        f"{candidate_model} response: {candidate_len} chars, {len(candidate_sections)} sections.",
        "Both models received the same context independently with no cross-visibility.",
        "Latency is sequential (primary then candidate); total wall time is roughly additive.",
        "Comparison is structural and keyword-based. Semantic quality requires Captain TJR review.",
    ]

    # --- Practical usefulness notes ---
    usefulness: list[str] = [
        "Compare the Position / Final Recommendation sections for decisiveness and clarity.",
        "Compare Next Actions sections for specificity and actionability.",
        "Note which model better surfaces trade-offs relevant to this mission context.",
        "Record your preference in captain_preferred_model after each run.",
        "This is one data point. Collect at least 5–10 runs before choosing a default Commander.",
    ]

    summary = (
        f"{primary_model} vs {candidate_model}: "
        f"{len(agreements)} agreement(s), {len(differences)} difference(s) detected. "
        f"Captain decision: Pending."
    )

    return {
        "summary": summary,
        "areas_of_agreement": agreements,
        "areas_of_difference": differences,
        "decision_style_observations": style_obs,
        "practical_usefulness_notes": usefulness,
    }


def _extract_section_names(response: str) -> set[str]:
    """Return the set of ## section headings in a Commander response."""
    sections: set[str] = set()
    for line in response.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            sections.add(stripped[3:].strip())
    return sections


def _shared_keywords(text_a: str, text_b: str) -> set[str]:
    """Return meaningful words that appear in both texts."""
    _STOP = {
        "the", "a", "an", "and", "or", "to", "of", "is", "in", "for",
        "with", "this", "that", "be", "as", "on", "at", "by", "are",
        "it", "its", "we", "our", "should", "will", "not", "but", "if",
        "from", "then", "than", "have", "has", "been", "after", "before",
    }
    def words(text: str) -> set[str]:
        return {
            re.sub(r"[^a-z]", "", w.lower())
            for w in text.split()
            if len(w) > 4 and w.lower().strip(".,;:()") not in _STOP
        }
    return words(text_a) & words(text_b) - {""}
