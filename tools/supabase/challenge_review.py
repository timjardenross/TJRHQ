#!/usr/bin/env python3
"""Structured one-specialist challenge review for MSN-0008B.

MSN-0009B: Extended to accept decision_context so the reviewer can
explicitly challenge irreversible decisions and surface opportunity cost.
"""

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
    decision_context: dict[str, Any] | None = None,
) -> ChallengeReview:
    """Run a structured challenge review.

    MSN-0009B: decision_context is optional. When provided, the reviewer
    explicitly challenges irreversible decisions and surfaces opportunity cost.
    Existing callers that omit decision_context continue to work unchanged.
    """
    sources = context.get("source_paths", [])
    low_confidence = [output.specialist for output in [primary, *supporting] if output.confidence < 70]

    assumptions = [
        f"{primary.specialist}'s recommendation is correctly sequenced for the current mission priority.",
        "Retrieved knowledge is fresh enough to support the decision.",
    ]
    if not sources:
        assumptions.append("A decision can be made without live Supabase source citations.")

    # MSN-0009B: challenge the reversibility assumption when decision context is available
    reversibility = None
    opportunity_cost = None
    if decision_context:
        reversibility = decision_context.get("reversibility")
        opportunity_cost = decision_context.get("opportunity_cost")
        if reversibility and _is_low_reversibility(reversibility):
            assumptions.append(
                f"This decision is reversible enough to proceed without exhaustive validation "
                f"(reversibility assessed as: {reversibility})."
            )
        if opportunity_cost:
            assumptions.append(
                f"The opportunity cost of not choosing the alternative is acceptable: {opportunity_cost}"
            )

    risks = [
        "The recommendation may be technically sound but operationally premature.",
        "Missing or stale retrieval evidence may hide important constraints.",
    ]
    if low_confidence:
        risks.append(f"Low confidence from: {', '.join(low_confidence)}.")

    # MSN-0009B: add reversibility risk for low-reversibility decisions
    if reversibility and _is_low_reversibility(reversibility):
        risks.append(
            f"This decision has low reversibility ({reversibility}). "
            f"Reversing it later will be costly — validate thoroughly before committing."
        )

    # MSN-0009B: escalate if low reversibility and no sources
    irreversible_and_unsourced = bool(
        reversibility
        and _is_low_reversibility(reversibility)
        and not sources
    )
    escalation_required = bool(low_confidence) or not sources or irreversible_and_unsourced

    return ChallengeReview(
        reviewer=reviewer,
        reviewer_reason=reviewer_reason,
        challenge_position=_challenge_position(reviewer, reversibility),
        assumptions_challenged=assumptions,
        risks_identified=risks,
        alternative_view=recommendation_for(reviewer, question),
        recommendation_adjustment=adjustment_for(reviewer, primary, reversibility),
        escalation_required=escalation_required,
    )


def _challenge_position(reviewer: str, reversibility: str | None) -> str:
    base = f"{reviewer} challenges the recommendation before Commander finalisation."
    if reversibility and _is_low_reversibility(reversibility):
        return (
            f"{base} Given the low reversibility of this decision, "
            f"the reviewer demands stronger evidence before proceeding."
        )
    return base


def _is_low_reversibility(reversibility: str) -> bool:
    """Return True if the reversibility assessment indicates a hard-to-reverse decision."""
    lowered = reversibility.lower()
    return "low" in lowered or "expensive" in lowered or "costly" in lowered


def adjustment_for(
    reviewer: str,
    primary: SpecialistOutput,
    reversibility: str | None = None,
) -> str:
    base = _base_adjustment(reviewer, primary)
    if reversibility and _is_low_reversibility(reversibility):
        return (
            f"{base} Additionally, given the low reversibility of this decision, "
            f"produce a rollback plan or staged approach before committing."
        )
    return base


def _base_adjustment(reviewer: str, primary: SpecialistOutput) -> str:
    if reviewer == "Chief of Staff":
        return "Proceed only after mission priority, sequencing and dependencies are explicit."
    if reviewer == "Chief Engineer":
        return "Proceed only after architecture, validation path and implementation risk are explicit."
    if reviewer == "Knowledge Manager":
        return "Proceed only if source-of-truth and documentation placement are explicit."
    # MSN-0312: "Design Officer" is the canonical retitle of "UX Design
    # Officer" (same specialist); match either name.
    if reviewer in ("UX Design Officer", "Design Officer"):
        return "Proceed only if the workflow is understandable and low-friction for Captain TJR."
    if reviewer == "Code Review Specialist":
        return "Proceed only if testability and maintainability are addressed."
    return f"Refine {primary.specialist}'s recommendation before execution."
