#!/usr/bin/env python3
"""Select the single challenge specialist for MSN-0008B."""

from __future__ import annotations

from dataclasses import dataclass

from mission_context_builder import infer_intent
from specialist_router import load_specialist_profiles


@dataclass(frozen=True)
class ReviewSelection:
    reviewer: str
    reason: str


REVIEWER_BY_PRIMARY = {
    "Chief Engineer": "Chief of Staff",
    "Chief of Staff": "Chief Engineer",
    "Knowledge Manager": "Chief of Staff",
    "UX Design Officer": "Chief Engineer",
    "Code Review Specialist": "Chief Engineer",
}

REVIEWER_BY_INTENT = {
    "technical_delivery": "Chief of Staff",
    "mission_planning": "Chief Engineer",
    "knowledge_visibility": "Chief of Staff",
    "experience_design": "Chief Engineer",
    "implementation_review": "Chief Engineer",
}


def select_review_specialist(
    question: str,
    primary_specialist: str,
    requested_reviewer: str | None = None,
    force: bool = False,
) -> ReviewSelection:
    profiles = load_specialist_profiles()
    if requested_reviewer:
        if requested_reviewer not in profiles:
            raise ValueError(f"Unknown reviewer: {requested_reviewer}")
        if force or requested_reviewer != primary_specialist:
            return ReviewSelection(requested_reviewer, "Reviewer provided by CLI")

    intent = "implementation_review" if primary_specialist == "Code Review Specialist" else infer_intent(question)
    reviewer = REVIEWER_BY_INTENT.get(intent) or REVIEWER_BY_PRIMARY.get(primary_specialist, "Chief of Staff")
    reason = f"Reviewer selected for intent {intent}"
    if reviewer == primary_specialist:
        reviewer = "Chief of Staff" if primary_specialist != "Chief of Staff" else "Chief Engineer"
        reason = "Reviewer adjusted to avoid duplicating the primary specialist"
    return ReviewSelection(reviewer, reason)
