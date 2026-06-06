#!/usr/bin/env python3
"""Structured one-specialist challenge review for MSN-0008B."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from specialist_executor import SpecialistOutput, recommendation_for


@dataclass
class ChallengeReview:
    reviewer: str
    reviewer_reason: str
    challenge_position: str
    assumptions_challenged: list[str]
    risks_identified: list[str]
    alternative_view: str
    recommendation_adjustment: str
    escalation_required: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "reviewer": self.reviewer,
            "reviewer_reason": self.reviewer_reason,
            "challenge_position": self.challenge_position,
            "assumptions_challenged": self.assumptions_challenged,
            "risks_identified": self.risks_identified,
            "alternative_view": self.alternative_view,
            "recommendation_adjustment": self.recommendation_adjustment,
            "escalation_required": self.escalation_required,
        }


def run_challenge_review(
    question: str,
    reviewer: str,
    reviewer_reason: str,
    primary: SpecialistOutput,
    supporting: list[SpecialistOutput],
    context: dict[str, Any],
) -> ChallengeReview:
    sources = context.get("source_paths", [])
    low_confidence = [output.specialist for output in [primary, *supporting] if output.confidence < 70]
    assumptions = [
        f"{primary.specialist}'s recommendation is correctly sequenced for the current mission priority.",
        "Retrieved knowledge is fresh enough to support the decision.",
    ]
    if not sources:
        assumptions.append("A decision can be made without live Supabase source citations.")
    risks = [
        "The recommendation may be technically sound but operationally premature.",
        "Missing or stale retrieval evidence may hide important constraints.",
    ]
    if low_confidence:
        risks.append(f"Low confidence from: {', '.join(low_confidence)}.")
    return ChallengeReview(
        reviewer=reviewer,
        reviewer_reason=reviewer_reason,
        challenge_position=f"{reviewer} challenges the recommendation before Commander finalisation.",
        assumptions_challenged=assumptions,
        risks_identified=risks,
        alternative_view=recommendation_for(reviewer, question),
        recommendation_adjustment=adjustment_for(reviewer, primary),
        escalation_required=bool(low_confidence) or not sources,
    )


def adjustment_for(reviewer: str, primary: SpecialistOutput) -> str:
    if reviewer == "Chief of Staff":
        return "Proceed only after mission priority, sequencing and dependencies are explicit."
    if reviewer == "Chief Engineer":
        return "Proceed only after architecture, validation path and implementation risk are explicit."
    if reviewer == "Knowledge Manager":
        return "Proceed only if source-of-truth and documentation placement are explicit."
    if reviewer == "UX Design Officer":
        return "Proceed only if the workflow is understandable and low-friction for Captain TJR."
    if reviewer == "Code Review Specialist":
        return "Proceed only if testability and maintainability are addressed."
    return f"Refine {primary.specialist}'s recommendation before execution."
